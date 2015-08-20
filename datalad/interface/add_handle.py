# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for adding a handle to a collection

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.handlerepo import HandleRepo
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class AddHandle(Interface):
    """Adds a handle to a collection."""
    _params_ = dict(
        h_path=Parameter(
            doc="path to the handle",
            constraints=EnsureStr()),
        c_path=Parameter(
            doc="path to the collection",
            constraints=EnsureStr()),
        h_name=Parameter(
            args=('h_name',),
            nargs='?',
            doc="name of the handle in the collection. If no name is given, "
                "the handle's default name is used.",
            constraints=EnsureStr()))

    def __call__(self, h_path, c_path, h_name=None):

        # TODO: - add a remote handle by its url
        #       - handle and collection can be adressed via name or path/url

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                          'localcollection'))
        handle = HandleRepo(h_path)
        collection = CollectionRepo(c_path)
        collection.add_handle(handle, name=h_name)

        # TODO: More sophisticated: Check whether the collection is registered.
        # Might be a different name than collection.name or not at all.
        local_master.git_fetch(collection.name)