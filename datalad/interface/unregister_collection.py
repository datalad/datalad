# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for collection de-registration

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


class UnregisterCollection(Interface):
    """Unregister a collection with datalad.

    Makes that collection unknown to datalad. This means it's no longer
    included in searches and it's not available as a source of handles,
    for example.
    """
    _params_ = dict(
        name=Parameter(
            doc="name of the collection to unregister",
            constraints=EnsureStr()))

    def __call__(self, name):

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))
        local_master.git_remote_remove(name)
