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


from six import string_types

from functools import wraps
from ..repos import *
from ..utils import with_testrepos_new, _all_setups

from datalad.tests.utils import assert_is_instance, assert_raises, with_tempfile, swallow_outputs
from nose.tools import assert_is_not, assert_not_in


@with_testrepos_new(read_only=True)
@with_tempfile
def test_with_testrepos_yields(repo, path):
    # this is a somewhat crippled test.
    # It should result in nose executing parametric tests (one per each
    # TestRepo delivered)
    # ATM this is just for seeing this happen "manually" when looking at nose's
    # output
    assert isinstance(repo, TestRepo_NEW)
    assert isinstance(path, string_types)


def test_with_testrepos_new_read_only():

    # Note: Calls to the "tests" look a bit weird, since with_testrepos_new
    # is yielding parametric tests to be discovered and executed by nose. We
    # need to simulate the "outside" point of view of nose here.

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
    [x[0](*(x[1:])) for x in sometest()]
    assert all(any(isinstance(x, cls) for x in sometest_repos)
               for cls in _all_setups)

    # next test gets the very same objects:
    [x[0](*(x[1:])) for x in anothertest()]
    assert all(any(a is b for b in anothertest_repos) for a in sometest_repos)

    # third test gets its own instances:
    [x[0](*(x[1:])) for x in thirdtest()]
    assert all(not any(a is b for b in thirdtest_repos) for a in sometest_repos)

    # messuptest fails:
    with assert_raises(AssertionError):
        [x[0](*(x[1:])) for x in messuptest()]

    # Note, that due to the failing of messuptest, it was executed only for the
    # first testrepo delivered to it.
    # This one should be replaced and therefore the next test gets a new
    # instance, while the others are still the same:
    anothertest_repos = []
    [x[0](*(x[1:])) for x in anothertest()]
    assert all(any(a is b for b in anothertest_repos[1:])
               for a in sometest_repos[1:])
    assert_is_not(anothertest_repos[0], sometest_repos[0])
    eq_(anothertest_repos[0].__class__, sometest_repos[0].__class__)
    # but they are at the same location as before, so they will be reused
    # further on:
    eq_(anothertest_repos[0].path, sometest_repos[0].path)


def test_with_testrepos_new_selector():

    # Note: Calls to the "tests" look a bit weird, since with_testrepos_new
    # is yielding parametric tests to be discovered and executed by nose. We
    # need to simulate the "outside" point of view of nose here.

    sometest_repos = []

    @with_testrepos_new(read_only=True)
    def sometest(repo):
        assert_is_instance(repo, TestRepo_NEW)
        sometest_repos.append(repo)

    someothertest_repos = []

    @with_testrepos_new(read_only=True, selector=[('all',)])
    def someothertest(repo):
        assert_is_instance(repo, TestRepo_NEW)
        someothertest_repos.append(repo)

    additionaltest_repos = []

    @with_testrepos_new(read_only=True, selector=[(BasicGit,), (BasicMixed,)])
    def additionaltest(repo):
        assert_is_instance(repo, TestRepo_NEW)
        additionaltest_repos.append(repo)

    # sometest got all TestRepo classes:
    [x[0](*(x[1:])) for x in sometest()]
    assert all(any(isinstance(x, cls) for x in sometest_repos)
               for cls in _all_setups)

    # someothertest got all TestRepo classes:
    [x[0](*(x[1:])) for x in someothertest()]
    assert all(any(isinstance(x, cls) for x in someothertest_repos)
               for cls in _all_setups)

    # additionaltest got just BasicGit and BasicMixed:
    [x[0](*(x[1:])) for x in additionaltest()]
    assert all(any(isinstance(x, cls) for x in additionaltest_repos)
               for cls in [BasicGit, BasicMixed])


def test_with_testrepos_new_decorators():

    def first_decorator(t):
        @wraps(t)
        def newfunc(*arg, **kw):
            print("first_decorator called")
            return t(*arg, **kw)
        return newfunc

    def second_decorator(t):
        @wraps(t)
        def newfunc(*arg, **kw):
            print("second_decorator called")
            return t(*arg, **kw)
        return newfunc

    @with_testrepos_new(read_only=True,
                        selector=[
                            # this is making first_decorator the default for all
                            # test setups and simultaneously making sure all of
                            # them are used with this test ('sometest'):
                            ('all', first_decorator),
                            # now, this overrides the decorator for the
                            # invocation using BasicGit:
                            (BasicGit, second_decorator),
                            # this one is passing a stack of decorators:
                            # Note, that just first_decorator(second_decorator)
                            # wouldn't work as expected! This is somewhat hard
                            # to get one's head around, since we are passing a
                            # callable into a decorator which is then using it
                            # inside the function it is supposed to return to
                            # decorate the function it is decorating itself.
                            # This leads to easy confusion of what happens
                            # during "compile" time and run time.
                            # So, just note: That's the way you can do it.
                            (BasicMixed, lambda x: first_decorator(second_decorator(x))),
                            # and finally this one shouldn't do anything, since
                            # there is no decorator passed to override the
                            # default one:
                            (MixedSubmodulesOldOneLevel,)
                                  ]
                        )
    def sometest(repo):
        print("sometest called with %s: " % repo.__class__.__name__)

    # calling sometest now, should lead to the test being executed with all
    # available test setups, but differently decorated:
    # All invocations should call the first decorator by default with the
    # following exceptions:
    # - invocation with BasicGit should call second decorator instead
    # - invocation with BasicMixed should call first_decorator and
    #   second_decorator

    for x in sometest():
        with swallow_outputs() as cmo:
            x[0](*(x[1:]))

            assert_in("sometest called with %s:" % x[1].__class__.__name__,
                      cmo.out)

            if x[1].__class__ == BasicGit:
                assert_in("second_decorator called", cmo.out)
                assert_not_in("first_decorator called", cmo.out)
            elif x[1].__class__ == BasicMixed:
                # note, that this is testing for correct order of execution:
                assert_in("first_decorator called\nsecond_decorator called", cmo.out)
            else:
                assert_not_in("second_decorator called", cmo.out)
                assert_in("first_decorator called", cmo.out)


