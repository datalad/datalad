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
from .crawl import Crawl
from .update import Update
from .whereis import Whereis
from .describe import Describe
from .pull import Pull
from .push import Push

# all interfaces should be associated with (at least) one of the groups below
_group_collection = (
    'Commands for collection handling',
    [
        CreateCollection,
        RegisterCollection,
        UnregisterCollection,
        ListCollection,
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
    ])

_group_misc = (
    'Miscellaneous commands',
    [
        Test,
        Crawl,
        SPARQLQuery,
        Update,
        Whereis,
        Describe,
        Pull,
        Push
    ])
