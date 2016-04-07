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
#from .sparql_query import SPARQLQuery
from .test import Test
from .crawl import Crawl
from .pull import Pull
from .push import Push
from .add_archive_content import AddArchiveContent
from .download_url import DownloadURL
from .ls import Ls
from .clean import Clean
from ..distribution.install import Install
from ..distribution.publish import Publish
from .POC_move import POCMove
from .POC_update import POCUpdate
from .POC_uninstall import POCUninstall
from ..distribution.create_publication_target_sshwebserver import \
    CreatePublicationTargetSSHWebserver
from ..distribution.add_sibling import AddSibling
from .POC_modify_subhandle_urls import POCModifySubhandleURLs


# all interfaces should be associated with (at least) one of the groups below
_group_handle = (
    'Commands for dataset operations',
    [
        Install,
        Publish,
        POCUninstall,
        POCMove,
        POCUpdate,
        CreatePublicationTargetSSHWebserver,
        AddSibling,
        POCModifySubhandleURLs,
    ])

_group_misc = (
    'Miscellaneous commands',
    [
        Test,
        Crawl,
        #SPARQLQuery,
        #Describe,
        Pull,
        Push,
        #ImportMetadata,
        AddArchiveContent,
        DownloadURL,
        Ls,
        Clean,
    ])
