# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for handle installation

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, isdir, \
    exists, basename
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.handle import Handle
from datalad.support.metadatahandler import CustomImporter
from datalad.consts import HANDLE_META_DIR, REPO_STD_META_FILE
from datalad.cmdline.helpers import get_datalad_master

from ..support.handlerepo import HandleRepo
from datalad.support.handle_backends import HandleRepoBackend, \
    CollectionRepoHandleBackend
from ..support.network import get_url_straight_filename
from ..utils import getpwd, get_url_path
from .base import Interface

# TODO: Should the URI of the installed handle be corrected to "this" after
# cloning? Probably depends on decision whether we always want to use "this"
# instead of a "real" URI.


class InstallHandle(Interface):
    """Install a handle.

    Installing a handle means to create a local repository clone of the handle
    to be installed. Additionally, that clone is registered with datalad.
    Installing a handle into an existing directory is not possible, except if
    a handle with the same name already exists therein. In the latter case,
    the cloning will be skipped.

    Examples:

      $ datalad install-handle http://psydata.ovgu.de/forrest_gump
      $ datalad install-handle MyCoolCollection/EvenCoolerHandle /foo/bar
    """
    _params_ = dict(
        handle=Parameter(
            doc="name or url of the handle to install; in case of a name it "
                "is expected to state the name of the collection the handle is "
                "in, followed by the handle's name, separated by '/'.",
            constraints=EnsureStr()),
        path=Parameter(
            args=('path',),
            nargs='?',
            doc="path, where to install the handle. If not provided, local "
                "directory with the name from the url will be used",
            constraints=EnsureStr() | EnsureNone()),
        name=Parameter(
            doc="local name of the installed handle. If not provided, the name"
                "of the installation directory will be used.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, handle, path=None, name=None):
        """
        Examples
        --------
        >>> from datalad.api import install_handle, list_handles, whereis
        >>> def test_install_handle_simple():
        ...     assert("forrest_gump" not in [h.name for h in list_handles()])
        ...     handle = install_handle("http://psydata.ovgu.de/forrest_gump/.git")
        ...     assert(os.path.exists(os.path.join(getpwd(), 'forrest_gump', '.git', 'annex')))
        ...     assert(handle.name == "forrest_gump")
        ...     assert(handle.name in [h.name for h in list_handles()])
        ...     assert(os.path.join(getpwd(), 'forrest_gump') == whereis("forrest_gump"))

        Returns
        -------
        Handle
        """
        # TODO: doctest apparently detected by nose and passed, but doesn't
        # seem to actually be executed yet.

        local_master = get_datalad_master()

        # check whether 'handle' is a key ("{collection}/{handle}")
        # or a local path or an url:
        parts = handle.split('/')
        if parts[0] == local_master.name:
            # addressing a handle, that is part of local master collection
            # Note: Theoretically, we could allow for this if a new name is
            # given.
            raise ValueError("Installing handles from collection '%s' doesn't "
                             "make sense." % local_master.name)

        name_prefix = None
        handle_name = None
        if parts[0] in local_master.git_get_remotes() \
                and len(parts) >= 2:
            # 'handle' starts with a name of a known collection, followed by at
            # least a second part, separated by '/'.
            # Therefore assuming it's a handle's key, not an url

            handle_name = handle[len(parts[0])+1:]
            url = CollectionRepoHandleBackend(repo=local_master,
                                              key=handle_name,
                                              branch=parts[0] + '/master').url
            name_prefix = parts[0] + '/'

            # TODO: Where to determine whether the handle even exists?
            # May be use Collection instead and check for "hasPart"->url
            # Note: Actually CollectionRepoHandleBackend should raise an
            # exception!
        elif isdir(abspath(expandvars(expanduser(handle)))):
            # appears to be a local path
            url = abspath(expandvars(expanduser(handle)))
        else:
            # assume it's an url:
            # TODO: Further checks needed? May be at least check for spaces and
            # ';' to avoid injection?
            url = handle

        if not path:
            if exists(url):
                # could well be a local path
                subdir = basename(url)
            else:
                # proper url -- could be a bit more evolved
                subdir = get_url_straight_filename(url, allowdir=True, strip=['.git'])
            install_path = opj(getpwd(), subdir)
        else:
            install_path = abspath(expandvars(expanduser(path)))

        # TODO:  name might be in conflict -- already have a handle with that name
        # More difficult especially if installed_handle.name to be taken!
        # It should fail as early as possible, i.e. without actually calling
        # HandleRepo(create=True) first, but we wouldn't know the name unless
        # we sense remotely!!! TODO
        known_handles = local_master.get_handle_list()
        if name and name in known_handles:
            epath = CollectionRepoHandleBackend(local_master, name).url
            if epath.startswith('file://'):
                epath = get_url_path(epath)
            if epath != install_path:
                raise ValueError("Handle %s is already known and already installed under "
                                 "different path %s. Specify another name"
                                 % (name, epath))

        if exists(install_path):
            # try to overlay without any creation/init
            try:
                installed_handle = HandleRepo(install_path, create=False)
            except:
                raise RuntimeError("%s already exists, and is not a handle" % path)

            if name and name != installed_handle.name:
                raise ValueError("Different handle (%s) is already installed under %s"
                                 % (installed_handle.name, install_path))
        else:
            # install the handle:
            installed_handle = HandleRepo(install_path, url, create=True)

        local_name = name or handle_name or installed_handle.name
        if name_prefix is not None:
            # TODO: Yarik is asking why?  how would we later decipher which one is local and which one remote????
            # Ben is answering: Why do we need to? If installed we want to use
            # the local handle instead of the remote one when addressing it in
            # datalad command, don't we? If we install
            # "somecollection/Myhandle" and later use a datalad command with
            # "somecollection/Myhandle" this should lead to the installed one,
            # I think.
            local_name = name_prefix + local_name

        # "register" handle only if not yet known
        if local_name not in known_handles:
            local_master.add_handle(installed_handle, name=local_name)

        # Import metadata of the handle, if there's any.
        # Priorities: First try to get metadata from the handle itself,
        # if there's none, then get whatever is stored in the collection it was
        # installed from.
        # TODO: Discuss this approach. May be it makes more sense to always use
        # the metadata from the collection, if the handle was installed that
        # way.

        if exists(opj(installed_handle.path, HANDLE_META_DIR,
                      REPO_STD_META_FILE)):
            local_master.import_metadata_to_handle(CustomImporter,
                                                   key=local_name,
                                                   files=opj(
                                                       installed_handle.path,
                                                       HANDLE_META_DIR))
        elif name_prefix is not None:
            # installed from  collection
            # get the metadata from that remote collection:
            metadata = dict()
            files = [f for f in local_master.git_get_files(
                name_prefix + 'master') if f.startswith(handle_name)]
            for file_ in files:
                metadata[file_[len(handle_name) + 1:]] = \
                    local_master.git_get_file_content(file_,
                                                      name_prefix + 'master')
            local_master.import_metadata_to_handle(CustomImporter,
                                                   key=local_name,
                                                   data=metadata)

        return HandleRepoBackend(installed_handle)
