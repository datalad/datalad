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

from datalad.tests.utils import (
    assert_cwd_unchanged,
    assert_in,
    assert_raises,
    eq_,
    OBSCURE_FILENAME,
    ok_,
    ok_file_has_content,
    with_tempfile,
)
from datalad.cmd import (
    StdOutErrCapture,
    WitlessRunner as Runner,
    StdOutCapture,
)
from datalad.utils import Path
from datalad.support.exceptions import CommandError


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
    res = runner.run(cmd)
    # no capture of any kind, by default
    ok_(not res['stdout'])
    ok_(not res['stderr'])
    ok_file_has_content(tempfile, content, strip=True)
    os.unlink(tempfile)


def test_runner_stderr_capture():
    runner = Runner()
    test_msg = "stderr-Message"
    res = runner.run(py2cmd(
        'import sys; print(%r, file=sys.stderr)' % test_msg),
        protocol=StdOutErrCapture,
    )
    eq_(res['stderr'].rstrip(), test_msg)
    ok_(not res['stdout'])


def test_runner_stdout_capture():
    runner = Runner()
    test_msg = "stdout-Message"
    res = runner.run(py2cmd(
        'import sys; print(%r, file=sys.stdout)' % test_msg),
        protocol=StdOutErrCapture,
    )
    eq_(res['stdout'].rstrip(), test_msg)
    ok_(not res['stderr'])


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
    res = runner.run(
        py2cmd('import os; print(os.environ["PWD"])'),
        protocol=StdOutCapture,
    )
    eq_(res['stdout'].strip(), path)  # was fixed up to point to point to cwd's path
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

    res = runner.run(
        py2cmd('import fileinput; print(fileinput.input().readline())'),
        stdin=fakestdin.open(),
        protocol=StdOutCapture,
    )
    assert_in(OBSCURE_FILENAME, res['stdout'])


def test_runner_parametrized_protocol():
    runner = Runner()

    # protocol returns a given value whatever it receives
    class ProtocolInt(StdOutCapture):
        def __init__(self, done_future, value):
            self.value = value
            super().__init__(done_future)

        def pipe_data_received(self, fd, data):
            super().pipe_data_received(fd, self.value)

    res = runner.run(
        py2cmd('print(1)'),
        protocol=ProtocolInt,
        # value passed to protocol constructor
        value=b'5',
    )
    eq_(res['stdout'], '5')
