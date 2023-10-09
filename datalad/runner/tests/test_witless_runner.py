# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test WitlessRunner
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import unittest.mock
from threading import (
    Lock,
    Thread,
)
from time import (
    sleep,
    time,
)
from typing import Any

import pytest

from datalad.tests.utils_pytest import (
    OBSCURE_FILENAME,
    SkipTest,
    assert_cwd_unchanged,
    assert_in,
    assert_raises,
    eq_,
    integration,
    ok_,
    ok_file_has_content,
    skip_if_on_windows,
    swallow_logs,
    with_tempfile,
)
from datalad.utils import (
    CMD_MAX_ARG,
    Path,
    on_windows,
)

from .. import (
    CommandError,
    KillOutput,
    Protocol,
    Runner,
    StdOutCapture,
    StdOutErrCapture,
)
from .utils import py2cmd

result_counter = 0


@assert_cwd_unchanged
@with_tempfile
def test_runner(tempfile: str = "") -> None:
    runner = Runner()
    content = 'Testing real run' if on_windows else 'Testing äöü東 real run'
    cmd = 'echo %s > %s' % (content, tempfile)
    res = runner.run(cmd)
    assert isinstance(res, dict)
    # no capture of any kind, by default
    ok_(not res['stdout'])
    ok_(not res['stderr'])
    ok_file_has_content(tempfile, content, strip=True)
    os.unlink(tempfile)


def test_runner_stderr_capture() -> None:
    runner = Runner()
    test_msg = "stderr-Message"
    res = runner.run(py2cmd(
        'import sys; print(%r, file=sys.stderr)' % test_msg),
        protocol=StdOutErrCapture,
    )
    assert isinstance(res, dict)
    eq_(res['stderr'].rstrip(), test_msg)
    ok_(not res['stdout'])


def test_runner_stdout_capture() -> None:
    runner = Runner()
    test_msg = "stdout-Message"
    res = runner.run(py2cmd(
        'import sys; print(%r, file=sys.stdout)' % test_msg),
        protocol=StdOutErrCapture,
    )
    assert isinstance(res, dict)
    eq_(res['stdout'].rstrip(), test_msg)
    ok_(not res['stderr'])


def test_runner_failure() -> None:
    runner = Runner()
    with assert_raises(CommandError) as cme:
        runner.run(
            py2cmd('import sys; sys.exit(53)')
        )
    eq_(53, cme.value.code)

    # but we bubble up FileNotFoundError if executable does not exist at all
    with assert_raises(FileNotFoundError) as cme:
        runner.run(['dne1l2k3j4'])  # be damned the one who makes such a command


@with_tempfile(mkdir=True)
def test_runner_fix_PWD(path: str = "") -> None:
    env = os.environ.copy()
    env['PWD'] = orig_cwd = os.getcwd()
    runner = Runner(cwd=path, env=env)
    res = runner.run(
        py2cmd('import os; print(os.environ["PWD"])'),
        protocol=StdOutCapture,
    )
    assert isinstance(res, dict)
    eq_(res['stdout'].strip(), path)  # was fixed up to point to point to cwd's path
    eq_(env['PWD'], orig_cwd)  # no side-effect


@with_tempfile(mkdir=True)
def test_runner_cwd_encoding(path: str = "") -> None:
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
def test_runner_stdin(path: str = "") -> None:
    runner = Runner()
    fakestdin = Path(path) / 'io'
    # go for difficult content
    fakestdin.write_text(OBSCURE_FILENAME)

    res = runner.run(
        py2cmd('import fileinput; print(fileinput.input().readline())'),
        stdin=fakestdin.open(),
        protocol=StdOutCapture,
    )
    assert isinstance(res, dict)
    assert_in(OBSCURE_FILENAME, res['stdout'])

    # we can do the same without a tempfile, too
    res = runner.run(
        py2cmd('import fileinput; print(fileinput.input().readline())'),
        stdin=OBSCURE_FILENAME.encode('utf-8'),
        protocol=StdOutCapture,
    )
    assert isinstance(res, dict)
    assert_in(OBSCURE_FILENAME, res['stdout'])


@pytest.mark.fail_slow(3)
def test_runner_stdin_no_capture() -> None:
    # Ensure that stdin writing alone progresses
    runner = Runner()
    runner.run(
        py2cmd('import sys; print(sys.stdin.read()[-10:])'),
        stdin=('ABCDEFGHIJKLMNOPQRSTUVWXYZ-' * 2 + '\n').encode('utf-8'),
        protocol=None
    )


@pytest.mark.fail_slow(3)
def test_runner_no_stdin_no_capture() -> None:
    # Ensure a runner without stdin data and output capture progresses
    runner = Runner()
    runner.run(
        (["cmd.exe", "/c"] if on_windows else []) + ["echo", "a", "b", "c"],
        stdin=None,
        protocol=None
    )


@pytest.mark.fail_slow(3)
def test_runner_empty_stdin() -> None:
    # Ensure a runner without stdin data and output capture progresses
    runner = Runner()
    runner.run(
        py2cmd('import sys; print(sys.stdin.read())'),
        stdin=b"",
        protocol=None
    )


def test_runner_parametrized_protocol() -> None:
    runner = Runner()

    # protocol returns a given value whatever it receives
    class ProtocolInt(StdOutCapture):
        def __init__(self, value: bytes) -> None:
            self.value = value
            super().__init__()

        def pipe_data_received(self, fd: int, data: bytes) -> None:
            super().pipe_data_received(fd, self.value)

    res = runner.run(
        py2cmd('print(1, end="")'),
        protocol=ProtocolInt,
        # value passed to protocol constructor
        value=b'5',
    )
    assert isinstance(res, dict)
    eq_(res['stdout'], '5')


@integration  # ~3 sec
@with_tempfile(mkdir=True)
@with_tempfile()
def test_asyncio_loop_noninterference1(path1: str = "", path2: str = "") -> None:
    if on_windows and sys.version_info < (3, 8):
        raise SkipTest(
            "get_event_loop() raises "
            "RuntimeError: There is no current event loop in thread 'MainThread'.")
    # minimalistic use case provided by Dorota
    import datalad.api as dl
    src = dl.create(path1)  # type: ignore[attr-defined]
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
def test_asyncio_forked(temp_: str = "") -> None:
    # temp will be used to communicate from child either it succeeded or not
    temp = Path(temp_)
    runner = Runner()
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


def test_done_deprecation() -> None:
    with unittest.mock.patch("datalad.cmd.warnings.warn") as warn_mock:
        _ = Protocol("done")
        warn_mock.assert_called_once()

    with unittest.mock.patch("datalad.cmd.warnings.warn") as warn_mock:
        _ = Protocol()
        warn_mock.assert_not_called()


def test_faulty_poll_detection() -> None:
    popen_mock = unittest.mock.MagicMock(**{"pid": 666, "poll.return_value": None})
    protocol = Protocol()
    protocol.process = popen_mock
    assert_raises(CommandError, protocol._prepare_result)


def test_kill_output() -> None:
    runner = Runner()
    res = runner.run(
        py2cmd('import sys; sys.stdout.write("aaaa\\n"); sys.stderr.write("bbbb\\n")'),
        protocol=KillOutput)
    assert isinstance(res, dict)
    eq_(res['stdout'], '')
    eq_(res['stderr'], '')


@skip_if_on_windows  # no "hint" on windows since no ulimit command there
def test_too_long() -> None:
    with swallow_logs(new_level=logging.ERROR) as cml:
        with assert_raises(OSError):  # we still raise an exception if we exceed too much
            Runner().run(
                [sys.executable, '-c', 'import sys; print(len(sys.argv))'] + [str(i) for i in range(CMD_MAX_ARG)],
                protocol=StdOutCapture
            )
        cml.assert_logged('.*use.*ulimit.*')


def test_path_to_str_conversion() -> None:
    # Regression test to ensure that Path-objects are converted into strings
    # before they are put into the environment variable `$PWD`
    runner = Runner()
    test_path = Path("a/b/c")
    adjusted_env = runner._get_adjusted_env(
        cwd=test_path,
        env=dict(some_key="value")
    )
    assert adjusted_env is not None
    assert str(test_path) == adjusted_env['PWD']


def test_env_copying() -> None:
    # Regression test to ensure environments are only copied
    # if `copy=True` is given to `Runner._get_adjusted_env.`
    # Test also for path adjustments, if not-`None` `pwd`-value
    # is given to `Runner._get_adjusted_env`.
    runner = Runner()
    for original_env in (None, dict(some_key='value')):
        for cwd in (None, Path('a/b/c')):
            for do_copy in (True, False):
                adjusted_env = runner._get_adjusted_env(
                    cwd=cwd,
                    env=original_env,
                    copy=do_copy
                )
                if original_env is None:
                    assert adjusted_env is None
                else:
                    assert adjusted_env is not None
                    if do_copy is True:
                        assert adjusted_env is not original_env
                    else:
                        assert adjusted_env is original_env
                    if cwd is None:
                        assert 'PWD' not in adjusted_env
                    else:
                        assert 'PWD' in adjusted_env


@with_tempfile(mkdir=True)
def test_environment(temp_dir_path: str = "") -> None:
    # Ensure that the subprocess sees a string in `$PWD`, even if a Path-object
    # is provided to `cwd`.
    cmd = py2cmd("import os; print(os.environ['PWD'])")
    cwd = Path(temp_dir_path)
    env = dict(SYSTEMROOT=os.environ.get('SYSTEMROOT', ''))
    runner = Runner()
    results = runner.run(cmd=cmd, protocol=StdOutCapture, cwd=cwd, env=env)
    assert isinstance(results, dict)
    output = results['stdout'].splitlines()[0]
    assert output == temp_dir_path

    runner = Runner(cwd=cwd, env=env)
    results = runner.run(cmd=cmd, protocol=StdOutCapture)
    assert isinstance(results, dict)
    output = results['stdout'].splitlines()[0]
    assert output == temp_dir_path


def test_argument_priority() -> None:
    class X:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

        def run(self) -> dict:
            return dict(
                code=0,
                args=self.args,
                kwargs=self.kwargs,
            )

    test_path_1 = "a/b/c"
    test_env_1 = dict(source="constructor")
    test_path_2 = "d/e/f"
    test_env_2 = dict(source="run-method")

    with unittest.mock.patch('datalad.runner.runner.ThreadedRunner') as tr_mock:

        tr_mock.side_effect = X
        runner = Runner(cwd=test_path_1, env=test_env_1)

        result = runner.run("first-command")
        assert isinstance(result, dict)
        assert result['kwargs']['cwd'] == test_path_1
        assert result['kwargs']['env'] == {
            **test_env_1,
            'PWD': test_path_1
        }

        result = runner.run("second-command", cwd=test_path_2, env=test_env_2)
        assert isinstance(result, dict)
        assert result['kwargs']['cwd'] == test_path_2
        assert result['kwargs']['env'] == {
            **test_env_2,
            'PWD': test_path_2
        }


def test_concurrent_execution() -> None:
    runner = Runner()
    caller_threads = []

    result_list: list[str] = []
    result_list_lock = Lock()

    def target(count: int, r_list: list[str], r_list_lock: Lock) -> None:
        result = runner.run(
            py2cmd(
                "import time;"
                "import sys;"
                "time.sleep(1);"
                "print('end', sys.argv[1])",
                str(count)
            ),
            protocol=StdOutCapture,
        )
        assert isinstance(result, dict)
        output = result["stdout"].strip()
        assert output == f"end {str(count)}"
        with r_list_lock:
            r_list.append(output)

    for c in range(100):
        caller_thread = Thread(
            target=target,
            kwargs=dict(
                count=c,
                r_list=result_list,
                r_list_lock=result_list_lock,
            ))
        caller_thread.start()
        caller_threads.append(caller_thread)

    while caller_threads:
        t = caller_threads.pop()
        t.join()

    assert len(result_list) == 100
