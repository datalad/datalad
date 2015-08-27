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
from os.path import join as opj, abspath, expanduser, expandvars
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo, \
    CollectionRepoHandleBackend
from datalad.support.handlerepo import HandleRepo
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class InstallHandle(Interface):
    """Installs a handle."""
    _params_ = dict(
        orig_name=Parameter(
            doc="name of the handle to install",
            constraints=EnsureStr()),
        path=Parameter(
            args=('path',),
            nargs='?',
            doc="path, where to install the handle",
            constraints=EnsureStr()),
        inst_name=Parameter(
            doc="local name of the installed handle",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, orig_name, path=curdir, inst_name=None):

        # TODO: Address handle via ID or url
        # check urllib2 for url "validator"


        # TODO: metadata: priority: handle->collection->nothing

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                          'localcollection'))

        # retrieve handle's url from id (orig_name):
        q_col = orig_name.split('/')[0]
        q_hdl = orig_name.split('/')[1]

        handle_backend = CollectionRepoHandleBackend(repo=local_master,
                                                     key=q_hdl,
                                                     branch=q_col + '/master')

        # install the handle:
        installed_handle = HandleRepo(abspath(expandvars(expanduser(path))),
                                      handle_backend.url)
        local_master.add_handle(installed_handle,
                                name=inst_name or installed_handle.name)