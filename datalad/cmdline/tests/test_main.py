# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test functioning of the datalad main cmdline utility """

import os
import re
from io import StringIO
from unittest.mock import patch

import datalad
from datalad import __version__
from datalad.api import (
    Dataset,
    create,
)
from datalad.cmd import StdOutErrCapture
from datalad.cmd import WitlessRunner as Runner
from datalad.support.exceptions import CommandError
from datalad.tests.utils import (
    SkipTest,
    assert_equal,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_re_in,
    eq_,
    in_,
    ok_startswith,
    on_windows,
    slow,
    with_tempfile,
)
from datalad.ui.utils import (
    get_console_width,
    get_terminal_size,
)
from datalad.utils import (
    Path,
    chpwd,
)

from ..helpers import fail_with_short_help
from ..main import (
    main,
)


def run_main(args, exit_code=0, expect_stderr=False):
    """Run main() of the datalad, do basic checks and provide outputs

    Parameters
    ----------
    args : list
        List of string cmdline arguments to pass
    exit_code : int
        Expected exit code. Would raise AssertionError if differs
    expect_stderr : bool or string
        Whether to expect stderr output. If string -- match

    Returns
    -------
    stdout, stderr  strings
       Output produced
    """
    with patch('sys.stderr', new_callable=StringIO) as cmerr:
        with patch('sys.stdout', new_callable=StringIO) as cmout:
            with assert_raises(SystemExit) as cm:
                main(["datalad"] + list(args))
            assert_equal(cm.exception.code, exit_code)
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
    # we just get a version if not asking for a version of some command
    stdout, stderr = run_main(['--version'], expect_stderr=True)
    eq_(stdout.rstrip(), "datalad %s" % datalad.__version__)

    stdout, stderr = run_main(['clone', '--version'], expect_stderr=True)
    ok_startswith(stdout, 'datalad %s\n' % datalad.__version__)
    # since https://github.com/datalad/datalad/pull/2733 no license in --version
    assert_not_in("Copyright", stdout)
    assert_not_in("Permission is hereby granted", stdout)

    try:
        import datalad_container
    except ImportError:
        pass  # not installed, cannot test with extension
    else:
        stdout, stderr = run_main(['containers-list', '--version'], expect_stderr=True)
        eq_(stdout, 'datalad_container %s\n' % datalad_container.__version__)


def test_help_np():
    stdout, stderr = run_main(['--help-np'])

    # Let's extract section titles:
    # enough of bin/datalad and .tox/py27/bin/datalad -- guarantee consistency! ;)
    ok_startswith(stdout, 'Usage: datalad')
    # Sections start/end with * if ran under DATALAD_HELP2MAN mode
    sections = [l[1:-1] for l in filter(re.compile(r'^\*.*\*$').match, stdout.split('\n'))]
    # but order is still not guaranteed (dict somewhere)! TODO
    # see https://travis-ci.org/datalad/datalad/jobs/80519004
    # thus testing sets
    for s in {'Commands for dataset operations',
              'Commands for metadata handling',
              'Miscellaneous commands',
              'General information',
              'Global options',
              'Plumbing commands',
              }:
        assert_in(s, sections)
        # should be present only one time!
        eq_(stdout.count(s), 1)

    if not get_terminal_size()[0] or 0:
        raise SkipTest(
            "Could not determine terminal size, skipping the rest of the test")

    # none of the lines must be longer than 80 chars
    # TODO: decide on   create-sibling and possibly
    # rewrite-urls
    accepted_width = get_console_width()

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
    stdout, stderr = run_main(['get', '--murks'], exit_code=1, expect_stderr=True)
    in_('get', stdout)


def test_combined_short_option():
    stdout, stderr = run_main(['-fjson'], exit_code=2, expect_stderr=True)
    assert_not_in("unrecognized argument", stderr)
    assert_in("too few arguments", stderr)


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
    stdout, stderr = run_main(opts, expect_stderr=True, exit_code=2)
    out = stdout + stderr
    assert_in("usage: ", out)
    assert_re_in(err_str, out, match=False)


def test_incorrect_options():
    # apparently a bit different if following a good one so let's do both
    err_invalid = "error: (invalid|too few arguments|unrecognized argument)"
    yield check_incorrect_option, ('--buga',), err_invalid
    yield check_incorrect_option, ('--dbg', '--buga'), err_invalid

    err_insufficient = err_invalid  # "specify"
    yield check_incorrect_option, ('--dbg',), err_insufficient
    yield check_incorrect_option, tuple(), err_insufficient


def test_script_shims():
    runner = Runner()
    for script in [
        'datalad',
        'git-annex-remote-datalad-archives',
        'git-annex-remote-datalad']:

        from shutil import which
        which(script)

        # and let's check that it is our script
        out = runner.run([script, '--version'], protocol=StdOutErrCapture)
        version = out['stdout'].rstrip()
        mod, version = version.split(' ', 1)
        assert_equal(mod, 'datalad')
        # we can get git and non git .dev version... so for now
        # relax
        get_numeric_portion = lambda v: [x for x in re.split('[+.]', v) if x.isdigit()]
        # extract numeric portion
        assert get_numeric_portion(version), f"Got no numeric portion from {version}"
        assert_equal(get_numeric_portion(__version__),
                     get_numeric_portion(version))


@slow  # 11.2591s
@with_tempfile(mkdir=True)
def test_cfg_override(path):
    with chpwd(path):
        cmd = ['datalad', 'wtf', '-s', 'some']
        # control
        out = Runner().run(cmd, protocol=StdOutErrCapture)['stdout']
        assert_not_in('datalad.dummy: this', out)
        # ensure that this is not a dataset's cfg manager
        assert_not_in('datalad.dataset.id', out)
        # env var
        out = Runner(env=dict(os.environ, DATALAD_DUMMY='this')).run(
            cmd, protocol=StdOutErrCapture)['stdout']
        assert_in('datalad.dummy: this', out)
        # cmdline arg
        out = Runner().run([cmd[0], '-c', 'datalad.dummy=this'] + cmd[1:],
                           protocol=StdOutErrCapture)['stdout']
        assert_in('datalad.dummy: this', out)

        # now create a dataset in the path. the wtf plugin will switch to
        # using the dataset's config manager, which must inherit the overrides
        create(dataset=path)
        # control
        out = Runner().run(cmd, protocol=StdOutErrCapture)['stdout']
        assert_not_in('datalad.dummy: this', out)
        # ensure that this is a dataset's cfg manager
        assert_in('datalad.dataset.id', out)
        # env var
        out = Runner(env=dict(os.environ, DATALAD_DUMMY='this')).run(
            cmd, protocol=StdOutErrCapture)['stdout']
        assert_in('datalad.dummy: this', out)
        # cmdline arg
        out = Runner().run([cmd[0], '-c', 'datalad.dummy=this'] + cmd[1:],
                           protocol=StdOutErrCapture)['stdout']
        assert_in('datalad.dummy: this', out)


def test_incorrect_cfg_override():
    run_main(['-c', 'some', 'wtf'], exit_code=3)
    run_main(['-c', 'some=', 'wtf'], exit_code=3)
    run_main(['-c', 'some.var', 'wtf'], exit_code=3)
    run_main(['-c', 'some.var=', 'wtf'], exit_code=3)


def test_fail_with_short_help():
    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(exit_code=3, out=out)
    assert_equal(cme.exception.code, 3)
    assert_equal(out.getvalue(), "")

    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(msg="Failed badly", out=out)
    assert_equal(cme.exception.code, 1)
    assert_equal(out.getvalue(), "error: Failed badly\n")

    # Suggestions, hint, etc
    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(
            msg="Failed badly",
            known=["mother", "mutter", "father", "son"],
            provided="muther",
            hint="You can become one",
            exit_code=0,  # nobody forbids
            what="parent",
            out=out)
    assert_equal(cme.exception.code, 0)
    assert_equal(out.getvalue(),
                 "error: Failed badly\n"
                 "datalad: Unknown parent 'muther'.  See 'datalad --help'.\n\n"
                 "Did you mean any of these?\n"
                 "        mutter\n"
                 "        mother\n"
                 "        father\n"
                 "Hint: You can become one\n")


def test_fail_with_short_help():
    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(exit_code=3, out=out)
    assert_equal(cme.exception.code, 3)
    assert_equal(out.getvalue(), "")

    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(msg="Failed badly", out=out)
    assert_equal(cme.exception.code, 1)
    assert_equal(out.getvalue(), "error: Failed badly\n")

    # Suggestions, hint, etc
    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(
            msg="Failed badly",
            known=["mother", "mutter", "father", "son"],
            provided="muther",
            hint="You can become one",
            exit_code=0,  # nobody forbids
            what="parent",
            out=out)
    assert_equal(cme.exception.code, 0)
    assert_equal(out.getvalue(),
                 "error: Failed badly\n"
                 "datalad: Unknown parent 'muther'.  See 'datalad --help'.\n\n"
                 "Did you mean any of these?\n"
                 "        mutter\n"
                 "        mother\n"
                 "        father\n"
                 "Hint: You can become one\n")


@with_tempfile
@with_tempfile(mkdir=True)
def test_commanderror_jsonmsgs(src, exp):
    ds = Dataset(src).create()
    (ds.pathobj / '123').write_text('123')
    ds.save()
    ds.repo.call_annex([
        'initremote', 'expdir', 'type=directory',
        'directory={}'.format(exp),
        'encryption=none',
        'exporttree=yes'
    ])
    #ds.repo.call_annex(['export', '--to=expdir', 'HEAD'])
    # this must fail, because `push` cannot handle an export.
    # when https://github.com/datalad/datalad/issues/3127 is implemented
    # this test must be adjusted
    with assert_raises(CommandError) as cme:
        Runner(cwd=ds.path).run(
            ['datalad', 'push', '--to', 'expdir'],
            protocol=StdOutErrCapture)
    if ds.repo.git_annex_version >= "8.20201129":
        in_('use `git-annex export`', cme.exception.stderr)
