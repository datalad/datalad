# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for test repositories

"""
from datalad.tests.utils_pytest import (
    assert_repo_status,
    ok_,
    ok_file_under_git,
    skip_if_on_windows,
    swallow_outputs,
    with_tempfile,
)
from datalad.tests.utils_testrepos import (
    BasicAnnexTestRepo,
    BasicGitTestRepo,
)


def _test_BasicAnnexTestRepo(repodir):
    trepo = BasicAnnexTestRepo(repodir)
    trepo.create()
    assert_repo_status(trepo.path)
    ok_file_under_git(trepo.path, 'test.dat')
    ok_file_under_git(trepo.path, 'INFO.txt')
    ok_file_under_git(trepo.path, 'test-annex.dat', annexed=True)
    ok_(trepo.repo.file_has_content('test-annex.dat') is False)
    with swallow_outputs():
        trepo.repo.get('test-annex.dat')
    ok_(trepo.repo.file_has_content('test-annex.dat'))


# Use of @with_tempfile() apparently is not friendly to test generators yet
# so generating two tests manually
# something is wrong with the implicit tempfile generation on windows
# a bunch of tested assumptions aren't met, and which ones depends on the
# windows version being tested
@skip_if_on_windows
def test_BasicAnnexTestRepo_random_location_generated():
    _test_BasicAnnexTestRepo(None)  # without explicit path -- must be generated


@with_tempfile()
def test_BasicAnnexTestRepo(path=None):
    _test_BasicAnnexTestRepo(path)


@with_tempfile()
def test_BasicGitTestRepo(path=None):
    trepo = BasicGitTestRepo(path)
    trepo.create()
    assert_repo_status(trepo.path, annex=False)
    ok_file_under_git(trepo.path, 'test.dat')
    ok_file_under_git(trepo.path, 'INFO.txt')
