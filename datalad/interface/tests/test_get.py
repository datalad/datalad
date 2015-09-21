# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for get command

"""

__docformat__ = 'restructuredtext'

from mock import patch
from ...api import get

from ...tests.utils import with_testrepos
from ...tests.utils import assert_cwd_unchanged

@assert_cwd_unchanged(ok_to_chdir=True)
@with_testrepos('basic', flavors=['clone'])
@patch('datalad.support.annexrepo.AnnexRepo.annex_get')
def test_get_basic(path_to_ignore, annex_get_mocked):
    get('test-annex.dat')
    annex_get_mocked.assert_called_with('test-annex.dat')