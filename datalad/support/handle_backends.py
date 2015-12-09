# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
Implements backends for handles.
"""
import logging

from rdflib import Graph, Literal, RDF, RDFS

from datalad.support.collectionrepo import CollectionRepo
from datalad.support.exceptions import ReadOnlyBackendError
from datalad.support.handle import Handle
from datalad.support.handlerepo import HandleRepo
from datalad.support.metadatahandler import DLNS
from datalad.utils import get_local_file_url

lgr = logging.getLogger('datalad.handle_backends')


# TODO: Both of the repo backends for handles share a lot of code.
# So, there probably should be a super class to contain that code and the sub
# classes just hold different paths and may be redirect some calls to
# differently named methods of the underlying repo.

class HandleRepoBackend(Handle):
    # TODO: Name. See corresponding naming for CollectionBackend and find
    # a solution for both of them
    """Handle backend using a handle repository.

    Implements a Handle pointing to a handle repository branch. Such a
    repository may contain several metadata files, storing parts of the entire
    graph. By default, all of these files are used, but you can limit it to the
    ones you need in order to save time and memory.
    These parts are represented in the attribute `sub_graphs`. Since it is a
    subclass of Handle, you can still access the entire graph by the
    attribute `meta`. But in case you need to store changes of the graph
    to the underlying repository, `sub_graphs` needs to be modified in order to
    know, what files to store the changes to. Therefore, while `meta` returns a
    rdflib.Graph, you cannot assign a Graph to it, but only a dict of Graph,
    which is in fact assigned to `sub_graphs`.
    """

    def __init__(self, repo, branch=None, files=None):
        """

        Parameters
        ----------
        repo: HandleRepo
            The handle repository, that contains the desired handle.
        branch: str
            The branch, that holds the desired handle. Naturally also allows
            for addressing remote branches.
            Default: Active branch of the repository.
        files: list of str
            Optionally restrict the metadata files to be represented by this
            instance. This does not only save memory due to a smaller graph,
            but also saves time for parsing the files and querying the graph.
        """

        super(HandleRepoBackend, self).__init__()

        if not isinstance(repo, HandleRepo):
            e_msg = "Can't deal with type %s to access a handle repository." \
                    % type(repo)
            lgr.error(e_msg)
            raise TypeError(e_msg)
        else:
            self.repo = repo

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
        self._sub_graphs = {}

    @property
    def name(self):
        return self.repo.name

    def get_subgraphs(self):
        if not self._sub_graphs:
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
        self._graph = Graph(identifier=Literal(self.name))
        for key in self.sub_graphs:
            self._graph += self.sub_graphs[key]

        return self._graph

    meta = property(get_metadata, set_metadata)

    def update_metadata(self):
        """

        :return:
        """
        self.sub_graphs = self.repo.get_metadata(self._files,
                                                 branch=self._branch)

    def commit_metadata(self, msg="Handle metadata updated."):
        """

        :param msg:
        :return:
        """
        if self.is_read_only:
            raise ReadOnlyBackendError("Can't commit to handle '%s'.\n"
                                       "(Repository: %s\tBranch: %s)" %
                                       (self.name, self.repo.path,
                                        self._branch))

        self.repo.set_metadata(self.sub_graphs, msg=msg, branch=self._branch)

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


    # TODO: set_name? See Handle.


class CollectionRepoHandleBackend(Handle):
    """Handle backend for collection repositories.

    Implements a Handle backend retrieving its data from a branch of a
    collection repository.
    """

    def __init__(self, repo, key, branch=None, files=None):
        """

        :param repo:
        :param key:
        :param branch:
        :param files:
        :return:
        """
        super(CollectionRepoHandleBackend, self).__init__()

        if not isinstance(repo, CollectionRepo):
            e_msg = "Can't deal with type %s to access " \
                    "a collection repository." % type(repo)
            lgr.error(e_msg)
            raise TypeError(e_msg)
        else:
            self.repo = repo

        if branch is None:
            self._branch = self.repo.git_get_active_branch()
        elif branch in self.repo.git_get_branches() + \
                self.repo.git_get_remote_branches():
            self._branch = branch
        else:
            raise ValueError("Unknown branch %s of repository at %s." %
                             (branch, self.repo.path))

        if key not in self.repo.get_handle_list(self._branch):
            raise ValueError("Unknown handle %s in branch %s of repository %s."
                             % (key, self._branch, self.repo.path))
        self._key = key

        # we can't write to a remote branch:
        self.is_read_only = self._branch.split('/')[0] in \
                            self.repo.git_get_remotes()

        self._files = files
        self._sub_graphs = dict()

    @property
    def name(self):
        return self._key

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
        self._graph = Graph(identifier=Literal(self._key))
        for key in self.sub_graphs:
            self._graph += self.sub_graphs[key]

        return self._graph

    meta = property(get_metadata, set_metadata)

    def update_metadata(self):
        self.sub_graphs = self.repo.get_handle_graphs(self._key,
                                                      branch=self._branch,
                                                      files=self._files)

    def commit_metadata(self, msg="Handle metadata updated."):
        if self.is_read_only:
            raise ReadOnlyBackendError("Can't commit to handle '%s'.\n"
                                       "(Repository: %s\tBranch: %s." %
                                       (self.name, self.repo.path,
                                        self._branch))

        self.repo.store_handle_graphs(self.sub_graphs, self._key,
                                      branch=self._branch, msg=msg)

    # TODO: set_name? See Handle.

    @property
    def url(self):
        return str(self.meta.value(predicate=RDF.type, object=DLNS.Handle))
        # TODO: DLNS.this? => path/url
        # Note: Shouldn't be possible to have DLNS.this from handle
        # WITHIN a collection!

        # TODO: Provide path/url without the need to load 'meta'?
        #       => explicitly from datalad or config
        #    or => from collection-level

        # git_remote_url? Nope. That would be a collection.


class RuntimeHandle(Handle):
    """Pure runtime Handle without a persistent backend.

    This kind of a handle can only be used as a "virtual" handle, that has no
    physical storage.

    Note: For now, there is no usecase.
    It serves as an example and a test case.
    """

    def __init__(self, name):
        super(RuntimeHandle, self).__init__()
        self._graph = Graph(identifier=Literal(name))
        self._graph.add((DLNS.this, RDF.type, DLNS.Handle))
        self._graph.add((DLNS.this, RDFS.label, Literal(name)))

    @property
    def url(self):
        return None

    def update_metadata(self):
        pass

    def commit_metadata(self, msg="Metadata updated."):
        raise ReadOnlyBackendError("Can't commit RuntimeHandle.")
