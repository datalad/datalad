# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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

import pytest

import datalad
from datalad import __version__
from datalad.api import (
    Dataset,
    create,
)
from datalad.cmd import StdOutErrCapture
from datalad.cmd import WitlessRunner as Runner
from datalad.interface.base import get_interface_groups
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_re_in,
    eq_,
    in_,
    ok_,
    ok_startswith,
    on_windows,
    skip_if_no_module,
    slow,
    with_tempfile,
)
from datalad.ui.utils import (
    get_console_width,
    get_terminal_size,
)
from datalad.utils import chpwd

from ..helpers import get_commands_from_groups
from ..main import main


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
    was_mode = datalad.__api
    try:
        # we need to catch "stdout" from multiple places:
        # sys.stdout but also from the UI, which insists on holding
        # a dedicated handle
        fakeout = StringIO()
        fakeerr = StringIO()
        with patch('sys.stderr', new=fakeerr) as cmerr, \
             patch('sys.stdout', new=fakeout) as cmout, \
             patch.object(datalad.ui.ui._ui, 'out', new=fakeout):
            with assert_raises(SystemExit) as cm:
                main(["datalad"] + list(args))
            eq_('cmdline', datalad.get_apimode())
            assert_equal(cm.value.code, exit_code)
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
    finally:
        # restore what we had
        datalad.__api = was_mode

    return stdout, stderr


def get_all_commands() -> list:
    return list(get_commands_from_groups(get_interface_groups()))


def assert_all_commands_present(out):
    """Helper to reuse to assert that all known commands are present in output
    """
    for cmd in get_all_commands():
        assert_re_in(fr"\b{cmd}\b", out, match=False)


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
    for s in {'Essential commands',
              'Commands for metadata handling',
              'Miscellaneous commands',
              'General information',
              'Global options',
              'Plumbing commands',
              }:
        assert_in(s, sections)
        # should be present only one time!
        eq_(stdout.count(s), 1)

    # check that we have global options actually listed after "Global options"
    # ATM -c is the first such option
    assert re.search(r"Global options\W*-c ", stdout, flags=re.MULTILINE)
    # and -c should be listed only once - i.e. that we do not duplicate sections
    # and our USAGE summary has only [global-opts]
    assert re.match("Usage: .*datalad.* \[global-opts\] command \[command-opts\]", stdout)
    assert stdout.count(' -c ') == 1

    assert_all_commands_present(stdout)

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


def test_dashh():
    stdout, stderr = run_main(['-h'])
    # Note: for -h we do not do ad-hoc tune up of Usage: to guarantee having
    # datalad instead of python -m nose etc, so we can only verify that we have
    # options listed
    assert_re_in(r'^Usage: .*\[', stdout.splitlines()[0])
    assert_all_commands_present(stdout)
    assert_re_in('Use .--help. to get more comprehensive information', stdout.splitlines())


def test_dashh_clone():
    # test -h on a sample command
    stdout, stderr = run_main(['clone', '-h'])
    assert_re_in(r'^Usage: .* clone \[', stdout.splitlines()[0])
    assert_re_in('Use .--help. to get more comprehensive information', stdout.splitlines())


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


# https://github.com/datalad/datalad/issues/6814
@with_tempfile(mkdir=True)
def test_conflicting_short_option(tempdir=None):
    # datalad -f|--format   requires a value. regression made parser ignore command
    # and its options
    with chpwd(tempdir):  # can't just use -C tempdir since we do "in process" run_main
        run_main(['create', '-f'])


# apparently a bit different if following a good one so let's do both
err_invalid = "error: (invalid|too few arguments|unrecognized argument)"
err_insufficient = err_invalid  # "specify"


@pytest.mark.parametrize(
    "opts,err_str",
    [
        (('--buga',), err_invalid),
        (('--dbg', '--buga'), err_invalid),
        (('--dbg',), err_insufficient),
        (tuple(), err_insufficient),
    ]
)
def test_incorrect_option(opts, err_str):
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


@pytest.mark.parametrize(
    "script",
    [
        'datalad',
        'git-annex-remote-datalad-archives',
        'git-annex-remote-datalad',
    ]
)
def test_script_shims(script):
    runner = Runner()
    if not on_windows:

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


@with_tempfile(mkdir=True)
def test_cfg_override(path=None):
    with chpwd(path):
        # use 'wtf' to dump the config
        # should be rewritten to use `configuration`
        cmd = ['datalad', 'wtf', '-S', 'configuration', '-s', 'some']
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
        create(dataset=path, annex=False)
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

        # set a config
        run_main([
            'configuration', '--scope', 'local', 'set', 'mike.item=some'])
        # verify it is successfully set
        assert 'some' == run_main([
            'configuration', 'get', 'mike.item'])[0].strip()
        # verify that an override can unset the config
        # we cannot use run_main(), because the "singleton" instance of the
        # dataset we are in is still around in this session, and with it
        # also its config managers that we will not be able to post-hoc
        # overwrite with this method. Instead, we'll execute in a subprocess.
        assert '' == Runner().run([
            'datalad', '-c', ':mike.item',
            'configuration', 'get', 'mike.item'],
            protocol=StdOutErrCapture)['stdout'].strip()
        # verify the effect is not permanent
        assert 'some' == Runner().run([
            'datalad',
            'configuration', 'get', 'mike.item'],
            protocol=StdOutErrCapture)['stdout'].strip()


def test_incorrect_cfg_override():
    run_main(['-c', 'some', 'wtf'], exit_code=3)
    run_main(['-c', 'some=', 'wtf'], exit_code=3)
    run_main(['-c', 'some.var', 'wtf'], exit_code=3)
    run_main(['-c', 'some.var=', 'wtf'], exit_code=3)


@with_tempfile
def test_librarymode(path=None):
    Dataset(path).create()
    was_mode = datalad.__runtime_mode
    try:
        # clean --dry-run is just a no-op command that is cheap
        # to execute. It has no particular role here, other than
        # to make the code pass the location where library mode
        # should be turned on via the cmdline API
        run_main(['-c', 'datalad.runtime.librarymode=yes', 'clean',
                  '-d', path, '--dry-run'])
        ok_(datalad.in_librarymode())
    finally:
        # restore pre-test behavior
        datalad.__runtime_mode = was_mode
        datalad.cfg.overrides.pop('datalad.runtime.librarymode')


@with_tempfile
def test_completion(out_fn=None):
    skip_if_no_module('argcomplete')

    from datalad.cmd import WitlessRunner
    runner = WitlessRunner()

    def get_completions(s: str, expected) -> list:
        """Run 'datalad' external command and collect completions

        Parameters
        ----------
        s: str
          what to append to 'datalad ' invocation
        expected: iterable of str
          What entries to expect - would raise AssertionError if any is
          not present in output
        exit_code: int, optional
          If incomplete/malformed we seems to get 2, most frequently used
          so default

        Returns
        -------
        list of str
          Entries output
        """
        if os.path.exists(out_fn):  # reuse but ensure it is gone
            os.unlink(out_fn)
        comp_line = f'datalad {s}'
        runner.run(
            comp_line.split(' '),
            env=dict(os.environ,
                     _ARGCOMPLETE='1',
                     _ARGCOMPLETE_STDOUT_FILENAME=out_fn,
                     COMP_LINE=comp_line,
                     # without -1 seems to get "finished completion", someone can investigate more
                     COMP_POINT=str(len(comp_line)-1),  # always at the end ATM
                     ))
        with open(out_fn, 'rb') as f:
            entries = f.read().split(b'\x0b')
            entries = [e.decode() for e in entries]
        diff = set(expected).difference(entries)
        if diff:
            raise AssertionError(
                f"Entries {sorted(diff)} were expected but not found in the completion output: {entries}"
            )
        return entries  # for extra analyzes if so desired

    all_commands = get_all_commands()
    get_completions('i', {'install'})
    get_completions(' ', ['--dbg', '-c'] + all_commands)
    # if command already matches -- we get only that hit ATM, not others which begin with it
    get_completions('create', ['create '])
    get_completions('create -', ['--dataset'])
    # but for incomplete one we do get all create* commands
    get_completions('creat', [c for c in all_commands if c.startswith('create')])
