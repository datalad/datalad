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
from ...utils import chpwd

@with_testrepos('basic', flavors=['clone'])
@assert_cwd_unchanged(ok_to_chdir=True)
@patch('datalad.support.annexrepo.AnnexRepo.annex_get')
def test_get_basic(repo_path, annex_get_mocked):
    chpwd(repo_path)
    get(['test-annex.dat'])
    annex_get_mocked.assert_called_with(['test-annex.dat'])

    # ATM get does glob extension
    get(['test-annex.*'])
    annex_get_mocked.assert_called_with(['test-annex.dat'])

    # thus would provide an empty list (which would cause annex call to puke!)
    # if there is no matching file, but since we mock -- we just test that
    # it functions as we thought it should
    get(['abracadabrasesame'])
    annex_get_mocked.assert_called_with([])
