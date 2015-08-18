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


@with_tempfile()
def test_BasicTestRepo(repodir):
    trepo = BasicTestRepo(repodir)
    ok_clean_git(repodir)
    ok_file_under_git(repodir, 'test.dat')
    ok_file_under_git(repodir, 'test-annex.dat', annexed=True)
    if not trepo.repo.is_crippled_fs():
        ok_broken_symlink(pathjoin(repodir, 'test-annex.dat'))
    with swallow_outputs():
        trepo.repo.annex_get('test-annex.dat')
    if not trepo.repo.is_crippled_fs():
        ok_good_symlink(pathjoin(repodir, 'test-annex.dat'))
