# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import sys

from unittest.mock import patch
from io import StringIO
from datalad.tests.utils import (
    assert_equal,
    assert_raises,
)

from .. import __main__, __version__


@patch('sys.stdout', new_callable=StringIO)
def test_main_help(stdout):
    assert_raises(SystemExit, __main__.main, ['__main__.py', '--help'])
    assert(
        stdout.getvalue().startswith(
        "Usage: %s -m datalad [OPTIONS] <file> [ARGS]\n" % sys.executable
    ))

@patch('sys.stdout', new_callable=StringIO)
def test_main_version(stdout):
    assert_raises(SystemExit, __main__.main, ['__main__.py', '--version'])
    assert_equal(stdout.getvalue().rstrip(), "datalad %s" % __version__)
