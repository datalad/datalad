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
import sys
from six.moves import StringIO
from mock import patch

import datalad
from ..main import main
from datalad import __version__
from datalad.cmd import Runner
from datalad.tests.utils import assert_equal, assert_raises, in_, ok_startswith
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_re_in
from datalad.tests.utils import assert_not_in


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
            if expect_stderr is False:
                assert_equal(stderr, "")
            elif expect_stderr is True:
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

    # https://hg.python.org/cpython/file/default/Doc/whatsnew/3.4.rst#l1952
    out = stdout if sys.version_info >= (3, 4) else stderr
    ok_startswith(out, 'datalad %s\n' % datalad.__version__)
    in_("Copyright", out)
    in_("Permission is hereby granted", out)


def test_help_np():
    stdout, stderr = run_main(['--help-np'])

    # Let's extract section titles:
    # enough of bin/datalad and .tox/py27/bin/datalad -- guarantee consistency! ;)
    ok_startswith(stdout, 'Usage: datalad')
    # Sections start/end with * if ran under DATALAD_HELP2MAN mode
    sections = [l[1:-1] for l in filter(re.compile('^\*.*\*$').match, stdout.split('\n'))]
    # but order is still not guaranteed (dict somewhere)! TODO
    # see https://travis-ci.org/datalad/datalad/jobs/80519004
    # thus testing sets
    assert_equal(set(sections),
                 {'Commands for dataset operations',
                  'Commands for meta data handling',
                  'Miscellaneous commands',
                  'General information',
                  'Global options',
                  'Plumbing commands'})

    # none of the lines must be longer than 80 chars
    # TODO: decide on   create-sibling and possibly
    # rewrite-urls
    import shutil
    accepted_width = shutil.get_terminal_size()[0] \
        if hasattr(shutil, 'get_terminal_size') else 80

    long_lines = ["%d %s" % (len(l), l) for l in stdout.split('\n')
                  if len(l) > accepted_width and
                  '{' not in l  # on nd70 summary line is unsplit
                  ]
    if long_lines:
        raise AssertionError(
            "Following lines in --help output were longer than %s chars:\n%s"
            % (accepted_width, '\n'.join(long_lines))
        )


def test_usage_on_insufficient_args():
    stdout, stderr = run_main(['install'], exit_code=2, expect_stderr=True)
    ok_startswith(stderr, 'usage:')


def test_subcmd_usage_on_unknown_args():
    stdout, stderr = run_main(['get', '--murks'], exit_code=1)
    in_('get', stdout)


def check_incorrect_option(opts, err_str):
    # The first line used to be:
    # stdout, stderr = run_main((sys.argv[0],) + opts, expect_stderr=True, exit_code=2)
    # But: what do we expect to be in sys.argv[0] here?
    # It depends on how we invoke the test.
    # - nosetests -s -v datalad/cmdline/tests/test_main.py would result in:
    #   sys.argv[0}=='nosetests'
    # - python -m nose -s -v datalad/cmdline/tests/test_main.py would result in:
    #   sys.argv[0}=='python -m nose'
    # - python -c "import nose; nose.main()" -s -v datalad/cmdline/tests/test_main.py would result in:
    #   sys.argv[0]=='-c'
    # This led to failure in case sys.argv[0] contained an option, that was
    # defined to be a datalad option too, therefore was a 'known_arg' and was
    # checked to meet its constraints.
    # But sys.argv[0] actually isn't used by main at all. It simply doesn't
    # matter what's in there. The only thing important to pass here is `opts`.
    stdout, stderr = run_main(('datalad',) + opts, expect_stderr=True, exit_code=2)
    out = stdout + stderr
    assert_in("usage: ", out)
    assert_re_in(err_str, out, match=False)


def test_incorrect_options():
    # apparently a bit different if following a good one so let's do both
    err_invalid = "error: (invalid|too few arguments)"
    yield check_incorrect_option, ('--buga',), err_invalid
    yield check_incorrect_option, ('--dbg', '--buga'), err_invalid

    err_insufficient = err_invalid # "specify"
    yield check_incorrect_option, ('--dbg',), err_insufficient
    yield check_incorrect_option, tuple(), err_insufficient

def test_script_shims():
    runner = Runner()
    for script in [
        'datalad',
        'git-annex-remote-datalad-archives',
        'git-annex-remote-datalad']:
        # those must be available for execution, and should not contain
        which, _ = runner(['which', script])
        # test if there is no easy install shim in there
        with open(which.rstrip()) as f:
            content = f.read()
        assert_not_in('EASY', content) # NOTHING easy should be there
        assert_not_in('pkg_resources', content)

        # and let's check that it is our script
        out, err = runner([script, '--version'])
        version = (out + err).splitlines()[0].split(' ', 1)[1]
        # we can get git and non git .dev version... so for now
        # relax
        get_numeric_portion = lambda v: [x for x in v.split('.') if x.isdigit()]
        # extract numeric portion
        assert get_numeric_portion(version) # that my lambda is correctish
        assert_equal(get_numeric_portion(__version__),
                     get_numeric_portion(version))