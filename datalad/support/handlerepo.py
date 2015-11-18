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

import logging
from os.path import join as opj, basename
from six import string_types

from rdflib import URIRef

#from datalad.support.handlebackends import HandleRepoBackend
from .annexrepo import AnnexRepo
from .metadatahandler import MetadataImporter, CustomImporter, Graph, \
    Literal, DLNS, RDFS
from ..consts import HANDLE_META_DIR, REPO_CONFIG_FILE, REPO_STD_META_FILE
from ..utils import assure_dir

lgr = logging.getLogger('datalad.handlerepo')


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
                 name=None, create=True, init=False):
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
                                         runner=runner, backend=backend,
                                         create=create, init=init)

        self.datalad_path = HANDLE_META_DIR
        self._cfg_file = opj(HANDLE_META_DIR, REPO_CONFIG_FILE)
        self._md_file = opj(HANDLE_META_DIR, REPO_STD_META_FILE)

        if create:
            assure_dir(self.path, HANDLE_META_DIR)

            importer = CustomImporter('Handle', 'Handle', DLNS.this)
            # load existing files:
            if self._cfg_file in self.get_indexed_files():
                importer.import_data(opj(self.path, self._cfg_file))
            if self._md_file in self.get_indexed_files():
                importer.import_data(opj(self.path, self._md_file))
            graphs = importer.get_graphs()

            # if there is no name statement, add it:
            if len([subj for subj in graphs[REPO_CONFIG_FILE[0:-4]].objects(
                    DLNS.this, RDFS.label)]) == 0:
                graphs[REPO_CONFIG_FILE[0:-4]].add(
                    (DLNS.this, RDFS.label,
                     Literal(name or basename(self.path))))

            importer.set_graphs(graphs)  # necessary?
            importer.store_data(opj(self.path, HANDLE_META_DIR))

            self.add_to_git([self._cfg_file, self._md_file],
                            "Initialized handle metadata.")

    def __repr__(self):
        return "<HandleRepo path=%s (%s)>" % (self.path, type(self))

    def _get_cfg(self):
        config_handler = CustomImporter('Handle', 'Handle', DLNS.this)
        config_handler.import_data(opj(self.path, self._cfg_file))
        return config_handler.get_graphs()[REPO_CONFIG_FILE[0:-4]]

    def _set_cfg(self, graph, commit_msg="Updated config file."):
        config_handler = CustomImporter('Handle', 'Handle', DLNS.this)
        graph_dict = dict()
        graph_dict[REPO_CONFIG_FILE[0:-4]] = graph
        config_handler.set_graphs(graph_dict)
        config_handler.store_data(opj(self.path, HANDLE_META_DIR))
        self.add_to_git(self._cfg_file, commit_msg)

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

    def get_handle(self, branch=None):
        """Convenience method to create a `Handle` instance.
        """
        return HandleRepoBackend(self, branch)

    def get_metadata(self, files=None, branch=None):
        """Get a Graph containing the handle's metadata

        Parameters
        ----------
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
            files = opj(self.path, HANDLE_META_DIR)
        else:
            files = [opj(self.path, HANDLE_META_DIR, f) for f in files]

        handler = CustomImporter('Handle', 'Handle', DLNS.this)

        handler.import_data(files)
        graphs = handler.get_graphs()

        # joined_graph = Graph(identifier=self.name)
        # for key in graphs:
        #     joined_graph += graphs[key]
        return graphs

    def set_metadata(self, graphs, msg="Metadata saved.", branch=None):
        """

        :param graphs:
        :param msg:
        :param branch:
        :return:
        """

        if not isinstance(graphs, dict):
            raise TypeError("Unexpected type of parameter 'graphs' (%s). "
                            "Expected: dict." % type(graphs))

        files = dict()
        for key in graphs:
            if not isinstance(graphs[key], Graph):
                raise TypeError("Wrong type of graphs['%s'] (%s). "
                                "Expected: Graph." % (key, type(graphs[key])))

            files[key] = opj(self.path, HANDLE_META_DIR, key + ".ttl")

        active_branch = self.git_get_active_branch()
        if branch is None:
            branch = active_branch
        elif branch not in self.git_get_branches():
            raise ValueError("Unknown branch '%s'." % branch)
        else:
            self.git_checkout(branch)

        for key in graphs:
            graphs[key].serialize(files[key], format="turtle")

        self.add_to_git(files.values(), msg)

        if branch != active_branch:
            self.git_checkout(active_branch)

    def import_metadata(self, importer, files=None, data=None,
                        about_uri=DLNS.this):
        """Imports metadata to the datalad-conform metadata representation
        of the handle.

        Expects either `files` or `data` to be not `None`.

        Parameters
        ----------
        importer: class
          the importer to be used; has to be a subclass of MetadataImporter
        files: str or list of str
          either a path to the file or directory to be imported or a list
          containing paths to the files.
        data: dict of list of str
          a dictionary containing the metadata to be imported. The key is
          expected to be the file name and the value its content as a list of
          the file's lines as returned by `readlines()`.
        about_uri: URIRef
          uri of the entity the metadata is about. By default it's the handle
          itself.
        """

        if not issubclass(importer, MetadataImporter):
            raise TypeError("Not a MetadataImporter: " + str(importer))

        # TODO: check whether cfg-file even exists, otherwise create a basic one.
        cfg_graph = Graph().parse(opj(self.path, HANDLE_META_DIR,
                                      REPO_CONFIG_FILE),
                                  format="turtle")

        # check for existing metadata sources to determine the name for the
        # new one:
        # TODO: the numbering is shit ;) Use a hash or sth.
        src_name = "%s_import%d" % (self.name,
                                    len([src for src in
                                         cfg_graph.objects(about_uri,
                                                               DLNS.usesSrc)])
                                    + 1)

        # graph containing just new config statements:
        cfg_graph_new = Graph()

        if files is not None and data is None:
            # treat it as a metadata source, that can be used again later on.
            src_node = URIRef(src_name)
            # add config-entries for that source:
            cfg_graph_new.add((about_uri, DLNS.usesSrc, src_node))
            if isinstance(files, string_types):
                cfg_graph_new.add((src_node, DLNS.usesFile, URIRef(files)))
            elif isinstance(files, list):
                [cfg_graph_new.add((src_node, DLNS.usesFile, URIRef(f)))
                 for f in files]

        elif files is None and data is not None:
            # just metadata to read, nothing we can refer to later on
            pass
        else:
            raise ValueError("Either 'files' or 'data' have to be passed.")

        im = importer(target_class='Handle', about_class='Handle',
                      about_uri=about_uri)
        im.import_data(files=files, data=data)

        # add new config statements:
        im.get_graphs()[REPO_CONFIG_FILE[:-4]] += cfg_graph + cfg_graph_new
        # create import branch:
        active_branch = self.git_get_active_branch()
        self.git_checkout(name=src_name, options='-b')

        im.store_data(opj(self.path, HANDLE_META_DIR))

        self.add_to_git(opj(self.path, HANDLE_META_DIR))

        # switching back and merge:
        # Note: -f used for the same reason as in remove_handle
        # TODO: Check this out
        self.git_checkout(active_branch, options="-f")
        self.git_merge(src_name)
