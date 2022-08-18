# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for dochelpers (largely copied from PyMVPA, the same copyright)
"""

from unittest.mock import patch

from datalad.tests.utils_pytest import (
    assert_equal,
    assert_re_in,
    assert_true,
)

from ..dochelpers import (
    borrowdoc,
    borrowkwargs,
    single_or_plural,
)


def test_basic():
    assert_equal(single_or_plural('a', 'b', 1), 'a')
    assert_equal(single_or_plural('a', 'b', 0), 'b')
    assert_equal(single_or_plural('a', 'b', 123), 'b')
    assert_equal(single_or_plural('a', 'b', 123, include_count=True), '123 b')


def test_borrow_doc():

    class A(object):
        def met1(self):
            """met1doc"""
            pass  # pragma: no cover
        def met2(self):
            """met2doc"""
            pass  # pragma: no cover

    class B(object):
        @borrowdoc(A)
        def met1(self):
            pass  # pragma: no cover
        @borrowdoc(A, 'met1')
        def met2(self):
            pass  # pragma: no cover

    assert_equal(B.met1.__doc__, A.met1.__doc__)
    assert_equal(B.met2.__doc__, A.met1.__doc__)


def test_borrow_kwargs():

    class A(object):
        def met1(self, kp1=None, kp2=1):
            """met1 doc

            Parameters
            ----------
            kp1 : None or int
              keyword parameter 1
            kp2 : int, optional
              something
            """
            pass  # pragma: no cover

        def met2(self):
            """met2doc"""
            pass  # pragma: no cover

    class B(object):

        @borrowkwargs(A)
        def met1(self, desc, **kwargs):
            """B.met1 doc

            Parameters
            ----------
            desc
              description
            **kwargs
              Same as in A.met1

            Some postamble
            """
            pass  # pragma: no cover

        @borrowkwargs(A, 'met1')
        def met_nodoc(self, **kwargs):
            pass  # pragma: no cover

        @borrowkwargs(methodname=A.met1)
        def met_anothermet(self, **kwargs):
            pass  # pragma: no cover

        @borrowkwargs(A, 'met1')
        def met_nodockwargs(self, bogus=None, **kwargs):
            """B.met_nodockwargs

            Parameters
            ----------
            bogus
              something
            """
            pass  # pragma: no cover

        if True:
            # Just so we get different indentation level
            @borrowkwargs(A, 'met1', ['kp1'])
            def met_excludes(self, boguse=None, **kwargs):
                """B.met_excludes

                Parameters
                ----------
                boguse
                  something
                """
                pass  # pragma: no cover

    assert_true('B.met1 doc' in B.met1.__doc__)
    for m in (B.met1,
              B.met_nodoc,
              B.met_anothermet,
              B.met_nodockwargs,
              B.met_excludes):
        docstring = m.__doc__
        assert_true('Parameters' in docstring)
        assert_true(not '*kwargs' in docstring,
            msg="We shouldn't carry kwargs in docstring now,"
                "Got %r for %s" % (docstring, m))
        assert_true('kp2 ' in docstring)
        assert_true((('kp1 ' in docstring)
                             ^ (m == B.met_excludes)))
        # indentation should have been squashed properly
        assert_true(not '   ' in docstring)

    # some additional checks to see if we are not losing anything
    assert_true('Some postamble' in B.met1.__doc__)
    assert_true('B.met_nodockwargs' in B.met_nodockwargs.__doc__)
    assert_true('boguse' in B.met_excludes.__doc__)
