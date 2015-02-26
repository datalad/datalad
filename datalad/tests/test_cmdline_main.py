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

# TODO: switch to stdout for --version output
# TODO: provide ultimate decorator  @run_main(args, exit_code) which would run
#       main command, check exit_code and ship stdout, stderr into the test
@patch('sys.stderr', new_callable=StringIO)
def test_version(stdout):
    with assert_raises(SystemExit) as cm:
        main(['--version'])
    assert_equal(cm.exception.code, 0)  # exit code must be 0

    # and output should contain our version, copyright, license
    stdout = stdout.getvalue()
    ok_(stdout.startswith('datalad %s\n' % datalad.__version__))
    ok_("Copyright" in stdout)
    ok_("Permission is hereby granted" in stdout)

def test_get_commands():
    assert('cmd_crawl' in get_commands())

@patch('sys.stdout', new_callable=StringIO)
def test_help(stdout):
    with assert_raises(SystemExit) as cm:
        main(['--help'])
    assert_equal(cm.exception.code, 0)  # exit code must be 0

    stdout = stdout.getvalue()
    # Let's extract section titles:
    sections = filter(re.compile('[a-zA-Z ]*:').match, stdout.split('\n'))
    ok_(sections[0].startswith('Usage:')) # == Usage: nosetests [-h] if running using nose
    assert_equal(sections[1:], ['Positional arguments:', 'Options:'])