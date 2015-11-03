# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for list-handles command

"""

__docformat__ = 'restructuredtext'

import re
from mock import patch
from nose.tools import assert_is_instance, assert_not_in
from six.moves.urllib.parse import urlparse

from ...utils import swallow_logs
from ...api import install_handle, list_handles, register_collection
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master
from ...support.handle import Handle
from ...support.handlerepo import HandleRepo


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=['clone'])  # should work for any annex
@with_tempfile()
@with_testrepos('.*collection.*', flavors=['network', 'local-url'])
@with_tempfile(mkdir=True)
def test_list_handles(handle_url, path, collection_url, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:
        handle = install_handle(handle_url, path)
        collection = register_collection(collection_url)

        handle_list = list_handles(remote=False)
        remote_handle_list = list_handles(remote=True)

        for item in handle_list + remote_handle_list:
            assert_is_instance(item, Handle)

        # installed handle in handle_list:
        assert_in(handle.name, [h.name for h in handle_list])
        assert_in(path, [urlparse(h.url).path for h in handle_list])

        # installed handle not in remote_handle_list:
        assert_not_in(handle.name, [h.name for h in remote_handle_list])

        # remote handles not in handle_list, but in remote_handle_list:
        for r_handle in collection:
            assert_not_in(r_handle, [h.name for h in handle_list])
            assert_in(r_handle, [h.name for h in remote_handle_list])


