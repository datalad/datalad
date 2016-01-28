# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for dochelpers (largely copied from PyMVPA, the same copyright)
"""

import os
from mock import patch

from ..dochelpers import single_or_plural, borrowdoc, borrowkwargs
from ..dochelpers import exc_str

from .utils import assert_equal, assert_true
from .utils import assert_re_in

def test_basic():
    assert_equal(single_or_plural('a', 'b', 1), 'a')
    assert_equal(single_or_plural('a', 'b', 0), 'b')
    assert_equal(single_or_plural('a', 'b', 123), 'b')


def test_borrow_doc():

    class A(object):
        def met1(self):
            """met1doc"""
            pass
        def met2(self):
            """met2doc"""
            pass

    class B(object):
        @borrowdoc(A)
        def met1(self):
            pass
        @borrowdoc(A, 'met1')
        def met2(self):
            pass

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
            pass

        def met2(self):
            """met2doc"""
            pass

    class B(object):

        @borrowkwargs(A)
        def met1(self, bu, **kwargs):
            """B.met1 doc

            Parameters
            ----------
            bu
              description
            **kwargs
              Same as in A.met1

            Some postamble
            """
            pass

        @borrowkwargs(A, 'met1')
        def met_nodoc(self, **kwargs):
            pass

        @borrowkwargs(A, 'met1')
        def met_nodockwargs(self, bogus=None, **kwargs):
            """B.met_nodockwargs

            Parameters
            ----------
            bogus
              something
            """
            pass

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
                pass

    assert_true('B.met1 doc' in B.met1.__doc__)
    for m in (B.met1,
              B.met_nodoc,
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

    # some additional checks to see if we are not loosing anything
    assert_true('Some postamble' in B.met1.__doc__)
    assert_true('B.met_nodockwargs' in B.met_nodockwargs.__doc__)
    assert_true('boguse' in B.met_excludes.__doc__)

def test_exc_str():
    try:
        raise Exception("my bad")
    except Exception as e:
        estr = exc_str(e)
    assert_re_in("my bad \[test_dochelpers.py:test_exc_str:...\]", estr)

    def f():
        def f2():
            raise Exception("my bad again")
        f2()
    try:
        f()
    except Exception as e:
        # default one:
        estr2 = exc_str(e, 2)
        estr1 = exc_str(e, 1)
        # and we can control it via environ by default
        with patch.dict('os.environ', {'DATALAD_EXC_STR_TBLIMIT': '3'}):
            estr3 = exc_str(e)
        with patch.dict('os.environ', {}, clear=True):
            estr_ = exc_str()

    assert_re_in("my bad again \[test_dochelpers.py:test_exc_str:...,test_dochelpers.py:f:...,test_dochelpers.py:f2:...\]", estr3)
    assert_re_in("my bad again \[test_dochelpers.py:f:...,test_dochelpers.py:f2:...\]", estr2)
    assert_re_in("my bad again \[test_dochelpers.py:f2:...\]", estr1)
    assert_equal(estr_, estr1)