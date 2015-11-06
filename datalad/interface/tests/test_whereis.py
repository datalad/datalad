# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for whereis command

"""

__docformat__ = 'restructuredtext'

from mock import patch
from nose.tools import assert_is_instance
from six.moves.urllib.parse import urlparse

from ...api import create_handle, create_collection, whereis
from ...utils import swallow_logs
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_whereis(hpath, cpath, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        create_handle(hpath, "TestHandle")
        create_collection(cpath, "TestCollection")

        eq_(hpath, whereis("TestHandle"))
        eq_(cpath, whereis("TestCollection"))