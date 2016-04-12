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
from datalad.distribution.modify_subhandle_urls import ModifySubhandleURLs
from datalad.distribution.move import Move
from datalad.distribution.uninstall import Uninstall
from datalad.distribution.update import Update
from .add_archive_content import AddArchiveContent
from .clean import Clean
from .crawl import Crawl
from .download_url import DownloadURL
from .ls import Ls
from .pull import Pull
from .push import Push
from .test import Test
from ..distribution.add_sibling import AddSibling
from ..distribution.create_publication_target_sshwebserver import \
    CreatePublicationTargetSSHWebserver
from ..distribution.install import Install
from ..distribution.publish import Publish

# all interfaces should be associated with (at least) one of the groups below
_group_dataset = (
    'Commands for dataset operations',
    [
        Install,
        Publish,
        Uninstall,
        Move,
        Update,
        CreatePublicationTargetSSHWebserver,
        AddSibling,
        ModifySubhandleURLs,
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
