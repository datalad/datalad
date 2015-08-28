# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
Implements a datalad handle repository.

This layer makes the difference between an arbitrary annex and a
datalad-managed dataset.
"""
# TODO: where to document definition of a valid handle?
# - Annex
# - .datalad directory:
#   - handle.cfg
#   - metadata file(s)

import os
from os.path import join as opj, exists, basename
import logging

from rdflib import URIRef, RDF

from .annexrepo import AnnexRepo
from .metadatahandler import CustomImporter, Graph, Literal, DLNS, RDFS
from .handle import HandleBackend, Handle
from ..utils import assure_dir

lgr = logging.getLogger('datalad.handlerepo')


class HandleRepoBackend(HandleBackend):
    # TODO: Name. See corresponding naming for CollectionBackend and find
    # a solution for both of them
    """HandleBackend for handle repositories.

    Implements a HandleBackend pointing to a handle repository branch.
    """

    # TODO: Currently the branch is always the active branch of the handle.
    # So, the branch-option of the constructor has no effect and is just a
    # placeholder, serving as a reminder. Implementing it may be involves some
    # changes in the HandleRepo-class, so it's returning infos from the
    # branch's config file.

    def __init__(self, repo, branch=None):

        if not isinstance(repo, HandleRepo):
            e_msg = "Can't deal with type '%s' to access a handle repository." \
                    % type(repo)
            lgr.error(e_msg)
            raise TypeError(e_msg)
        else:
            self._repo = repo

        self._branch = branch or self._repo.git_get_active_branch()

    @property
    def url(self):
        return self._repo.path

    def get_name(self):
        return self._repo.name

    def set_name(self, name):
        self._repo.name = name

    name = property(get_name, set_name)

    def get_metadata(self, files=None):
        return self._repo.get_metadata(files)

    def set_metadata(self, meta, msg=None):
        self._repo.set_metadata(meta, msg)

    metadata = property(get_metadata, set_metadata)


class HandleRepo(AnnexRepo):
    """Representation of a handle repository.

    This is to be used, if you have to perform operations on the repository
    rather than just a handle's metadata. Otherwise use `Handle` instead of
    `HandleRepo`. Keep in mind, that a repository can have several branches,
    each in fact representing a dataset.
    Implementations of datalad commands are supposed to use this rather than
    AnnexRepo or GitRepo directly, since any restrictions on annexes required
    by datalad due to its cross-platform distribution approach are handled
    within this class. Also an AnnexRepo has no idea of any datalad
    configuration needs, of course.
    """

    def __init__(self, path, url=None, direct=False, runner=None, backend=None,
                 name=None):
        """Creates a dataset representation from path.

        If `path` is empty, it creates an new repository.
        If `url` is given, it is expected to point to a git repository to
        create a clone from.

        Parameters
        ----------
        path : str
          path to repository
        url: str
          url to the to-be-cloned repository. Valid git url according to
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS
          required.
        direct: bool
          if True, force git-annex to operate in direct mode
        runner: Runner
        backend: str
        name: str
        """
        # TODO: More doc.

        super(HandleRepo, self).__init__(path, url, direct=direct,
                                         runner=runner, backend=backend)

        self.datalad_path = '.datalad'
        assure_dir(self.path, self.datalad_path)
        self._cfg_file = opj(self.datalad_path, 'config.ttl')
        self._md_file = opj(self.datalad_path, 'datalad.ttl')

        importer = CustomImporter('Handle', 'Handle', DLNS.this)
        # load existing files:
        if self._cfg_file in self.get_indexed_files():
            importer.import_data(opj(self.path, self._cfg_file))
        if self._md_file in self.get_indexed_files():
            importer.import_data(opj(self.path, self._md_file))
        graphs = importer.get_graphs()

        # collection settings:
        # if there is no name statement, add it:
        if len([subj for subj in graphs['config'].objects(DLNS.this,
                                                          RDFS.label)]) == 0:
            graphs['config'].add((DLNS.this, RDFS.label,
                                  Literal(name or basename(self.path))))

        importer.set_graphs(graphs)  # necessary?
        importer.store_data(opj(self.path, self.datalad_path))
        # TODO: How do we know something has changed?
        # => check git status?
        self.add_to_git([self._cfg_file, self._md_file],
                        "Initialized config file.")

    def _get_cfg(self):
        config_handler = CustomImporter('Handle', 'Handle', DLNS.this)
        config_handler.import_data(opj(self.path, self._cfg_file))
        return config_handler.get_graphs()['config']

    def _set_cfg(self, graph, commit_msg="Updated config file."):
        config_handler = CustomImporter('Handle', 'Handle', DLNS.this)
        graph_dict = dict()
        graph_dict['config'] = graph
        config_handler.set_graphs(graph_dict)
        config_handler.store_data(opj(self.path, self.datalad_path))
        self.add_to_git(self._cfg_file, commit_msg)

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        Note: There is a second meaning of 'equal' handles, meaning that
        they have the same datalad id. However, at the level of instances of
        this class, 'equal' means, that the both of them are representing the
        very same repository.
        """
        # TODO: Move this to GitRepo, since it is true for all the repositories
        return self.path == obj.path

    # TODO: Consider using preferred label for the name
    def get_name(self):
        return str(self._get_cfg().value(subject=DLNS.this,
                                         predicate=RDFS.label))

    def set_name(self, name):
        graph = self._get_cfg()
        for old_name in graph.objects(DLNS.this, RDFS.label):
            graph.remove((DLNS.this, RDFS.label, old_name))
        graph.add((DLNS.this, RDFS.label, Literal(name)))
        self._set_cfg(graph, "Changed name.")

    name = property(get_name, set_name)

    @property
    def datalad_id(self):
        """Get the datalad identifier of the handle.

        This is a read-only property.

        Returns
        -------
        str
        """
        raise NotImplementedError("datalad id not used anymore")

    def get(self, files):
        """get the actual content of files

        This command gets the actual content of the files in `list`.
        """
        self.annex_get(files)

    def _commit(self, msg):
        """Commit changes to repository

        Parameters:
        -----------
        msg: str
            commit-message
        """

        if self.is_direct_mode():
            self.annex_proxy('git commit -m "%s"' % msg)
        else:
            self.git_commit(msg)

    def add_to_annex(self, files, commit_msg="Added file(s) to annex."):
        """Add file(s) to the annex.

        Adds files to the annex and commits.

        Parameters
        ----------
        commit_msg: str
            commit message
        files: list
            list of paths to add to the annex; Can also be a str, in case of a
            single path.
        """

        self.annex_add(files)
        self._commit(commit_msg)

    def add_to_git(self, files, commit_msg="Added file(s) to git."):
        """Add file(s) directly to git

        Adds files directly to git and commits.

        Parameters
        ----------
        commit_msg: str
            commit message
        files: list
            list of paths to add to git; Can also be a str, in case of a single
            path.
        """
        self.annex_add_to_git(files)
        self._commit(commit_msg)

    def get_handle(self, branch=None):
        """Convenience method to create a `Handle` instance.
        """
        return Handle(HandleRepoBackend(self, branch))

    def get_metadata(self, files=None):
        """Get a Graph containing the handle's metadata

        Parameters:
        -----------
        files: list of str
            metadata files within the datalad directory of the handle to
            be read. Default: All files are read.
        """
        # Parameter? May be by default get graph of all files, just some of
        # them otherwise. But how to save then?
        # Just don't save at all (Exception)?
        # Or datalad.ttl + additional.ttl, regardless of where metadata
        # came from?
        # Is there some "in namespace" check in rdflib? => what to save to
        # datalad.ttl ==> str.startswith(ns) or URIRef.startswith(ns)

        if files is None:
            files = opj(self.path, self.datalad_path)
        else:
            files = [opj(self.path, self.datalad_path, f) for f in files]

        handler = CustomImporter('Handle', 'Handle', DLNS.this)

        handler.import_data(files)
        graphs = handler.get_graphs()
        joined_graph = Graph(identifier=self.name)
        for key in graphs:
            joined_graph += graphs[key]
        return joined_graph

    def set_metadata(self, graph, msg="Metadata saved."):
        raise NotImplementedError