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
from os.path import join as opj, abspath, expanduser, expandvars, isdir
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo, \
    CollectionRepoHandleBackend
from datalad.support.handlerepo import HandleRepo
from appdirs import AppDirs
from six.moves.urllib.parse import urlparse

dirs = AppDirs("datalad", "datalad.org")


class AddHandle(Interface):
    """Add a handle to a collection."""
    _params_ = dict(
        handle=Parameter(
            doc="path to or name of the handle",
            constraints=EnsureStr()),
        collection=Parameter(
            doc="path to or name of the collection",
            constraints=EnsureStr()),
        name=Parameter(
            args=('name',),
            nargs='?',
            doc="name of the handle in the collection. If no name is given, "
                "the handle's default name is used.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, handle, collection, name=None):

        # TODO: - add a remote handle by its url
        #       - handle and collection can be addressed via name or path/url

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                          'localcollection'))

        if isdir(abspath(expandvars(expanduser(handle)))):
            h_path = abspath(expandvars(expanduser(handle)))
        elif handle in local_master.get_handle_list():
            h_path = urlparse(CollectionRepoHandleBackend(repo=local_master,
                                                 key=handle).url).path
            if not isdir(h_path):
                raise RuntimeError("Invalid path to handle '%s':\n%s" %
                                   (handle, h_path))

        # TODO: allow for remote handles
        else:
            raise RuntimeError("Unknown handle '%s'." % handle)

        if isdir(abspath(expandvars(expanduser(collection)))):
            c_path = abspath(expandvars(expanduser(collection)))
        elif collection in local_master.git_get_remotes():
            c_path = urlparse(local_master.git_get_remote_url(collection)).path
            if not isdir(c_path):
                raise RuntimeError("Invalid path to collection '%s':\n%s" %
                                   (collection, c_path))
        else:
            raise RuntimeError("Unknown collection '%s'." % collection)

        handle_repo = HandleRepo(h_path, create=False)
        collection_repo = CollectionRepo(c_path, create=False)
        collection_repo.add_handle(handle_repo, name=name)

        # TODO: More sophisticated: Check whether the collection is registered.
        # Might be a different name than collection_repo.name or not at all.
        local_master.git_fetch(collection_repo.name)
