# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for importing metadata
"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import exists, join as opj, isfile, isdir

from six import string_types

from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone, EnsureListOf
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..support.handlerepo import HandleRepo, HandleRepoBackend
from datalad.support.collection import Collection
from datalad.support.handle import Handle

from ..support.metadatahandler import PlainTextImporter, CustomImporter, \
    URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from ..consts import HANDLE_META_DIR, REPO_STD_META_FILE
from appdirs import AppDirs
from six.moves.urllib.parse import urlparse

dirs = AppDirs("datalad", "datalad.org")

# TODO: Move elsewhere, may be even create it automatically from known
# importers
ImporterDict = {"plain-text": PlainTextImporter}


class ImportMetadata(Interface):
    """Import metadata to the repository in cwd.

    Make metadata available to datalad. This may involve metadata, that is
    available from within the repository but not yet known to datalad or
    metadata that comes from any outside location.
    There are different importers, that can be used to read that metadata
    depending on its format.

    Example:

    ~/MyHandle$ datalad import-metadata plain-text /path/to/my/textfiles

    ~/MyCollection$ datalad import-metadata plain-text /path/to/my/textfiles \
            MyHandle
    """
    # TODO: Check and doc sub entities

    _params_ = dict(

        format=Parameter(
            doc="an identifier of the format the to be imported metadata is "
                "available in. Currently available are:" +
                "\n".join(k for k in ImporterDict),
            constraints=EnsureStr()),
        path=Parameter(
            doc="path to the directory or list of the files to be imported.",
            nargs='+',
            constraints=EnsureStr() | EnsureListOf(string_types)),
        subject=Parameter(
            doc="subject to be described by the metadata. By default it's the "
                "repository we are in. In case it's not the handle or "
                "collection itself, provide an URI to identify the sub-entity "
                "to describe.",
            constraints=EnsureStr() | EnsureNone()),
        handle=Parameter(
            doc="when importing to a collection, specify the handle the "
                "metadata is about. By default it's interpreted as collection "
                "level metadata.",
            constraints=EnsureStr() | EnsureNone()),)

    def __call__(self, format, path, handle=None, subject=None):
        """
        Returns
        -------
        Handle or Collection
        """

        if len(path) == 1:
            if exists(path[0]) and isdir(path[0]):
                path = path[0]
            else:
                raise RuntimeError("Not an existing directory: %s" % path[0])

        repo = get_repo_instance()

        # TODO: Should we accept a pure annex and create a handle repo from it?
        if isinstance(repo, HandleRepo):
            repo.import_metadata(ImporterDict[format], files=path,
                                 about_uri=subject if subject is not None
                                 else DLNS.this)
        elif isinstance(repo, CollectionRepo):
            if handle is None:
                # collection level
                repo.import_metadata_collection(ImporterDict[format],
                                                files=path, about_uri=subject)
            else:
                repo.import_metadata_to_handle(ImporterDict[format], handle,
                                               files=path, about_uri=subject)

        # Update metadata of local master collection:
        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))

        if isinstance(repo, CollectionRepo):
            # update master if it is a registered collection:
            for c in local_master.git_get_remotes():
                if repo.path == local_master.git_get_remote_url(c):
                    local_master.git_fetch(c)
        elif isinstance(repo, HandleRepo):
            # update master if it is an installed handle:
            for h in local_master.get_handle_list():
                if repo.path == urlparse(
                        CollectionRepoHandleBackend(local_master, h).url).path:
                    local_master.import_metadata_to_handle(CustomImporter,
                                                           key=h,
                                                           files=opj(
                                                               repo.path,
                                                               HANDLE_META_DIR))

        # TODO: What to do in case of a handle, if it is part of another
        # locally available collection than just the master?

        if isinstance(repo, CollectionRepo):
            return Collection(CollectionRepoBackend(repo))
        elif isinstance(repo, HandleRepo):
            return Handle(HandleRepoBackend(repo))