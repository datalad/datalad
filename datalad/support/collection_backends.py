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
from six import string_types, iterkeys

from rdflib import Graph, Literal, RDF, RDFS

from datalad.support.collection import Collection
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.handle_backends import CollectionRepoHandleBackend
from datalad.support.metadatahandler import DLNS
from datalad.support.exceptions import ReadOnlyBackendError
from datalad.utils import get_local_file_url

lgr = logging.getLogger('datalad.collectionbackends')


class CollectionRepoBackend(Collection):

    def __init__(self, repo, branch=None, files=None):

        super(CollectionRepoBackend, self).__init__()

        if isinstance(repo, CollectionRepo):
            self.repo = repo
        elif isinstance(repo, string_types):
            # TODO: create=??? let it be an option?
            self.repo = CollectionRepo(repo, create=False)
        else:
            msg = "Invalid repo type: %s" % type(repo)
            lgr.error(msg)
            raise TypeError(msg)

        if branch is None:
            self._branch = self.repo.git_get_active_branch()
        elif branch in self.repo.git_get_branches() + \
                self.repo.git_get_remote_branches():
            self._branch = branch
        else:
            raise ValueError("Unknown branch '%s' of repository at %s." %
                             (branch, self.repo.path))

        # we can't write to a remote branch:
        if self._branch.split('/')[0] in self.repo.git_get_remotes():
            self._remote = self._branch.split('/')[0]
            self.is_read_only = True
        else:
            self._remote = None
            self.is_read_only = False

        self._files = files
        self._sub_graphs = dict()

        self.reload()

    @property
    def branch(self):
        # Read only
        return self._branch

    @property
    def remote(self):
        # Read only
        return self._remote

    def __eq__(self, other):
        raise NotImplementedError("TODO")

    def get_subgraphs(self):
        if self._sub_graphs == dict():
            self.update_metadata()
        return self._sub_graphs

    def set_subgraphs(self, graphs):
        if not isinstance(graphs, dict):
            raise TypeError("Unexpected type of data: %s. "
                            "Expects a dictionary of sub-graphs." %
                            type(graphs))
        for subgraph in graphs:
            if not isinstance(graphs[subgraph], Graph):
                raise TypeError("Sub-graph '%s' is of type %s. "
                                "Expected: rdflib.Graph." %
                                (subgraph, type(graphs[subgraph])))
            self._sub_graphs[subgraph] = graphs[subgraph]
        self.notify_update_listeners(self.meta)

    sub_graphs = property(get_subgraphs, set_subgraphs)

    def set_metadata(self, data):
        """

        :param data: dict of Graph
        :return:
        """
        self.sub_graphs = data

    def get_metadata(self):
        """

        :return:
        """
        self._graph = Graph(identifier=Literal(self.name),
                            store=self.store)
        for key in self.sub_graphs:
            self._graph += self.sub_graphs[key]

        return self._graph

    meta = property(get_metadata, set_metadata)

    @property
    def name(self):
        # TODO: Reconsider naming (also for Handles)
        return self.remote or self.repo.name

    @property
    def url(self):
        """

        :return:
        """
        if self._remote is not None:
            # TODO: In case of local FS remote,
            # currently returns the path not according to file-scheme
            return self.repo.git_get_remote_url(self._remote)
        else:
            return get_local_file_url(self.repo.path)

    def update_metadata(self):
        """

        :return:
        """
        self.sub_graphs = self.repo.get_collection_graphs(branch=self._branch,
                                                          files=self._files)

        # creation of self.meta needs to be triggered in order to be up to date
        # in the collections graph store. Furthermore, returning the updated
        # graph might be reasonable anyway.
        return self.meta

    def commit_metadata(self, msg="Collection metadata updated."):
        """

        :param msg:
        :return:
        """
        if self.is_read_only:
            raise ReadOnlyBackendError("Can't commit to collection '%s'.\n"
                                       "(Repository: %s\tBranch: %s)" %
                                       (self.name, self.repo.path,
                                        self._branch))

        self.repo.set_collection_graphs(self.sub_graphs, branch=self._branch,
                                        msg=msg)

    def commit(self, msg="Collection updated."):
        # commit not just collection metadata, but any changes to the
        # collection (handle list, handles' meta, ...)
        raise NotImplementedError("TODO")

    def reload(self):
        # self.update_metadata()
        # TODO: update_metadata? lazy! instead reset sub_graphs?
        self._sub_graphs = dict()
        self.clear()
        # TODO: clean store?

        # load handle list:
        for handle_name in self.repo.get_handle_list(self._branch):
            self.register_handle(CollectionRepoHandleBackend(self.repo,
                                                             handle_name,
                                                             self._branch),
                                 add_handle_uri=False)

        # TODO: new update signal, that allows for reading the empty graphs
        # without triggering loading and read possibly new handle list?


    # TODO: name from repo? => not, if CollectionRepo melted in!
    # TODO: set_name? See Handle.
    # TODO: setitem (+ delitem?)

############################# from old backend:
#
#     def commit_collection(self, collection, msg):
#
#         if self.is_read_only:
#             raise RuntimeWarning("Can't commit remote collection.")
#
#         if not isinstance(collection, Collection):
#             raise TypeError("Can't save non-collection type: %s" %
#                             type(collection))
#
#         # save current branch ...
#         current_branch = self.repo.git_get_active_branch()
#
#         if self.branch != current_branch:
#             # ... and switch to the one to be changed:
#             self.repo.git_checkout(self.branch)
#
#         # handle files we no longer have:
#         files_to_remove = [f for f in self.repo.get_indexed_files()
#                            if self.repo._filename2key(ops(f)[0]) not in
#                            collection.keys()]
#
#         self.repo.git_remove(files_to_remove)
#
#         # update everything else to be safe
#         files_to_add = []
#
#         # collection level:
#         collection.meta.serialize(opj(self.repo.path, REPO_STD_META_FILE),
#                                   format="turtle")
#         files_to_add.append(REPO_STD_META_FILE)
#
#         # handles:
#         for k, v in collection.iteritems():
#
#             v.commit()
#             # files_to_add.append(self.repo._key2filename(k))
#             # Actually, this shouldn't be necessary, since it was
#             # committed above. On the other hand, that's a lot of commits.
#             # May be don't commit the handles but just write_to_file and commit
#             # herein.
#
#         self.repo.git_add(files_to_add)
#         self.repo.git_commit(msg)
#
#         if self.branch != current_branch:
#             # switch back to repo's active branch on disk
#             self.repo.git_checkout(current_branch)


class RuntimeCollection(Collection):

    def __init__(self, name):
        super(RuntimeCollection, self).__init__()
        self._graph = Graph(identifier=Literal(name), store=self.store)
        self._graph.add((DLNS.this, RDF.type, DLNS.Collection))
        self._graph.add((DLNS.this, RDFS.label, Literal(name)))

    def __eq__(self, other):
        return self.keys() == other.keys() and self.name == other.name  \
               and all([self[k] == other[k] for k in self.keys()])

    @property
    def url(self):
        return None

    def update_metadata(self):
        pass

    def commit(self, msg="Collection updated."):
        raise ReadOnlyBackendError("Can't commit RuntimeHandle.")

    # TODO: set_name? See Handle.
    # TODO: setitem (+ delitem?)
