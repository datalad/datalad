# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for search-collection command

"""

__docformat__ = 'restructuredtext'

from os import getcwd, chdir
from os.path import basename, exists, isdir, join as opj
from mock import patch
from nose.tools import assert_is_instance, assert_not_in
from six.moves.urllib.parse import urlparse

from ...api import search_collection, import_metadata, install_handle, \
    create_collection, add_handle, describe
from ...utils import swallow_logs
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master
from ...support.handle import Handle
from ...support.collection import Collection
from ...support.metadatahandler import DLNS, PAV, DCTERMS, URIRef, RDF, FOAF, \
    PROV, Literal, Graph
from ...support.handlerepo import HandleRepo
from ...consts import REPO_CONFIG_FILE, REPO_STD_META_FILE, HANDLE_META_DIR


@assert_cwd_unchanged
@with_testrepos('meta_pt_annex_handle', flavors=['clone'])
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_search_collection(hurl, hpath, cpath, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        handle = install_handle(hurl, hpath)
        collection = create_collection(cpath)
        add_handle(hpath, cpath)
        current_dir = getcwd()
        chdir(cpath)
        # import handle metadata
        import_metadata(format="plain-text", path=hpath, handle=handle.name)

        # search:
        clist = search_collection("Poldrack")
        assert_is_instance(clist, list)
        # string contained in handle metadata only, so there shouldn't be any
        # result:
        eq_(clist, [])

        # create some collection level metadata:
        describe(author="Benjamin Poldrack",
                 description="This a description.")
        chdir(current_dir)

        # search again:
        clist = search_collection("Poldrack")

        assert_is_instance(clist, list)
        for item in clist:
            assert_is_instance(item, Collection)
        eq_(len(clist), 1)
        # TODO: Replace, when Collection.__eq__ is implemented:
        eq_(clist[0].name, collection.name)
        eq_(urlparse(clist[0].url).path, cpath)
