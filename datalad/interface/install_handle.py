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
from os.path import join as opj, abspath, expanduser, expandvars, isdir
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo, \
    CollectionRepoHandleBackend
from datalad.support.handlerepo import HandleRepo
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class InstallHandle(Interface):
    """Installs a handle.
        Examples:

    $ datalad install-handle http://psydata.ovgu.de/forrest_gump/.git /foo/bar
    $ datalad install-handle MyCoolCollection/EvenCoolerHandle /foo/bar
    """
    _params_ = dict(
        handle=Parameter(
            doc="name or url of the handle to install; in case of  a name this "
                "is expected to state the name of the collection the handle is "
                "in, followed by the handle's name, seperated by '/'.",
            constraints=EnsureStr()),
        path=Parameter(
            args=('path',),
            nargs='?',
            doc="path, where to install the handle",
            constraints=EnsureStr()),
        name=Parameter(
            doc="local name of the installed handle",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, handle, path=curdir, name=None):

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
            # least a second part, seperated by '/'.
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

        # install the handle:
        installed_handle = HandleRepo(abspath(expandvars(expanduser(path))),
                                      url, create=True)
        local_name = name or installed_handle.name
        if name_prefix is not None:
            local_name = name_prefix + local_name

        local_master.add_handle(installed_handle, name=local_name)

        # TODO: metadata: priority: handle->collection->nothing
