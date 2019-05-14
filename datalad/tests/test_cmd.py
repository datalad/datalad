# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test command call wrapper
"""

import os
import os.path as op
import sys
import logging
import shlex

from .utils import (
    ok_,
    ok_exists,
    eq_,
    assert_is,
    assert_equal,
    assert_false,
    assert_true,
    assert_greater,
    assert_raises,
    assert_in,
    SkipTest,
    skip_if_on_windows,
    with_tempfile,
    assert_cwd_unchanged,
    swallow_outputs,
    swallow_logs,
    ok_file_has_content,
    on_windows,
    lgr,
    OBSCURE_FILENAME,
)

from ..cmd import (
    Runner,
    GitRunner,
)
from ..support.exceptions import CommandError
from ..support.protocol import DryRunProtocol


@assert_cwd_unchanged
@with_tempfile
def test_runner_dry(tempfile):

    dry = DryRunProtocol()
    runner = Runner(protocol=dry)

    # test dry command call
    cmd = 'echo Testing äöü東 dry run > %s' % tempfile
    with swallow_logs(new_level=9) as cml:
        ret = runner.run(cmd)
        cml.assert_logged("{DryRunProtocol} Running: %s" % cmd, regex=False)
    assert_equal(("DRY", "DRY"), ret,
                 "Output of dry run (%s): %s" % (cmd, ret))
    assert_equal(shlex.split(cmd, posix=not on_windows), dry[0]['command'])
    assert_false(os.path.exists(tempfile))

    # test dry python function call
    output = runner.call(os.path.join, 'foo', 'bar')
    assert_is(None, output, "Dry call of: os.path.join, 'foo', 'bar' "
                            "returned: %s" % output)
    assert_in('join', dry[1]['command'][0])
    assert_equal("args=('foo', 'bar')", dry[1]['command'][1])


@assert_cwd_unchanged
@with_tempfile
def test_runner(tempfile):

    # test non-dry command call
    runner = Runner()
    content = 'Testing äöü東 real run'
    cmd = 'echo %s > %r' % (content, tempfile)
    ret = runner.run(cmd)
    assert_equal(ret, ('', ''))  # no out or err
    ok_file_has_content(tempfile, content, strip=True)
    os.unlink(tempfile)

    # Run with shell
    ret = runner.run(cmd, shell=True)
    assert_equal(ret, ('', ''))  # no out or err
    ok_file_has_content(tempfile, content, strip=True)
    os.unlink(tempfile)

    # Pass as a list and with shell - "not exactly what we expect"
    # Initial suspicion came from incorrect behavior of Runner as a runner
    # for patool.  Apparently (docs for 2.7):
    #   If args is a sequence, the first item specifies the command string,
    #   and any additional items will be treated as additional arguments to
    #   the shell itself.
    # which is what it ruins it for us!  So, for now we are not testing/using
    # this form
    # ret = runner.run(shlex.split(cmd, posix=not on_windows), shell=True)
    # # ?! for some reason there is an empty line in stdout
    # # TODO: figure out.  It shouldn't though be of critical effect
    # ret = (ret[0].rstrip(), ret[1])
    # assert_equal(ret, ('', ''))  # no out or err
    # # And here we get kaboom ATM!
    # ok_file_has_content(tempfile, content, strip=True)

    # test non-dry python function call
    output = runner.call(os.path.join, 'foo', 'bar')
    assert_equal(os.path.join('foo', 'bar'), output,
                 "Call of: os.path.join, 'foo', 'bar' returned %s" % output)


def test_runner_instance_callable_dry():

    cmd_ = ['echo', 'Testing', '__call__', 'with', 'string']
    for cmd in [cmd_, ' '.join(cmd_)]:
        dry = DryRunProtocol()
        runner = Runner(protocol=dry)
        ret = runner(cmd)
        # (stdout, stderr) is returned.  But in dry -- ("DRY","DRY")
        eq_(ret, ("DRY", "DRY"))
        assert_equal(cmd_, dry[0]['command'],
                     "Dry run of Runner.__call__ didn't record command: %s.\n"
                     "Buffer: %s" % (cmd, dry))

    ret = runner(os.path.join, 'foo', 'bar')
    eq_(ret, None)

    assert_in('join', dry[1]['command'][0],
              "Dry run of Runner.__call__ didn't record function join()."
              "Buffer: %s" % dry)
    assert_equal("args=('foo', 'bar')", dry[1]['command'][1],
                 "Dry run of Runner.__call__ didn't record function join()."
                 "Buffer: %s" % dry)


def test_runner_instance_callable_wet():

    runner = Runner()
    cmd = [sys.executable, "-c", "print('Testing')"]

    out = runner(cmd)
    eq_(out[0].rstrip(), ('Testing'))
    eq_(out[1], '')

    ret = runner(os.path.join, 'foo', 'bar')
    eq_(ret, os.path.join('foo', 'bar'))


def test_runner_log_stderr():

    runner = Runner(log_outputs=True)
    cmd = 'echo stderr-Message should be logged >&2'
    with swallow_outputs() as cmo:
        with swallow_logs(new_level=9) as cml:
            ret = runner.run(cmd, log_stderr=True, expect_stderr=True)
            cml.assert_logged("Running: %s" % cmd, level='Level 9', regex=False)
            if not on_windows:
                # we can just count on sanity
                cml.assert_logged("stderr| stderr-"
                                  "Message should be logged", regex=False)
            else:
                # echo outputs quoted lines for some reason, so relax check
                ok_("stdout-Message should be logged" in cml.lines[1])

    cmd = 'echo stderr-Message should not be logged >&2'
    with swallow_outputs() as cmo:
        with swallow_logs(new_level=9) as cml:
            ret = runner.run(cmd, log_stderr=False)
            eq_(cmo.err.rstrip(), "stderr-Message should not be logged")
            assert_raises(AssertionError, cml.assert_logged,
                          "stderr| stderr-Message should not be logged")


def test_runner_log_stdout():
    # TODO: no idea of how to check correct logging via any kind of
    # assertion yet.

    runner = Runner(log_outputs=True)
    cmd_ = ['echo', 'stdout-Message äöü東 should be logged']
    for cmd in [cmd_, ' '.join(cmd_)]:
        # should be identical runs, either as a string or as a list
        kw = {}
        # on Windows it can't find echo if ran outside the shell
        if on_windows and isinstance(cmd, list):
            kw['shell'] = True
        with swallow_logs(9) as cm:
            ret = runner.run(cmd, log_stdout=True, **kw)
            cm.assert_logged("Running: %s" % cmd, level='Level 9', regex=False)
            if not on_windows:
                # we can just count on sanity
                cm.assert_logged("stdout| stdout-"
                                 "Message äöü東 should be logged", regex=False)
            else:
                # echo outputs quoted lines for some reason, so relax check
                ok_("stdout-Message äöü東 should be logged" in cm.lines[1])

    cmd = 'echo stdout-Message äöü東 should not be logged'
    with swallow_outputs() as cmo:
        with swallow_logs(new_level=11) as cml:
            ret = runner.run(cmd, log_stdout=False)
            eq_(cmo.out, "stdout-Message äöü東 should not be logged\n")
            eq_(cml.out, "")


def check_runner_heavy_output(log_online):
    # TODO: again, no automatic detection of this resulting in being
    # stucked yet.

    runner = Runner()
    cmd = '%s %s' % (sys.executable, op.join(op.dirname(__file__), "heavyoutput.py"))

    with swallow_outputs() as cm, swallow_logs():
        ret = runner.run(cmd,
                         log_online=log_online,
                         log_stderr=False, log_stdout=False,
                         expect_stderr=True)
        eq_(cm.err, cm.out)  # they are identical in that script
        eq_(cm.out[:10], "0 [0, 1, 2")
        eq_(cm.out[-15:], "997, 998, 999]\n")

    # for some reason swallow_logs is not effective, so we just skip altogether
    # if too heavy debug output
    if lgr.getEffectiveLevel() <= logging.DEBUG:
        raise SkipTest("Skipping due to too heavy impact on logs complicating debugging")

    #do it again with capturing:
    with swallow_logs():
        ret = runner.run(cmd,
                         log_online=True, log_stderr=True, log_stdout=True,
                         expect_stderr=True)

    if log_online:
        # halting case of datalad add and other batch commands #2116
        logged = []
        with swallow_logs():
            def process_stdout(l):
                assert l
                logged.append(l)
            ret = runner.run(
                cmd,
                log_online=log_online,
                log_stdout=process_stdout,
                log_stderr='offline',
                expect_stderr=True
            )
        assert_equal(len(logged), 100)
        assert_greater(len(ret[1]), 1000)  # stderr all here
        assert not ret[0], "all messages went into `logged`"


def test_runner_heavy_output():
    skip_if_on_windows()
    for log_online in [False, True]:
        yield check_runner_heavy_output, log_online


@with_tempfile(mkdir=True)
def test_runner_failure(dir_):
    from ..support.annexrepo import AnnexRepo
    repo = AnnexRepo(dir_, create=True)
    runner = Runner()
    failing_cmd = ['git-annex', 'add', 'notexistent.dat']

    with assert_raises(CommandError) as cme, \
         swallow_logs() as cml:
        runner.run(failing_cmd, cwd=dir_)
        assert_in('notexistent.dat not found', cml.out)
    assert_equal(1, cme.exception.code)


@with_tempfile(mkdir=True)
def test_runner_failure_unicode(path):
    # Avoid OBSCURE_FILENAME in hopes of windows-compatibility (gh-2929).
    runner = Runner()
    with assert_raises(CommandError), swallow_logs():
        runner.run(u"β-command-doesnt-exist", cwd=path)


@skip_if_on_windows  # likely would fail
@with_tempfile(mkdir=True)
def test_runner_fix_PWD(path):
    env = os.environ.copy()
    env['PWD'] = orig_cwd = os.getcwd()
    runner = Runner(cwd=path, env=env)
    out, err = runner.run(
        [sys.executable, '-c', 'import os; print(os.environ["PWD"])'],
        cwd=path,
        shell=False
    )
    eq_(err, '')
    eq_(out.rstrip(os.linesep), path)  # was fixed up to point to point to cwd's path
    eq_(env['PWD'], orig_cwd)  # no side-effect


@with_tempfile(mkdir=True)
def test_runner_cwd_encoding(path):
    env = os.environ.copy()
    # Add PWD to env so that runner will temporarily adjust it to point to cwd.
    env['PWD'] = os.getcwd()
    cwd = op.join(path, OBSCURE_FILENAME)
    os.mkdir(cwd)
    # Running doesn't fail if cwd or env has unicode value.
    Runner().run("cd .> foo", cwd=cwd, env=env)
    ok_exists(op.join(cwd, "foo"))


@with_tempfile(mkdir=True)
def test_git_path(dir_):
    from ..support.gitrepo import GitRepo
    # As soon as we use any GitRepo we should get _GIT_PATH set in the Runner
    repo = GitRepo(dir_, create=True)
    assert GitRunner._GIT_PATH is not None


@with_tempfile(mkdir=True)
def test_runner_stdin(path):
    runner = Runner()
    with open(op.join(path, "test_input.txt"), "w") as f:
        f.write("whatever")

    with swallow_outputs() as cmo, open(op.join(path, "test_input.txt"), "r") as fake_input:
        runner.run(['cat'], log_stdout=False, stdin=fake_input)
        assert_in("whatever", cmo.out)


def test_process_remaining_output():
    runner = Runner()
    out = u"""\
s
п
"""
    out_bytes = out.encode('utf-8')
    target = u"s{ls}п{ls}".format(ls=os.linesep).encode('utf-8')
    args = ['stdout', None, False, False]
    #  probably #2185
    eq_(runner._process_remaining_output(None, out_bytes, *args), target)
    eq_(runner._process_remaining_output(None, out, *args), target)
