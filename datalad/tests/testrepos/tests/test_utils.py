# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for testrepos.utils
"""

from ..repos import *
from ..utils import with_testrepos_new

from datalad.tests.utils import assert_is_instance, assert_raises
from nose.tools import assert_is_not


def test_with_testrepos_new_read_only():

    sometest_repos = []

    @with_testrepos_new(read_only=True)
    def sometest(repo):
        assert_is_instance(repo, TestRepo_NEW)
        sometest_repos.append(repo)

    anothertest_repos = []

    @with_testrepos_new(read_only=True)
    def anothertest(repo):
        assert_is_instance(repo, TestRepo_NEW)
        anothertest_repos.append(repo)

    thirdtest_repos = []

    @with_testrepos_new(read_only=False)
    def thirdtest(repo):
        assert_is_instance(repo, TestRepo_NEW)
        thirdtest_repos.append(repo)

    @with_testrepos_new(read_only=True)
    def messuptest(repo):
        # we can't test every possible way to mess up and furthermore this test
        # isn't about testing assert_intact. So, just let assert_intact fail:
        def fake():
            raise AssertionError

        repo.assert_intact = fake

    # they got all TestRepo classes:
    sometest()
    assert any(isinstance(x, BasicGit) for x in sometest_repos)
    assert any(isinstance(x, BasicMixed) for x in sometest_repos)
    assert any(isinstance(x, MixedSubmodulesOldOneLevel) for x in sometest_repos)
    assert any(isinstance(x, MixedSubmodulesOldNested) for x in sometest_repos)

    # next test gets the very same objects:
    anothertest()
    assert all(any(a is b for b in anothertest_repos) for a in sometest_repos)

    # third test gets its own instances:
    thirdtest()
    assert all(not any(a is b for b in thirdtest_repos) for a in sometest_repos)

    # messuptest fails:
    assert_raises(AssertionError, messuptest)

    # Note, that due to the failing of messuptest, it was executed only for the
    # first testrepo delivered to it.
    # This one should be replaced and therefore the next test gets a new
    # instance, while the others are still the same:
    anothertest_repos = []
    anothertest()
    assert all(any(a is b for b in anothertest_repos[1:])
               for a in sometest_repos[1:])
    assert_is_not(anothertest_repos[0], sometest_repos[0])
    eq_(anothertest_repos[0].__class__, sometest_repos[0].__class__)
    # but they are at the same location as before, so they will be reused
    # further on:
    eq_(anothertest_repos[0].path, sometest_repos[0].path)


def test_with_testrepos_new_selector():
    pass


def test_with_testrepos_new_known_failure():
    pass

