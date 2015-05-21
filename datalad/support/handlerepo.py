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
from abc import ABCMeta, abstractmethod, abstractproperty


from annexrepo import AnnexRepo
from .metadatahandler import MetadataHandler, DefaultHandler, URIRef, RDF, \
    DLNS, Graph

lgr = logging.getLogger('datalad.handle')


class HandleBackend(object):

    __metaclass__ = ABCMeta

    @abstractproperty
    def id(self):
        pass

    @abstractproperty
    def url(self):
        pass

    @abstractmethod
    def get_name(self):
        pass

    @abstractmethod
    def set_name(self, name):
        pass

    name = abstractproperty(get_name, set_name)

    @abstractmethod
    def get_metadata(self):
        print "Oha"
        pass

    @abstractmethod
    def set_metadata(self, meta):
        pass

    metadata = abstractproperty(get_metadata, set_metadata)


class Handle(object):
    """Representation of a Handle's metadata.

    Independent on its physical representation.
    """

    # TODO: May be all the data like url, id should directly go into the
    # metadata graph. If we need them without a desire to query/build the
    # metadata graph we would likely use HandleRepo instead of Handle anyway.

    def __init__(self, src=None, name=None):
        # TODO: Handling of 'name' option. See Collections.

        if isinstance(src, HandleBackend):
            self._backend = src
            self.id = self._backend.id
            self.url = self._backend.url
            self.name = self._backend.name
            self.metadata = self._backend.metadata

        elif isinstance(src, Handle):
            # TODO: Correct behaviour of copy constructor?
            # Does this mean, Handle is also a HandleBackend?
            # Additionally think about pure runtime handles, without any
            # backend. They would need to store the data, instead of linking
            # to a backend. But do we need such?
            self._backend = src
            self.id = self._backend.id
            self.url = self._backend.url
            self.name = self._backend.name
            self.metadata = self._backend.metadata

        elif src is None:
            self._backend = None
            self.id = None
            self.url = None
            self.name = name
            self.metadata = Graph(identifier=URIRef(self.name))

        else:
            e_msg = "Invalid source for Handle: %s." % type(src)
            lgr.error(e_msg)
            raise TypeError(e_msg)


class HandleRepoBranchBackend(HandleBackend):
    # TODO: Name. See corresponding naming for CollectionBackend.

    def __init__(self, repo, branch):

        # TODO: Check whether the branch handling is reasonable,
        # especially whether this works on windows.

        # Note: By now 'branch' has no effect at all. Just a reminder.

        if not isinstance(repo, HandleRepo):
            e_msg = "Can't deal with type '%s' to access a handle repository." \
                    % type(repo)
            lgr.error(e_msg)
            raise TypeError(e_msg)
        else:
            self._repo = repo

        self._branch = branch

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

        super(HandleRepo, self).__init__(path, url, direct=direct, runner=runner,
                                     backend=backend)

        self.datalad_path = opj(self.path, '.datalad')
        self.metadata_path = opj(self.datalad_path, 'metadata')
        if not exists(self.datalad_path):
            os.mkdir(self.datalad_path)
        if not exists(self.metadata_path):
            os.mkdir(self.metadata_path)

        # Read configuration as far as it is available already.
        # Set defaults, wherever there's nothing available.
        self.config_file = opj(self.datalad_path, 'handle.cfg')
        self._cfg_parser = SafeConfigParser()

        if exists(self.config_file):
            self._cfg_parser.read(self.config_file)
        if not self._cfg_parser.has_section('HandleRepo'):
            self._cfg_parser.add_section('HandleRepo')
        # By now, the datalad id is the uuid of the original annex that handle
        # was created from. Since that config file is added to git, the id is
        # kept, whenever the repository is cloned.
        if not self._cfg_parser.has_option('HandleRepo', 'id'):
            self._cfg_parser.set('HandleRepo', 'id',
                                 self.repo.config_reader().get_value("annex",
                                                                     "uuid"))
        # Constructors parameter 'name' has priority to be used with this
        # instance as well as to be used as default name, if there is no
        # default name in config file already. If nothing is available at all,
        # the repository's name in the filesystem is used as default.
        if not self._cfg_parser.has_option('HandleRepo', 'name'):
            self._cfg_parser.set('HandleRepo', 'name', name or basename(self.path))
        self.name = name or self._cfg_parser.get('HandleRepo', 'name')
        # TODO: if name is set during runtime, how to treat this? Rethink,
        # whether this means to set the default name

        # By now, we distinguish between metadata explicitly supported by
        # datalad (option 'standard') in order to ease queries, and additional,
        # metadata (option 'custom'), that takes more effort to query.
        # However, this distinction is done inside the handler.
        # TODO: As soon as we are sure about this, have better documentation.
        # Note: This comment is outdated but kept as a reminder. To be replaced.

        if not self._cfg_parser.has_section('Metadata'):
            self._cfg_parser.add_section('Metadata')
        if not self._cfg_parser.has_option('Metadata', 'handler'):
            self._cfg_parser.set('Metadata', 'handler',
                                 'DefaultHandler')

    def __del__(self):
        # TODO: destructor seems to not be called when python program just exits.
        # Check what this is about and how to solve it.

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
        return self._cfg_parser.get('HandleRepo', 'id')

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
            handler = getattr(mdh, name)(self.metadata_path)
        except AttributeError:
            lgr.error("'%s' is an unknown metadata handler." % name)
            raise ValueError("'%s' is an unknown metadata handler." % name)
        
        meta = handler.get_graph()
        meta.add((URIRef(self.path), RDF.type, DLNS.Handle))

        return meta

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
            handler = getattr(mdh, name)(self.metadata_path)
        except AttributeError:
            lgr.error("'%s' is an unknown metadata handler." % name)
            raise ValueError("'%s' is an unknown metadata handler." % name)

        handler.set(meta)
        self.add_to_git(opj(self.metadata_path, '*'), "Metadata updated.")

    def get_handle(self, branch=None):
        """Convenience method to create a Handle instance.
        """
        # TODO: set branch option in action
        return Handle(HandleRepoBranchBackend(self, branch))