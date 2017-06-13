# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import sys

from mock import patch
from six.moves import StringIO
from tempfile import NamedTemporaryFile
from nose.tools import assert_raises, assert_equal

from .. import __main__, __version__
from ..auto import AutomagicIO


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

@patch.object(AutomagicIO, 'activate')
@patch('sys.stdout', new_callable=StringIO)
def test_main_run_a_script(stdout, mock_activate):
    f = NamedTemporaryFile()
    f.write('print("Running the script")\n'.encode()); f.flush()
    __main__.main(['__main__.py', f.name])
    assert_equal(stdout.getvalue().rstrip(), "Running the script")
    # And we have "activated"
    mock_activate.assert_called_once_with()
