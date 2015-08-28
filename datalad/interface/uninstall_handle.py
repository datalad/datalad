# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for uninstalling a handle

"""

__docformat__ = 'restructuredtext'


from os.path import join as opj

from appdirs import AppDirs
from urlparse import urlparse


from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.collectionrepo import CollectionRepo, \
    CollectionRepoHandleBackend
from ..utils import rmtree

dirs = AppDirs("datalad", "datalad.org")


class UninstallHandle(Interface):
    """Uninstalls a handle.
        Examples:

    $ datalad uninstall-handle MyCoolHandle
    """
    _params_ = dict(
        handle=Parameter(
            doc="name of the handle to uninstall",
            constraints=EnsureStr()))

    def __call__(self, handle):

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))

        if handle not in local_master.get_handle_list():
            raise ValueError("Handle '%s' unknown." % handle)

        # converting file-scheme url to local path:
        path = urlparse(CollectionRepoHandleBackend(local_master,
                                                    handle).url).path
        rmtree(path)
        local_master.remove_handle(handle)

