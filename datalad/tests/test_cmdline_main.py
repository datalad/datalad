# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test functioning of the datalad main cmdline utility """

import re
from StringIO import StringIO
from mock import patch

import datalad
from datalad.cmdline.main import main, get_commands
from datalad.tests.utils import assert_equal, ok_, assert_raises

def run_main(args, exit_code=0, expect_stderr=False):
    """Run main() of the datalad, do basic checks and provide outputs

    Parameters
    ----------
    args : list
        List of string cmdline arguments to pass
    exit_code : int
        Expected exit code. Would raise AssertionError if differs
    expect_stderr : bool or string
        Either to expect stderr output. If string -- match

    Returns
    -------
    stdout, stderr  strings
       Output produced
    """
    with patch('sys.stderr', new_callable=StringIO) as cmerr:
        with patch('sys.stdout', new_callable=StringIO) as cmout:
            with assert_raises(SystemExit) as cm:
                main(args)
            assert_equal(cm.exception.code, exit_code)  # exit code must be 0
            stdout = cmout.getvalue()
            stderr = cmerr.getvalue()
            if expect_stderr == False:
                assert_equal(stderr, "")
            elif expect_stderr == True:
                # do nothing -- just return
                pass
            else:
                # must be a string
                assert_equal(stderr, expect_stderr)
    return stdout, stderr


# TODO: switch to stdout for --version output
def test_version():
    stdout, stderr = run_main(['--version'], expect_stderr=True)

    # and output should contain our version, copyright, license
    ok_(stderr.startswith('datalad %s\n' % datalad.__version__))
    ok_("Copyright" in stderr)
    ok_("Permission is hereby granted" in stderr)

def test_get_commands():
    assert('cmd_crawl' in get_commands())
    assert('cmd_install' in get_commands())
    assert('cmd_get' in get_commands())

def test_help():
    stdout, stderr = run_main(['--help'])

    # Let's extract section titles:
    sections = filter(re.compile('[a-zA-Z ]{4,50}:').match, stdout.split('\n'))
    ok_(sections[0].startswith('Usage:'))  # == Usage: nosetests [-h] if running using nose
    assert_equal(sections[1:], ['Positional arguments:', 'Options:'])