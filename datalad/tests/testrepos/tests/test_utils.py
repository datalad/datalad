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


import logging
from six import string_types
from nose import SkipTest
from nose.tools import assert_is_not
from functools import wraps

from datalad.tests.utils import assert_is_instance
from datalad.tests.utils import assert_raises
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import assert_not_in

from ..repos import *
from ..utils import with_testrepos_new, _all_setups


lgr = logging.getLogger('datalad.tests.testrepos.test_utils')


@with_testrepos_new(read_only=True)
@with_tempfile
def test_with_testrepos_yields(repo, path):
    # this is a somewhat crippled test.
    # It should result in nose executing parametric tests (one per each
    # TestRepo delivered)
    # ATM this is just for seeing this happen "manually" when looking at nose's
    # output
    assert_is_instance(repo, TestRepo_NEW)
    assert_is_instance(path, string_types)


def test_with_testrepos_new_read_only():

    # Note: Calls to the "tests" look a bit weird, since with_testrepos_new
    # is yielding parametric tests to be discovered and executed by nose. We
    # need to simulate the "outside" point of view of nose here. This also leads
    # to the need of catching possible SkipTest exceptions, that may be raised
    # when building MixedSubmodulesOld* in annex V6 mode for example.
    # This is why we call those decorated test functions like:
    #
    # for x in sometest():
    #     try:
    #         x[0](*(x[1:])
    #     except SkipTest
    #        ...

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
    all_classes = set(_all_setups)
    for x in sometest():
        try:
            x[0](*(x[1:]))
        except SkipTest as e:
            lgr.debug("Skipped sometest() with %s:\n%s" % (x[1:], str(e)))
            all_classes.remove(x[1])

    assert all(any(isinstance(x, cls) for x in sometest_repos)
               for cls in all_classes)

    # next test gets the very same objects:
    for x in anothertest():
        try:
            x[0](*(x[1:]))
        except SkipTest as e:
            lgr.debug("Skipped anothertest() with %s:\n%s" % (x[1:], str(e)))

    assert all(any(a is b for b in anothertest_repos) for a in sometest_repos)

    # third test gets its own instances:
    for x in thirdtest():
        try:
            x[0](*(x[1:]))
        except SkipTest as e:
            lgr.debug("Skipped thirdtest() with %s:\n%s" % (x[1:], str(e)))
    assert all(not any(a is b for b in thirdtest_repos) for a in sometest_repos)

    # messuptest fails:
    #
    # Note: This test is somewhat incomplete, since AssertionError will be
    # raised by the first yielded function, not considering the remaining ones.
    # For now, didn't find a way to write a proper test, that is in addition
    # also accounting for possible SkipTest raised. Due to the way the generator
    # works (with_testrepo_new) the AssertionError would be raised only, when
    # the next function is yielded. So, assertions herein would be
    # "phase shifted".
    # Proper test probably needs to look similar to the following code, but
    # couldn't figure it out entirely yet:
    # g = messuptest()
    # x = g.next()
    # while True:
    #     lgr.debug("Calling with %s" % x[1:])
    #     try:
    #         x[0](*(x[1:]))
    #     except SkipTest as e:
    #         lgr.debug("Skipped messuptest() with %s:\n%s" % (x[1:], str(e)))
    #     try:
    #         lgr.debug("Yielding next")
    #         with assert_raises(AssertionError):
    #             x = g.next()
    #     except StopIteration:
    #         break

    with assert_raises(AssertionError):
        [x[0](*(x[1:])) for x in messuptest()]

    # Note, that due to the failing of messuptest, it was executed only for the
    # first testrepo delivered to it.
    # This one should be replaced and therefore the next test gets a new
    # instance, while the others are still the same:
    anothertest_repos = []
    for x in anothertest():
        try:
            x[0](*(x[1:]))
        except SkipTest as e:
            lgr.debug("Skipped anothertest() with %s:\n%s" % (x[1:], str(e)))

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

    all_classes = set(_all_setups)
    for x in sometest():
        try:
            x[0](*(x[1:]))
        except SkipTest as e:
            lgr.debug("Skipped sometest() with %s:\n%s" % (x[1:], str(e)))
            all_classes.remove(x[1])

    assert all(any(isinstance(x, cls) for x in sometest_repos)
               for cls in all_classes)

    # someothertest got all TestRepo classes:
    all_classes = set(_all_setups)
    for x in someothertest():
        try:
            x[0](*(x[1:]))
        except SkipTest as e:
            lgr.debug("Skipped someothertest() with %s:\n%s" % (x[1:], str(e)))
            all_classes.remove(x[1])

    assert all(any(isinstance(x, cls) for x in someothertest_repos)
               for cls in all_classes)

    # additionaltest got just BasicGit and BasicMixed:
    for x in additionaltest():
        try:
            x[0](*(x[1:]))
        except SkipTest as e:
            lgr.debug("Skipped additionaltest() with %s:\n%s" % (x[1:], str(e)))

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
            try:
                x[0](*(x[1:]))
            except SkipTest as e:
                lgr.debug("Skipped sometest() with %s:\n%s" % (x[1:], str(e)))
                continue

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


