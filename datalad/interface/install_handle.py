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
from os.path import join as opj, abspath, expanduser, expandvars, isdir, exists, basename
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo, \
    CollectionRepoHandleBackend
from appdirs import AppDirs

from ..support.handlerepo import HandleRepo
from ..support.network import get_url_straight_filename
from ..utils import getpwd, get_url_path
from .base import Interface

dirs = AppDirs("datalad", "datalad.org")


class InstallHandle(Interface):
    """Install a handle.

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
            doc="local name of the installed handle",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, handle, path=None, name=None):

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))

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
        if parts[0] in local_master.git_get_remotes() \
                and len(parts) >= 2:
            # 'handle' starts with a name of a known collection, followed by at
            # least a second part, separated by '/'.
            # Therefore assuming it's a handle's key, not an url

            url = CollectionRepoHandleBackend(repo=local_master,
                                              key=handle[len(parts[0])+1:],
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

        local_name = name or installed_handle.name
        if name_prefix is not None:
            # TODO: Yarik is asking why?  how would we later decipher which one is local and which one remote????
            local_name = name_prefix + local_name

        # "register" handle only if not yet known
        if local_name not in known_handles:
            local_master.add_handle(installed_handle, name=local_name)

        # TODO: metadata: priority: handle->collection->nothing
