# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for search-handle command

"""

__docformat__ = 'restructuredtext'

from os import getcwd, chdir
from mock import patch
from nose.tools import assert_is_instance, assert_not_in
from six.moves.urllib.parse import urlparse

from ...api import search_handle, import_metadata, install_handle, \
    create_handle
from ...utils import swallow_logs
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master
from ...support.handle import Handle


@assert_cwd_unchanged
@with_testrepos('meta_pt_annex_handle', flavors=['clone'])
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_search_handle(hurl, hpath, hpath2, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        # handle to search for:
        handle = install_handle(hurl, hpath)
        # empty handle that should not be contained in any result:
        create_handle(hpath2)

        # search:
        hlist = search_handle("Poldrack")
        assert_is_instance(hlist, list)
        # no metadata imported yet, so there shouldn't be any result:
        eq_(hlist, [])

        # import handle metadata
        current_dir = getcwd()
        chdir(hpath)
        import_metadata(format="plain-text", path=hpath)
        chdir(current_dir)

        # now, search again:
        hlist = search_handle("Poldrack")

        assert_is_instance(hlist, list)
        for item in hlist:
            assert_is_instance(item, Handle)
        eq_(len(hlist), 1)
        # TODO: Replace, when Handle.__eq__ is implemented:
        eq_(hlist[0].name, handle.name)
        eq_(urlparse(hlist[0].url).path, hpath)
