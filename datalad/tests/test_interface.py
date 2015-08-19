# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test command call wrapper
"""

from nose.tools import assert_is, assert_equal, assert_true, assert_raises

from datalad.support.param import Parameter
import datalad.support.constraints as cnstr
from datalad.interface.base import Interface


class Demo(Interface):
    """I am a demo"""
    _params_ = dict(

        demoposarg=Parameter(
            doc="demoposdoc",
            constraints=cnstr.EnsureInt(),
            nargs=2),

        demooptposarg1=Parameter(
            args=('demooptposarg1',),
            doc="demooptposdoc1",
            constraints=cnstr.EnsureInt(),
            nargs='?'),

        demooptposarg2=Parameter(
            args=('demooptposarg2',),
            doc="demooptposdoc2",
            constraints=cnstr.EnsureInt(),
            nargs='?'),

        demoarg=Parameter(
            doc="demodoc",
            constraints=cnstr.EnsureInt()))

    def __call__(self, demoposarg, demooptposarg1=99, demooptposarg2=999, demoarg=100):
        return demoarg


def test_param():
    # having a parametr with no information is fine
    # it doesn't need a name, because it comes from the signatur
    # of the actual implementation that is described
    p = Parameter()
    pname = 'testname'
    # minimal docstring
    assert_equal(pname, p.get_autodoc('testname'))
    doc = 'somedoc'
    p = Parameter(doc=doc)
    assert_equal('%s\n  %s.' % (pname, doc), p.get_autodoc('testname'))
    # constraints
    p = Parameter(doc=doc, constraints=cnstr.EnsureInt() | cnstr.EnsureStr())
    autodoc = p.get_autodoc('testname')
    assert_true("convertible to type 'int'" in autodoc)
    assert_true('must be a string' in autodoc)
    assert_true('int or str' in autodoc)


def test_interface():
    di = Demo()

    import argparse
    parser = argparse.ArgumentParser()

    di.setup_parser(parser)
    print(parser.print_help())
    args = parser.parse_args(['42', '11', '1', '2', '--demoarg', '23'])
    assert_is(args.demoarg, 23)
    assert_equal(args.demoposarg, [42, 11])
    assert_equal(args.demooptposarg1, 1)
    assert_equal(args.demooptposarg2, 2)

    # wrong type
    assert_raises(SystemExit, parser.parse_args, ['--demoarg', 'abc'])
    # missing argument to option
    assert_raises(SystemExit, parser.parse_args, ['--demoarg'])
    # missing positional argument
    assert_raises(SystemExit, parser.parse_args, [''])
