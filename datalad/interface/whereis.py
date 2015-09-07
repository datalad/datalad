# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for finding location of repositories based on their names
"""

__docformat__ = 'restructuredtext'


from os.path import join as opj
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..log import lgr
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class Whereis(Interface):
    """Find a handle or collection by its name"""

    _params_ = dict(
        key=Parameter(
            args=('key',),
            doc="name of the handle or collection to look for",
            constraints=EnsureStr()))

    def __call__(self, key):

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))

        if key in local_master.git_get_remotes():
            print(CollectionRepoBackend(local_master, key).url)
        elif key in local_master.get_handle_list():
            print(CollectionRepoHandleBackend(local_master, key).url)
        else:
            lgr.error("Unknown name '%s" % key)