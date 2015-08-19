# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for collection creation

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


class CreateCollection(Interface):
    """Creates a new collection."""
    _params_ = dict(
        path=Parameter(
            doc="path where to create the collection",
            constraints=EnsureStr()),
        name=Parameter(
            doc="name of the collection; if no name is given the name of the "
                "destination directory is used.",
            constraints=EnsureStr()))

    def __call__(self, path=curdir, name=None):

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                          'localcollection'))
        # create the collection:
        new_collection = CollectionRepo(abspath(path), name=name)
        # TODO: Move the abspath conversion to a constraint!
        # Additionally (or instead?) check for validity: existing directory or
        # just non-existing.

        # register with local master:
        local_master.git_remote_add(new_collection.name, new_collection.path)
        local_master.git_fetch(new_collection.name)