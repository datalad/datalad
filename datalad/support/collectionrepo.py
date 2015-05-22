# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Implements datalad collection repositories.
"""

import re
import logging
from os.path import join as opj, basename

from rdflib import Graph

from .gitrepo import GitRepo, _remove_empty_items
from .handlerepo import HandleRepo
from .handle import Handle, HandleBackend
from .exceptions import CollectionBrokenError
from .metadatahandler import DLNS
from .collection import Collection, CollectionBackend

lgr = logging.getLogger('datalad.collectionrepo')


class CollectionRepoBranchHandleBackend(HandleBackend):
    """HandleBackend for collection repositories.

    Implements a HandleBackend retrieving its data from a branch of a
    collection repository. This is a read-only backend for Handle.
    """
    # TODO: raise proper Exceptions on write access
    # TODO: Better name of these classes

    def __init__(self, repo, branch, key):
        self.repo = repo
        self.branch = branch
        self.key = key
        self.cache = dict()
        self.update()

    def update(self):
        """Reloads data from git.

        Calls to backend interface methods return cached data.
        TODO: Maybe make an explicit update() mandatory for backends.
        """
        for line in self.repo.git_get_file_content(
                self.repo._key2filename(self.key),
                self.branch):
            if line.startswith("handle_id = "):
                self.cache['id'] = line[12:]
            elif line.startswith("last_seen = "):
                self.cache['url'] = line[12:]
            else:
                pass

        self.cache['meta'] = Graph(identifier=self.key).parse(
            self.repo.git_get_file_content(
                opj('metadata/', self.repo._key2filename(self.key)),
                self.branch))

    @property
    def id(self):
        return self.cache['id']

    @property
    def url(self):
        return self.cache['url']

    def get_name(self):
        return self.key

    def set_name(self, name):
        lgr.warning("Can't write handle data from within %s" +
                    str(self.__class__))

    name = property(get_name, set_name)

    def get_metadata(self):
        return self.cache['meta']

    def set_metadata(self, meta):
        lgr.warning("Can't write handle data from within %s" +
                    str(self.__class__))

    metadata = property(get_metadata, set_metadata)


class CollectionRepoBranchBackend(CollectionBackend):
    """CollectionBackend for collection repositories.

    Implements a CollectionBackend that is connected to a branch of collection
    repository.
    """
    # TODO: Better name

    # Note (reminder): If it's a remote branch: Should writing data imply a
    # push or sth.?
    # Probably not, but it should it be well documented, since 'saving' a
    # collection with a remote url and then it's just locally done, could be
    # confusing to users not familiar with git.

    def __init__(self, repo, branch=None):
        """
        Parameters:
        -----------
        repo: CollectionRepo or str
          in case of a string it's interpreted as being the path to the
          repository in question.
        branch: str
        """
        if isinstance(repo, CollectionRepo):
            self.repo = repo
        elif isinstance(repo, basestring):
            self.repo = CollectionRepo(repo)
        else:
            msg = "Invalid repo type: %s" % type(repo)
            lgr.error(msg)
            raise TypeError(msg)

        self.branch = branch

    def get_handles(self):
        return self.repo.get_handles(self.branch)

    def get_collection(self):
        return self.repo.get_collection(self.branch)

    def commit_collection(self, collection, msg):
        self.repo.commit_collection(collection, self.branch, msg)


class CollectionRepo(GitRepo):
    """Representation of a datalad collection repository.

    A Collection is represented as a git-repository containing:
        a) a file named 'collection', which stores metadata of the collection
           itself, and
        b) one file per handle, storing the metadata of each handle

    Attention: files are valid only if in git.
    Being present is not sufficient!
    """

    # TODO: Change to two files per handle/collection:
    # 'collection' and ${key2filename} with ids, names, default layout
    # and a directory 'metadatacache' containing, again, one file per each item

    # TODO: collection level metadata; include statement
    # (self.get_uri_ref(), RDF.type, DLNS.Collection)
    # But: get_uri_ref: How to distinct branches? Just '/branch'?
    # Note: This may change the layout within a collection:
    # dedicated directory for collection level metadata and additionally a
    # directory for the metadata cache.

    # TODO: instead of writing own plain text, just use ConfigParser

    __slots__ = GitRepo.__slots__ + ['name']

    def __init__(self, path, url=None, name=None, runner=None):
        """

        Parameters:
        -----------
        path: str
          path to git repository. In case it's not an absolute path, it's
          relative to os.getcwd()

        url: str
          url to the to-be-cloned repository. Requires valid git url
          according to
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .

        name: str
          optional name of the collection. This is only used for creating new
          collections. If there is a collection repo at path already, `name`
          is ignored.

        Raises:
        -------
        CollectionBrokenError
        """

        super(CollectionRepo, self).__init__(path, url, runner=runner)

        if not self.get_indexed_files():
            # it's a brand new collection repo.

            # default name is the name of the directory, this repository is
            # located in.
            self.name = name if name else basename(self.path)

            # create collection file
            # How to name that file? For now just 'collection'
            #  generally contains:
            #   - default layout on filesystem?
            #     (Q: implicitly requires a list of handles?
            #      This would give an additional consistency check)
            with open(opj(self.path, 'collection'), 'w') as f:
                f.write("name = %s" % self.name)
            self.git_add('collection')
            self.git_commit("Collection initialized.")

        elif 'collection' not in self.get_indexed_files():
            raise CollectionBrokenError("Missing file: 'collection'.")

        else:
            # may be read the collection file/handle infos
            # or may be do it on demand?
            with open(opj(self.path, 'collection'), 'r') as f:
                self.name = f.readline()[7:]

            # For now read a list of handles' names, ids, paths and metadata
            # as a proof of concept:
            # self._update_handle_data()

    # ### helper functions:

    def _filename2key(self, fname, branch):
        """Placeholder

        For now just returns input.
        """

        return self.name + '/' + branch + '/' + fname

    def _key2filename(self, key):
        """Placeholder

        For now just returns input.
        """
        # TODO: Rethink whether ignoring the collection/branch part
        # is appropriate herein.
        return _remove_empty_items(key.split('/'))[-1:][0]

    # ### ############################# ###

    def get_remotes_data(self, name=None):
        """Get the metadata of all remotes.

        Returns:
        --------
        dictionary
        """

        remotes = dict()

        # TODO: name! None->all

        for remote in self.git_get_remotes():
            remote_dict = remotes.get(remote, {})
            head_branch = None
            for remote_branch in self.git_get_remote_branches():
                head = re.findall(r'-> (.*)', remote_branch)

                if len(head):
                    # found the HEAD pointer
                    head_branch = head[0]
                    continue

                # TODO: By now these branches are named 'remote/branch';
                # correct for get_handles_data, but not in dict-representation,
                # so split and integrate outer loop.
                remote_dict[remote_branch] = \
                    self.get_handles_data(remote_branch)
            # Add entry 'HEAD':
            remote_dict['HEAD'] = remote_dict[head_branch]
            remotes[remote] = remote_dict

        return remotes


    def add_handle(self, handle, name=None):
        """Adds a handle to the collection repository.

        Parameters:
        -----------
        handle: HandleRepo
          For now, this has to be a locally available handle.
        name: str
          name of the handle. This is required to be unique with respect to the
          collection.
        """

        # default name of the handle:
        if not name:
            name = basename(handle.path)

        # Writing plain text for now. This is supposed to change to use
        # rdflib or sth.
        with open(opj(self.path, self._key2filename(name)), 'w') as f:
            f.write("handle_id = %s\n" % handle.datalad_id)
            f.write("last_seen = %s\n" % handle.path)
            f.write("metadata = %s\n" % handle.get_metadata().serialize())
            # what else? maybe default view or sth.

        # TODO: write to collection file:
        # entry for default layout?

        self.git_add(name)
        self.git_commit("Add handle %s." % name)

    def remove_handle(self, key):

        # TODO: also accept a HandleRepo instead of a name
        # TODO: remove stuff from collection file (if there is going to be any)
        self.git_remove(self._key2filename(key))
        self.git_commit("Removed handle %s." % key)

    def get_handle_repos(self):
        handles_data = self.get_handles_data()
        return [HandleRepo(handles_data[x][1]) for x in handles_data]

    def get_handle_repo(self, name):
        return HandleRepo(self.get_handles_data()[name][1])

    # Reintroduce:
    # TODO: Delay and wait for checking rdflib
    def update_meta_data_cache(self, handle):

        # TODO: All handles?

        # if isinstance(handle, basestring):
        #     key = handle
        # elif isinstance(handle, HandleRepo):
        #     key = handle.name
        # else:
        #     raise TypeError("can't update from handle given by %s (%s)." %
        #                     (handle, type(handle)))


        # with open(opj(self.path, self._key2filename(handle)), 'w') as f:

        pass

    # ### Implementation of collection backend:

    def get_collection(self, branch=None):
        """Get collection level metadata of a branch
        """
        out = dict()
        if branch is None:
            branch = self.git_get_active_branch()
        out['name'] = self.name + '/' + branch
        out['meta'] = Graph(identifier=out['name']).parse(
            self.git_get_file_content(opj('metadata', 'collection'), branch))

        return out

    def get_handles(self, branch=None):
        """Get the metadata of all handles in `branch`.

        Returns:
        --------
        dictionary of Handle

        """
        out = dict()
        if branch is None:
            branch = self.git_get_active_branch()

        # load handles from branch
        for filename in self.git_get_files(branch):
            if filename != 'collection':
                out[self._filename2key(filename)] = \
                    Handle(src=CollectionRepoBranchHandleBackend(
                        self, branch, self._filename2key(filename)))
        return out

    def commit_collection(self, collection, branch=None,
                          msg="Collection saved."):

        if not isinstance(collection, Collection):
            raise TypeError("Can't save non-collection type: %s" %
                            type(collection))

        # save current branch ...
        current_branch = self.git_get_active_branch()

        if branch is None:
            branch = current_branch

        if branch != current_branch:
            # ... and switch to the one to be changed:
            self.git_checkout(branch)

        # handle we no longer have
        no_more = set(self.get_indexed_files()).difference(
            [self._key2filename(k) for k in collection.keys()])
        for gone in no_more:
            # collection meta data is treated differently
            # TODO: Actually collection meta data isn't treated yet at all!
            # => rewrite file 'collection'
            if gone != 'collection':
                self.git_remove(gone)

        # update everything else to be safe
        files_to_add = []
        for k, v in collection.iteritems():
            with open(opj(self.path, self._key2filename(k)), 'w') as ofile:
                ofile.write('\n'.join(['%s = %s' % (cat, val)
                                      for cat, val in (('handle_id', v.id),
                                                       ('last_seen', v.url))]))
            files_to_add.append(self._key2filename(k))
            # write metadata cache:
            meta_file = opj(self.path, 'metadata', self._key2filename(k))
            v.meta.serialize(meta_file, format="turtle")
            files_to_add.append(meta_file)

        # write collection files:
        with open(opj(self.path, 'collection'), 'w') as f:
            f.write("name = " + collection.name)
        files_to_add.append(opj(self.path, 'collection'))
        collection.meta.serialize(opj(self.path, 'metadata', 'collection'),
                                  format="turtle")
        files_to_add.append(opj(self.path, 'metadata', 'collection'))

        self.git_add(files_to_add)
        self.git_commit(msg)

        if branch != current_branch:
            # switch back to repo's active branch on disk
            self.git_checkout(current_branch)

    def get_backend_from_branch(self, branch=None):
        """Convenience function to get a backend from a branch of this repo.

        By default a backend to the active branch is returned.
        """
        if branch is None:
            branch = self.git_get_active_branch()
        return CollectionRepoBranchBackend(self, branch)

