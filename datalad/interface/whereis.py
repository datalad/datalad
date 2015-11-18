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
from datalad.cmdline.helpers import get_datalad_master
from ..log import lgr

from six.moves.urllib.parse import urlparse


class Whereis(Interface):
    """Get the location of a handle or collection.

    Finds a handle or collection on local filesystem by its name and returns
    the path to that location.
    """

    _params_ = dict(
        key=Parameter(
            args=('key',),
            doc="name of the handle or collection to look for",
            constraints=EnsureStr()))

    def __call__(self, key):
        """
        Returns
        -------
        str
        """

        local_master = get_datalad_master()

        if key in local_master.git_get_remotes():
            location = CollectionRepoBackend(local_master, key).url
        elif key in local_master.get_handle_list():
            location = CollectionRepoHandleBackend(local_master, key).url
        else:
            lgr.error("Unknown name '%s'" % key)

        result = urlparse(location).path
        print(result)
        return result