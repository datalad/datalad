# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface definition

"""

__docformat__ = 'restructuredtext'

# the following should be series of imports of interface implementations
# the shall be exposed in the Python API and the cmdline interface
from .create_collection import CreateCollection
from .create_handle import CreateHandle
from .register_collection import RegisterCollection
from .add_handle import AddHandle
from .install_handle import InstallHandle
from .unregister_collection import UnregisterCollection
from .list_collections import ListCollection
from .list_handles import ListHandles
from .sparql_query import SPARQLQuery
from .uninstall_handle import UninstallHandle
from .test import Test
from .get import Get
from .drop import Drop
from .crawl import Crawl
from .oldcrawl import OldCrawl
from .update import Update
from .whereis import Whereis
from .describe import Describe
from .pull import Pull
from .push import Push
from .upgrade_handle import UpgradeHandle
from .search_handle import SearchHandle
from .publish_handle import PublishHandle
from .search_collection import SearchCollection
from .publish_collection import PublishCollection
from .import_metadata import ImportMetadata
from .add_archive_content import AddArchiveContent

# all interfaces should be associated with (at least) one of the groups below
_group_collection = (
    'Commands for collection handling',
    [
        CreateCollection,
        RegisterCollection,
        UnregisterCollection,
        ListCollection,
        PublishCollection,
    ])

_group_handle = (
    'Commands for handle operations',
    [
        CreateHandle,
        AddHandle,
        InstallHandle,
        UninstallHandle,
        ListHandles,
        Get,
        Drop,
        UpgradeHandle,
        PublishHandle,
    ])

_group_misc = (
    'Miscellaneous commands',
    [
        Test,
        Crawl,
        OldCrawl,
        SPARQLQuery,
        SearchHandle,
        SearchCollection,
        Update,
        Whereis,
        Describe,
        Pull,
        Push,
        ImportMetadata,
        AddArchiveContent,
    ])
