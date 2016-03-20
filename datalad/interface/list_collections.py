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
from datalad.support.collection_backends import CollectionRepoBackend
from datalad.support.collection import Collection
from datalad.cmdline.helpers import get_datalad_master


class ListCollection(Interface):
    """List all collections known to datalad."""

    @staticmethod
    def __call__():
        """
        Returns
        -------
        list of Collection
        """

        local_master = get_datalad_master()
        for collection in local_master.git_get_remotes():
            print(collection)

        return [CollectionRepoBackend(local_master, branch=remote + "/master")
                for remote in local_master.git_get_remotes()]
