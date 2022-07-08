# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

import importlib.util
from io import StringIO as SIO
from pathlib import Path

import pytest

from datalad.tests.utils_pytest import (
    SkipTest,
    assert_in,
    assert_not_in,
    ok_,
    ok_startswith,
)

file_path = \
    Path(__file__).parents[3] / '_datalad_build_support' / 'formatters.py'
if not file_path.exists():
    raise SkipTest(f'Cannot find {file_path}')
spec = importlib.util.spec_from_file_location('formatters', file_path)
fmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fmt)

from ..parser import setup_parser

demo_example = """
#!/bin/sh

set -e
set -u

# BOILERPLATE

HOME=IS_MY_CASTLE

#% EXAMPLE START
#
# A simple start (on the command line)
# ====================================
#
# Lorem ipsum
#%

datalad install http://the.world.com

#%
# Epilog -- with multiline rubish sdoifpwjefw
# vsdokvpsokdvpsdkv spdokvpskdvpoksd
# pfdsvja329u0fjpdsv sdpf9p93qk
#%

datalad imagine --too \\
        --much \\
        --too say \\
        yes=no

datalad shameful-command  #% SKIP
#%
# The result is not comprehensible.
#%

#% EXAMPLE END

# define shunit test cases below, or just anything desired
"""


def test_cmdline_example_to_rst():
    # don't puke on nothing
    out = fmt.cmdline_example_to_rst(SIO(''))
    out.seek(0)
    ok_startswith(out.read(), '.. AUTO-GENERATED')
    out = fmt.cmdline_example_to_rst(SIO(''), ref='dummy')
    out.seek(0)
    assert_in('.. dummy:', out.read())
    # full scale test
    out = fmt.cmdline_example_to_rst(
        SIO(demo_example), ref='mydemo')
    out.seek(0)
    out_text = out.read()
    assert_in('.. code-block:: sh', out_text)
    assert_not_in('shame', out_text)  # no SKIP'ed
    assert_not_in('#', out_text)      # no comments


def test_parser_access():
    parsers = setup_parser(['datalad'], return_subparsers=True)
    # we have a bunch
    ok_(len(parsers) > 3)
    assert_in('install', parsers.keys())


def test_manpage_formatter():
    addonsections = {'mytest': "uniquedummystring"}

    parsers = setup_parser(['datalad'], return_subparsers=True)
    for p in parsers:
        mp = fmt.ManPageFormatter(
            p, ext_sections=addonsections).format_man_page(parsers[p])
        for section in ('SYNOPSIS', 'NAME', 'OPTIONS', 'MYTEST'):
            assert_in('.SH {0}'.format(section), mp)
        assert_in('uniquedummystring', mp)


def test_rstmanpage_formatter():
    parsers = setup_parser(['datalad'], return_subparsers=True)
    for p in parsers:
        mp = fmt.RSTManPageFormatter(p).format_man_page(parsers[p])
        for section in ('Synopsis', 'Description', 'Options'):
            assert_in('\n{0}'.format(section), mp)
        assert_in('{0}\n{1}'.format(p, '=' * len(p)), mp)
