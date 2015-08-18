# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for test repositories

"""
from os.path import join as pathjoin

from .utils_testrepos import BasicTestRepo
from .utils import with_tempfile, assert_true, ok_clean_git
from .utils import ok_file_under_git, ok_broken_symlink, ok_good_symlink
from .utils import swallow_outputs


def _test_BasicTestRepo(repodir):
    trepo = BasicTestRepo(repodir)
    trepo.create()
    ok_clean_git(trepo.path)
    ok_file_under_git(trepo.path, 'test.dat')
    ok_file_under_git(trepo.path, 'test-annex.dat', annexed=True)
    if not trepo.repo.is_crippled_fs():
        ok_broken_symlink(pathjoin(trepo.path, 'test-annex.dat'))
    with swallow_outputs():
        trepo.repo.annex_get('test-annex.dat')
    if not trepo.repo.is_crippled_fs():
        ok_good_symlink(pathjoin(trepo.path, 'test-annex.dat'))

# Use of @with_tempfile() apparently is not friendly to test generators yet
# so generating two tests manually
def test_BasicTestRepo_random_location_generated():
    _test_BasicTestRepo(None)  # without explicit path -- must be generated

@with_tempfile()
def test_BasicTestRepo(path):
    yield _test_BasicTestRepo, path