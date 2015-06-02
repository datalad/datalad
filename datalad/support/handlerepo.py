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
from ConfigParser import SafeConfigParser

from rdflib import URIRef, RDF

from .annexrepo import AnnexRepo
from .metadatahandler import MetadataHandler, DefaultHandler, DLNS
from .handle import HandleBackend, Handle
from ..utils import assure_dir

lgr = logging.getLogger('datalad.handlerepo')


class HandleRepoBranchBackend(HandleBackend):
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
    def id(self):
        return self._repo.datalad_id

    @property
    def url(self):
        return self._repo.path

    def get_name(self):
        return self._repo.name

    def set_name(self, name):
        self._repo.name = name
        # TODO: By now, this is not written to file.

    name = property(get_name, set_name)

    def get_metadata(self):
        return self._repo.get_metadata()

    def set_metadata(self, meta):
        self._repo.set_metadata(meta)

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
        self._cfg_file = opj(self.datalad_path, 'handle.cfg')

    def _initialize_config(self, name):

        assure_dir(self.path, self.datalad_path)
        cfg_parser = SafeConfigParser()

        # ignore config file, if it's not in git:
        if self._cfg_file in self.get_indexed_files():
            cfg_parser.read(opj(self.path, self._cfg_file))

        # Read configuration as far as it is available already.
        # Set defaults, wherever there's nothing available.
        if not cfg_parser.has_section('Handle'):
            cfg_parser.add_section('Handle')
        # By now, the datalad id is the uuid of the original annex that handle
        # was created from. Since that config file is added to git, the id is
        # kept, whenever the repository is cloned.
        # Note: Not sure yet, whether this is needed at all.
        if not cfg_parser.has_option('Handle', 'id'):
            cfg_parser.set('Handle', 'id',
                           self.repo.config_reader().get_value("annex", "uuid"))
        # Constructors parameter 'name' has priority to be used with this
        # instance as well as to be used as default name, if there is no
        # default name in config file already. If nothing is available at all,
        # the repository's name in the filesystem is used as default.
        if not cfg_parser.has_option('Handle', 'name'):
            cfg_parser.set('Handle', 'name', name or basename(self.path))

        # By now, we distinguish between metadata explicitly supported by
        # datalad (option 'standard') in order to ease queries, and additional,
        # metadata (option 'custom'), that takes more effort to query.
        # However, this distinction is done inside the handler.
        # TODO: As soon as we are sure about this, have better documentation.
        # Note: This comment is outdated but kept as a reminder. To be replaced.

        if not cfg_parser.has_section('Metadata'):
            cfg_parser.add_section('Metadata')
        if not cfg_parser.has_option('Metadata', 'handler'):
            cfg_parser.set('Metadata', 'handler', 'DefaultHandler')
        if not cfg_parser.has_option('Metadata', 'path'):
            cfg_parser.set('Metadata', 'path', 'metadata')
        assure_dir(self.path, cfg_parser.get('Metadata', 'path'))

        with open(opj(self.path, self._cfg_file), 'w') as f:
            cfg_parser.write(f)
        self.git_add(self._cfg_file)
        self.git_commit("Initialized config file.")

    def _get_cfg(self, section, option):
        parser = SafeConfigParser()
        parser.read(opj(self.path, self._cfg_file))
        return parser.get(section, option)

    def _set_cfg(self, section, option, value):
        filename = opj(self.path, self._cfg_file)
        parser = SafeConfigParser()
        parser.read(filename)
        parser.set(section, option, value)
        with open(filename, 'w') as f:
            parser.write(f)
        self.git_add(self._cfg_file)
        self.git_commit("Updated config file.")


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

    def get_name(self):
        return self._get_cfg('Handle', 'name')

    def set_name(self, name):
        self._set_cfg('Handle', 'name', name)

    name = property(get_name, set_name)

    @property
    def datalad_id(self):
        """Get the datalad identifier of the handle.

        This is a read-only property.

        Returns
        -------
        str
        """
        return self._get_cfg('Handle', 'id')

    def set_metadata_handler(self, handler=DefaultHandler):
        """
        std: subclass of MetadataHandler
        custom: subclass of MetadataHandler
        """
        if not issubclass(handler, MetadataHandler):
            raise TypeError("%s is not a MetadataHandler." % type(handler))

        self._set_cfg('Metadata', 'handler', handler.__name__)

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

    def get_metadata(self):
        """Get the metadata of a handle.

        Returns:
        --------
        rdflib.Graph
        """
        name = self._get_cfg('Metadata', 'handler')
        self_node = URIRef(self.path)
        import datalad.support.metadatahandler as mdh
        try:
            handler = getattr(mdh, name)(opj(self.path,
                                             self._get_cfg('Metadata', 'path')),
                                         self_node)
        except AttributeError:
            lgr.error("'%s' is an unknown metadata handler." % name)
            raise ValueError("'%s' is an unknown metadata handler." % name)

        meta = handler.get_graph(identifier=self.name)

        # Add datalad statement:
        meta.add((self_node, RDF.type, DLNS.Handle))
        return meta

    def set_metadata(self, meta):
        """Write the metadata of a handle.

        Parameters:
        -----------
        meta: rdflib.Graph
        """
        name = self._get_cfg('Metadata', 'handler')
        import datalad.support.metadatahandler as mdh
        try:
            handler = getattr(mdh, name)(opj(self.path,
                                             self._get_cfg('Metadata', 'path')))
        except AttributeError:
            lgr.error("'%s' is an unknown metadata handler." % name)
            raise ValueError("'%s' is an unknown metadata handler." % name)

        handler.set(meta)
        self.add_to_git(opj(self._get_cfg('Metadata', 'path'), '*'),
                        "Metadata updated.")

    def get_handle(self, branch=None):
        """Convenience method to create a `Handle` instance.
        """
        return Handle(HandleRepoBranchBackend(self, branch))