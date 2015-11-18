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
from os.path import join as opj, abspath, expanduser, expandvars, isdir, exists
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.handle_backends import CollectionRepoHandleBackend
from datalad.support.handlerepo import HandleRepo
from datalad.support.handle import Handle
from datalad.support.metadatahandler import CustomImporter
from datalad.consts import HANDLE_META_DIR, REPO_STD_META_FILE
from datalad.cmdline.helpers import get_datalad_master

from six.moves.urllib.parse import urlparse


class AddHandle(Interface):
    """Add a handle to a collection.

    This results in the handle to be included in the collection.
    Optionally you can give it a new name, that is used to reference that
    handle via the collection it is to be added to.
    The collection has to be locally available.
    Example:

        $ datalad add-handle MyPreciousHandle MyFancyCollection NewFancyHandle

        $ datalad add-handle MyPreciousHandle MyFancyCollection

        inside/MyPreciousHandle$ datalad add-handle . MyFancyCollection
    """
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
        """
        Returns
        -------
        Handle
        """

        local_master = get_datalad_master()

        if isdir(abspath(expandvars(expanduser(handle)))):
            h_path = abspath(expandvars(expanduser(handle)))
            handle_repo = HandleRepo(h_path, create=False)
        elif handle in local_master.get_handle_list():
            h_path = urlparse(CollectionRepoHandleBackend(repo=local_master,
                                                 key=handle).url).path
            handle_repo = HandleRepo(h_path, create=False)
            if not isdir(h_path):
                raise RuntimeError("Invalid path to handle '%s':\n%s" %
                                   (handle, h_path))

        elif urlparse(handle).scheme != '':  # rudimentary plausibility check for now
            # treat as a remote annex
            handle_repo = handle
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

        collection_repo = CollectionRepo(c_path, create=False)
        collection_repo.add_handle(handle_repo, name=name)

        # get handle's metadata, if there's any:
        if isinstance(handle_repo, HandleRepo) and \
                exists(opj(handle_repo.path, HANDLE_META_DIR,
                           REPO_STD_META_FILE)):
            collection_repo.import_metadata_to_handle(CustomImporter,
                                                      key=name if name is not None else handle_repo.name,
                                                      files=opj(
                                                          handle_repo.path,
                                                          HANDLE_META_DIR))

        # TODO: More sophisticated: Check whether the collection is registered.
        # Might be a different name than collection_repo.name or not at all.
        local_master.git_fetch(collection_repo.name)

        return CollectionRepoHandleBackend(collection_repo,
                                           name if name is not None
                                           else handle_repo.name)
