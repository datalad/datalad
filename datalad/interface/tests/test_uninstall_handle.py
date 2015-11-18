# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for uninstall-handle command

"""

__docformat__ = 'restructuredtext'

import re
from os.path import exists
from mock import patch
from nose.tools import assert_not_in
from six.moves.urllib.parse import urlparse

from ...utils import swallow_logs
from ...api import install_handle, uninstall_handle
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=['clone'])  # should work for any annex
@with_tempfile()
@with_tempfile(mkdir=True)
def test_uninstall_handle(handle_url, path, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:
        handle = install_handle(handle_url, path)
        assert_in(handle.name, get_datalad_master().get_handle_list())

        uninstall_handle(handle.name)

        # unknown to datalad
        assert_not_in(handle.name, get_datalad_master().get_handle_list())

        # repo was removed:
        ok_(not exists(path))
