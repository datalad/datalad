# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for listing registered collections

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.collectionrepo import CollectionRepo
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class ListCollection(Interface):
    """list all colections known to datalad."""

    def __call__(self):

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))
        for collection in local_master.git_get_remotes():
            print(collection)

