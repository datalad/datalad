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
from os.path import join as opj

from .utils_testrepos import BasicAnnexTestRepo, BasicGitTestRepo
from .utils import with_tempfile, assert_true, ok_clean_git, eq_, ok_
from .utils import ok_file_under_git, ok_broken_symlink, ok_good_symlink
from .utils import swallow_outputs
from .utils import on_windows
from .utils import SkipTest

# TODO: still true?
if on_windows:
    raise SkipTest("experiencing issues on windows -- disabled for now")


def _test_BasicAnnexTestRepo(repodir):
    trepo = BasicAnnexTestRepo(repodir)
    trepo.create()
    ok_clean_git(trepo.path)
    ok_file_under_git(trepo.path, 'test.dat')
    ok_file_under_git(trepo.path, 'INFO.txt')
    ok_file_under_git(trepo.path, 'test-annex.dat', annexed=True)
    ok_(trepo.repo.file_has_content('test-annex.dat') is False)
    with swallow_outputs():
        trepo.repo.get('test-annex.dat')
    ok_(trepo.repo.file_has_content('test-annex.dat'))


# Use of @with_tempfile() apparently is not friendly to test generators yet
# so generating two tests manually
def test_BasicAnnexTestRepo_random_location_generated():
    _test_BasicAnnexTestRepo(None)  # without explicit path -- must be generated


@with_tempfile()
def test_BasicAnnexTestRepo(path):
    _test_BasicAnnexTestRepo(path)


@with_tempfile()
def test_BasicGitTestRepo(path):
    trepo = BasicGitTestRepo(path)
    trepo.create()
    ok_clean_git(trepo.path, annex=False)
    ok_file_under_git(trepo.path, 'test.dat')
    ok_file_under_git(trepo.path, 'INFO.txt')
