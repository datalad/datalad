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

import re
from nose.tools import assert_is, assert_equal, assert_raises, assert_true

from ..support.param import Parameter
from ..support import constraints as cnstr
from ..interface.base import Interface, get_api_name, get_cmdline_command_name

from ..utils import swallow_outputs
from .utils import assert_re_in
from .utils import assert_in


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

    with assert_raises(ValueError) as cmr:
        Parameter(unknown_arg=123)
    assert_in('Detected unknown argument(s) for the Parameter: unknown_arg',
              str(cmr.exception))


def test_interface():
    di = Demo()

    import argparse
    parser = argparse.ArgumentParser()

    di.setup_parser(parser)
    with swallow_outputs() as cmo:
        assert_equal(parser.print_help(), None)
        assert(cmo.out)
        assert_equal(cmo.err, '')
    args = parser.parse_args(['42', '11', '1', '2', '--demoarg', '23'])
    assert_is(args.demoarg, 23)
    assert_equal(args.demoposarg, [42, 11])
    assert_equal(args.demooptposarg1, 1)
    assert_equal(args.demooptposarg2, 2)

    # wrong type
    with swallow_outputs() as cmo:
        assert_raises(SystemExit, parser.parse_args, ['--demoarg', 'abc'])
        # that is what we dump upon folks atm. TODO: improve reporting of illspecified options
        assert_re_in(".*invalid constraint:int value:.*",
                     cmo.err, re.DOTALL)

    # missing argument to option
    with swallow_outputs() as cmo:
        assert_raises(SystemExit, parser.parse_args, ['--demoarg'])
        assert_re_in(".*--demoarg: expected one argument", cmo.err, re.DOTALL)

    # missing positional argument
    with swallow_outputs() as cmo:
        assert_raises(SystemExit, parser.parse_args, [''])
        # PY2|PY3
        assert_re_in(".*error: (too few arguments|the following arguments are required: demoposarg)",
                     cmo.err, re.DOTALL)


def test_name_generation():
    assert_equal(
        get_api_name(("some.module", "SomeClass")),
        'module')
    assert_equal(
        get_api_name(("some.module", "SomeClass", "cmdline-override")),
        'module')
    assert_equal(
        get_api_name(("some.module",
                      "SomeClass",
                      "cmdline_override",
                      "api_override-dont-touch")),
        "api_override-dont-touch")
    assert_equal(
        get_cmdline_command_name(("some.module_something", "SomeClass")),
        "module-something")
    assert_equal(
        get_cmdline_command_name((
            "some.module_something",
            "SomeClass",
            "override")),
        "override")
    assert_equal(
        get_cmdline_command_name((
            "some.module_something",
            "SomeClass",
            "override",
            "api_ignore")),
        "override")
