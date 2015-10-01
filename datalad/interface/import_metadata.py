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
from ..support.handlerepo import HandleRepo
from ..support.metadatahandler import PlainTextImporter, CustomImporter, \
    URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from ..consts import HANDLE_META_DIR, REPO_STD_META_FILE
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")

# TODO: Move elsewhere, may be even create it automatically from known
# importers
ImporterDict = {"plain-text": PlainTextImporter}


class ImportMetadata(Interface):
    """Import metadata to the repository in cwd.
    """
    # TODO: A lot of doc ;)

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

    def __call__(self, format, path, subject=None, handle=None):

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

