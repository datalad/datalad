# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
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


from annexrepo import AnnexRepo
from .metadatahandler import MetadataHandler, DefaultHandler

lgr = logging.getLogger('datalad.dataset')


class Handle(AnnexRepo):
    """Representation of a dataset handled by datalad.

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
        # TODO: More doc. See above.

        super(Handle, self).__init__(path, url, direct=direct, runner=runner,
                                     backend=backend)

        datalad_path = opj(self.path, '.datalad')
        if not exists(datalad_path):
            os.mkdir(datalad_path)

        # Read configuration as far as it is available already.
        # Set defaults, wherever there's nothing available.
        self.config_file = opj(datalad_path, 'handle.cfg')
        self._cfg_parser = SafeConfigParser()

        if exists(self.config_file):
            self._cfg_parser.read(self.config_file)
        if not self._cfg_parser.has_section('Handle'):
            self._cfg_parser.add_section('Handle')
        # By now, the datalad id is the uuid of the original annex that handle
        # was created from. Since that config file is added to git, the id is
        # kept, whenever the repository is cloned.
        if not self._cfg_parser.has_option('Handle', 'id'):
            self._cfg_parser.set('Handle', 'id',
                                 self.repo.config_reader().get_value("annex",
                                                                     "uuid"))
        # Constructors parameter 'name' has priority to be used with this
        # instance as well as to be used as default name, if there is no
        # default name in config file already. If nothing is available at all,
        # the repository's name in the filesystem is used as default.
        if not self._cfg_parser.has_option('Handle', 'name'):
            self._cfg_parser.set('Handle', 'name', name or basename(self.path))
        self.name = name or self._cfg_parser.get('Handle', 'name')
        # TODO: if name is set during runtime, how to treat this? Rethink,
        # whether this means to set the default name

        # By now, we distinguish between metadata explicitly supported by
        # datalad (option 'standard') in order to ease queries, and additional,
        # metadata (option 'custom'), that takes more effort to query.
        # However, this distinction is done inside the handler.
        # TODO: As soon as we are sure about this, have better documentation.

        if not self._cfg_parser.has_section('Metadata'):
            self._cfg_parser.add_section('Metadata')
        if not self._cfg_parser.has_option('Metadata', 'handler'):
            self._cfg_parser.set('Metadata', 'handler',
                                 'DefaultHandler')

    def __del__(self):
        # TODO: destructor seems to not be called when python program just ends.
        # Check what this is about.

        with open(self.config_file, 'w') as f:
            self._cfg_parser.write(f)
        self.add_to_git(self.config_file, "Update config file.")

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        Note: There is a second meaning of 'equal' handles, meaning that
        they have the same datalad id. However, at the level of instances of
        this class, 'equal' means, that the both of them are representing the
        very same repository.
        """
        return self.path == obj.path

    @property
    def datalad_id(self):
        """Get the identifier of the handle.

        Returns
        -------
        str
        """
        return self._cfg_parser.get('Handle', 'id')

    def set_metadata_handler(self, handler=DefaultHandler):
        """
        std: subclass of MetadataHandler
        custom: subclass of MetadataHandler
        """
        if not issubclass(handler, MetadataHandler):
            raise TypeError("%s is not a MetadataHandler." % type(std))

        self._cfg_parser.set('Metadata', 'handler', handler.__name__)

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
        """
        Returns:
        --------
        datalad.support.metadatahandler.Graph (currently just rdflib.Graph)
        """
        name = self._cfg_parser.get('Metadata', 'handler')
        import datalad.support.metadatahandler as mdh
        try:
            handler = getattr(mdh, name)(opj(self.path, '.datalad'))
        except AttributeError, e:
            lgr.error("'%s' is an unknown metadata handler." % name)
            raise ValueError("'%s' is an unknown metadata handler." % name)

        return handler.get_handle_graph(self.path)

    def set_metadata(self, meta):
        """
        Parameters:
        -----------
        meta: datalad.support.metadatahandler.Graph
          (currently just rdflib.Graph)
        """
        name = self._cfg_parser.get('Metadata', 'handler')
        import datalad.support.metadatahandler as mdh
        try:
            handler = getattr(mdh, name)(opj(self.path, '.datalad'))
        except AttributeError, e:
            lgr.error("'%s' is an unknown metadata handler." % name)
            raise ValueError("'%s' is an unknown metadata handler." % name)

        handler.set(meta)