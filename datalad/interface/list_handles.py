# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for listing installed handles

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.collectionrepo import CollectionRepo, \
    CollectionRepoHandleBackend
from datalad.support.handle import Handle
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class ListHandles(Interface):
    """List all locally installed handles."""

    def __call__(self):
        """

        Returns
        -------
        list of Handle
        """

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))
        for handle in local_master.get_handle_list():
            print(handle)

        return [Handle(CollectionRepoHandleBackend(local_master, key))
                for key in local_master.get_handle_list()]

