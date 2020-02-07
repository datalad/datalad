# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test WitlessRunner
"""

import os
import sys

from .utils import (
    ok_,
    eq_,
    assert_raises,
    assert_in,
    with_tempfile,
    assert_cwd_unchanged,
    ok_file_has_content,
    OBSCURE_FILENAME,
)
from datalad.cmd import (
    WitlessRunner as Runner,
    capture_output,
)
from datalad.utils import Path
from datalad.support.exceptions import CommandError


class TweakOutput(object):
    """Test helper to twist and turn output from WitlessRunner"""
    def __init__(self, rtruncate_nbytes=None, report_truncation=True):
        self._rtruncate_nbytes = rtruncate_nbytes
        self._report_truncation = report_truncation
        self.__enter__()

    def __enter__(self):
        self.received = []
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def __call__(self, byts):
        self.received.append(byts)
        rtrunc = (-1) * self._rtruncate_nbytes \
            if self._rtruncate_nbytes else None
        byts = byts[:rtrunc]
        return byts, self._rtruncate_nbytes if self._report_truncation else 0


def py2cmd(code):
    """Helper to invoke some Python code through a cmdline invokation of
    the Python interpreter.

    This should be more portable in some cases.
    """
    return [sys.executable, '-c', code]


@assert_cwd_unchanged
@with_tempfile
def test_runner(tempfile):
    runner = Runner()
    content = 'Testing äöü東 real run'
    cmd = ['sh', '-c', 'echo %s > %r' % (content, tempfile)]
    out, err = runner.run(cmd)
    # no capture of any kind, by default
    ok_(not out)
    ok_(not err)
    ok_file_has_content(tempfile, content, strip=True)
    os.unlink(tempfile)


def test_runner_stderr_capture():
    runner = Runner()
    test_msg = "stderr-Message"
    out, err = runner.run(py2cmd(
        'import sys; print(%r, file=sys.stderr)' % test_msg),
        proc_stdout=capture_output,
        proc_stderr=capture_output,
    )
    eq_(err.rstrip(), test_msg)
    ok_(not out)


def test_runner_stdout_capture():
    runner = Runner()
    test_msg = "stdout-Message"
    out, err = runner.run(py2cmd(
        'import sys; print(%r, file=sys.stdout)' % test_msg),
        proc_stdout=capture_output,
        proc_stderr=capture_output,
    )
    eq_(out.rstrip(), test_msg)
    ok_(not err)


@with_tempfile(mkdir=True)
def test_runner_failure(dir_):
    runner = Runner()
    with assert_raises(CommandError) as cme:
        runner.run(
            py2cmd('import sys; sys.exit(53)')
        )
    eq_(53, cme.exception.code)


@with_tempfile(mkdir=True)
def test_runner_fix_PWD(path):
    env = os.environ.copy()
    env['PWD'] = orig_cwd = os.getcwd()
    runner = Runner(cwd=path, env=env)
    out, err = runner.run(
        py2cmd('import os; print(os.environ["PWD"])'),
        proc_stdout=capture_output,
    )
    eq_(out.strip(), path)  # was fixed up to point to point to cwd's path
    eq_(env['PWD'], orig_cwd)  # no side-effect


@with_tempfile(mkdir=True)
def test_runner_cwd_encoding(path):
    env = os.environ.copy()
    # Add PWD to env so that runner will temporarily adjust it to point to cwd.
    env['PWD'] = os.getcwd()
    cwd = Path(path) / OBSCURE_FILENAME
    cwd.mkdir()
    # Running doesn't fail if cwd or env has unicode value.
    Runner(cwd=cwd, env=env).run(
        py2cmd(
            'from pathlib import Path; (Path.cwd() / "foo").write_text("t")'))
    (cwd / 'foo').exists()


@with_tempfile(mkdir=True)
def test_runner_stdin(path):
    runner = Runner()
    fakestdin = Path(path) / 'io'
    # go for diffcult content
    fakestdin.write_text(OBSCURE_FILENAME)

    out, err = runner.run(
        py2cmd('import fileinput; print(fileinput.input().readline())'),
        stdin=fakestdin.open(),
        proc_stdout=capture_output,
    )
    assert_in(OBSCURE_FILENAME, out)


py_9bytes_plus_6bytes = """\
import sys
print("123456789", end="", file=sys.stdout, flush=True)
import time
time.sleep(1.5)
print("abcdefg", end="", file=sys.stdout, flush=True)
"""


def test_runner_incomplete_capture():
    runner = Runner()
    with TweakOutput(rtruncate_nbytes=3) as outproc:
        out, err = runner.run(
            py2cmd(py_9bytes_plus_6bytes),
            # we don't process the last three in the output, but we
            # report that to the runner
            proc_stdout=outproc,
            # make sure the runner polls faster than the output is coming
            poll_latency=0.1)
    # we must not loose any output, except for the very last three bytes
    # even though we poll at a higher frequency
    eq_(out, '123456789abcd')
    # conditional protect against slow execution
    # we see the first batch received
    if len(outproc.received) > 1:
        eq_(outproc.received[0], b'123456789')
        # we see the last batch that carries the pending 3 bytes upfront
        eq_(outproc.received[-1], b'789abcdefg')
    if len(outproc.received) > 2:
        # we see the truncated 3 bytes of the first batch, repeatedly
        # sent (but the processor rejects them)
        eq_(outproc.received[1:-1], (len(outproc.received) - 2) * [b'789'])

    # no the same, but the processor doesn't tell that it ignored
    # 3 bytes
    with TweakOutput(rtruncate_nbytes=3, report_truncation=False) as outproc:
        out, err = runner.run(
            py2cmd(py_9bytes_plus_6bytes),
            # we don't process the last three in the output, but we
            # report that to the runner
            proc_stdout=outproc,
            poll_latency=0.1)
    # we miss three bytes at the end of each batch
    if len(outproc.received) > 1:
        eq_(out, '123456abcd')
