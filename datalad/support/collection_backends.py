# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
Implements collection backends
"""

import logging
from os.path import basename, split, join
from six import string_types

from rdflib import Graph, RDF, RDFS

from datalad.consts import REPO_CONFIG_FILE, REPO_STD_META_FILE
from datalad.support.collection import CollectionBackend, Collection
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.handle_backends import CollectionRepoHandleBackend
from datalad.support.metadatahandler import DLNS

lgr = logging.getLogger('datalad.collectionbackends')


class CollectionRepoBackend(CollectionBackend):
    """CollectionBackend for collection repositories.

    Implements a CollectionBackend that is connected to a branch of a
    collection repository.
    """
    # TODO: Better name

    # Note (reminder): If it's a remote branch: Should writing data imply a
    # push or sth.?
    # Probably not, but it should be well documented, since 'saving' a
    # collection with a remote url and then it's just locally done, could be
    # confusing to users not familiar with git.
    # To be worked out when implementing such commands.
    #
    # Better to not allow to commit to remote branches and force the user to
    # clone it first.

    def __init__(self, repo, branch=None):
        """
        Parameters
        ----------
        repo: CollectionRepo or str
          in case of a string it's interpreted as being the path to the
          repository in question.
        branch: str
        """
        if isinstance(repo, CollectionRepo):
            self.repo = repo
        elif isinstance(repo, string_types):
            self.repo = CollectionRepo(repo)
        else:
            msg = "Invalid repo type: %s" % type(repo)
            lgr.error(msg)
            raise TypeError(msg)

        self.branch = branch if branch is not None \
            else self.repo.git_get_active_branch()

        # remote branch? => read-only
        if self.branch.split('/')[0] in self.repo.git_get_remotes():
            self.is_read_only = True
        else:
            self.is_read_only = False

    def get_handles(self):
        """Get the metadata of all handles in `branch`.

        Returns
        -------
        dictionary of Handle

        """
        out = dict()

        # load handles from branch
        for key in self.repo.get_handle_list(self.branch):
            out[key] = CollectionRepoHandleBackend(self.repo, key, self.branch)
        return out

    def get_collection(self):
        """Get collection level metadata of a branch
        """
        # read standard files:
        cfg_str = '\n'.join(self.repo.git_get_file_content(REPO_CONFIG_FILE,
                                                           self.branch))
        std = Graph().parse(data=cfg_str, format="turtle")

        col_node = std.value(predicate=RDF.type, object=DLNS.Collection)
        col_name = std.value(subject=col_node, predicate=RDFS.label)

        # additional turtle files in collection's basedir:
        files = [file_ for file_ in self.repo.git_get_files(branch=self.branch)
                 if file_ == basename(file_) and file_ != REPO_CONFIG_FILE and
                 file_.endswith(".ttl")]

        out = Graph(identifier=col_name)  # avoid type 'URIRef' or sth.

        for file_ in files:
            file_str = '\n'.join(self.repo.git_get_file_content(file_,
                                                                self.branch))
            out.parse(data=file_str, format="turtle")

        # Note: By now we parse config.ttl and datalad.ttl two times here.
        # The issue is to determine the identifier of hte graph, which can't be
        # changed after creation. We probably also want to read certain files
        # only into the returned graph later on.

        return out

    def commit_collection(self, collection, msg):

        if self.is_read_only:
            raise RuntimeWarning("Can't commit remote collection.")

        if not isinstance(collection, Collection):
            raise TypeError("Can't save non-collection type: %s" %
                            type(collection))

        # save current branch ...
        current_branch = self.repo.git_get_active_branch()

        if self.branch != current_branch:
            # ... and switch to the one to be changed:
            self.repo.git_checkout(self.branch)

        # handle files we no longer have:
        files_to_remove = [f for f in self.repo.get_indexed_files()
                           if self.repo._filename2key(ops(f)[0]) not in
                           collection.keys()]

        self.repo.git_remove(files_to_remove)

        # update everything else to be safe
        files_to_add = []

        # collection level:
        collection.meta.serialize(opj(self.repo.path, REPO_STD_META_FILE),
                                  format="turtle")
        files_to_add.append(REPO_STD_META_FILE)

        # handles:
        for k, v in collection.iteritems():

            v.commit()
            # files_to_add.append(self.repo._key2filename(k))
            # Actually, this shouldn't be necessary, since it was
            # committed above. On the other hand, that's a lot of commits.
            # May be don't commit the handles but just write_to_file and commit
            # herein.

        self.repo.git_add(files_to_add)
        self.repo.git_commit(msg)

        if self.branch != current_branch:
            # switch back to repo's active branch on disk
            self.repo.git_checkout(current_branch)

    @property
    def url(self):
        if self.is_read_only:
            # remote repo:
            return self.repo.git_get_remote_url(self.branch.split('/')[0])
        else:
            # available repo:
            return self.repo.path