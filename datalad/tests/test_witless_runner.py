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
import signal
import sys

from pathlib import Path
from time import (
    sleep,
    time,
)

from datalad.tests.utils import (
    assert_cwd_unchanged,
    assert_in,
    assert_raises,
    eq_,
    integration,
    OBSCURE_FILENAME,
    ok_,
    ok_file_has_content,
    SkipTest,
    with_tempfile,
)
from datalad.cmd import (
    StdOutErrCapture,
    WitlessRunner as Runner,
    StdOutCapture,
)
from datalad.utils import (
    on_windows,
    Path,
)
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
    content = 'Testing real run' if on_windows else 'Testing äöü東 real run' 
    cmd = 'echo %s > %s' % (content, tempfile)
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


@integration  # ~3 sec
@with_tempfile(mkdir=True)
@with_tempfile()
def test_asyncio_loop_noninterference1(path1, path2):
    if on_windows and sys.version_info < (3, 8):
        raise SkipTest(
            "get_event_loop() raises "
            "RuntimeError: There is no current event loop in thread 'MainThread'.")
    # minimalistic use case provided by Dorota
    import datalad.api as dl
    src = dl.create(path1)
    reproducer = src.pathobj/ "reproducer.py"
    reproducer.write_text(f"""\
import asyncio
asyncio.get_event_loop()
import datalad.api as datalad
ds = datalad.clone(path=r'{path2}', source=r"{path1}")
loop = asyncio.get_event_loop()
assert loop
# simulate outside process closing the loop
loop.close()
# and us still doing ok
ds.status()
""")
    Runner().run([sys.executable, str(reproducer)])  # if Error -- the test failed


@with_tempfile
def test_asyncio_forked(temp):
    # temp will be used to communicate from child either it succeeded or not
    temp = Path(temp)
    runner = Runner()
    import os
    try:
        pid = os.fork()
    except BaseException as exc:
        # .fork availability is "Unix", and there are cases where it is "not supported"
        # so we will just skip if no forking is possible
        raise SkipTest(f"Cannot fork: {exc}")
    # if does not fail (in original or in a fork) -- we are good
    if sys.version_info < (3, 8) and pid != 0:
        # for some reason it is crucial to sleep a little (but 0.001 is not enough)
        # in the master process with older pythons or it takes forever to make the child run
        sleep(0.1)
    try:
        runner.run([sys.executable, '--version'], protocol=StdOutCapture)
        if pid == 0:
            temp.write_text("I rule")
    except:
        if pid == 0:
            temp.write_text("I suck")
    if pid != 0:
       # parent: look after the child
       t0 = time()
       try:
           while not temp.exists() or temp.stat().st_size < 6:
               if time() - t0 > 5:
                   raise AssertionError("Child process did not create a file we expected!")
       finally:
           # kill the child
           os.kill(pid, signal.SIGTERM)
       # see if it was a good one
       eq_(temp.read_text(), "I rule")
    else:
       # sleep enough so parent just kills me the kid before I continue doing bad deeds
       sleep(10)
