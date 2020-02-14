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
        protocol=StdOutErrCapture,
    )
    eq_(err.rstrip(), test_msg)
    ok_(not out)


def test_runner_stdout_capture():
    runner = Runner()
    test_msg = "stdout-Message"
    out, err = runner.run(py2cmd(
        'import sys; print(%r, file=sys.stdout)' % test_msg),
        protocol=StdOutErrCapture,
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
        protocol=StdOutCapture,
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
        protocol=StdOutCapture,
    )
    assert_in(OBSCURE_FILENAME, out)
