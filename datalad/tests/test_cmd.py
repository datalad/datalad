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
import sys
import unittest.mock
from subprocess import TimeoutExpired

import pytest

from datalad.cmd import (
    BatchedCommand,
    readline_rstripped,
)
from datalad.cmd import BatchedCommandError
from datalad.runner.exception import CommandError
from datalad.runner.tests.utils import py2cmd
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_is_none,
    assert_is_not_none,
    assert_not_equal,
    assert_raises,
    assert_true,
)


def test_readline_rstripped_deprecation():
    with unittest.mock.patch("datalad.cmd.warnings.warn") as warn_mock:
        class StdoutMock:
            def readline(self):
                return "abc\n"
        readline_rstripped(StdoutMock())
        warn_mock.assert_called_once()


def test_batched_command():
    bc = BatchedCommand(cmd=[sys.executable, "-i", "-u", "-q", "-"])
    response = bc("print('a')")
    assert_equal(response, "a")
    response = bc("print(2 + 1)")
    assert_equal(response, "3")
    stderr = bc.close(return_stderr=True)
    assert_is_not_none(stderr)


def test_batched_close_abandon():
    # Expect a timeout if the process runs longer than timeout and the config
    # for "datalad.runtime.stalled-external" is "abandon".
    bc = BatchedCommand(
        cmd=[sys.executable, "-i", "-u", "-q", "-"],
        timeout=.1)
    # Send at least one instruction to start the subprocess
    response = bc("import time; print('a')")
    assert_equal(response, "a")
    bc.stdin_queue.put("time.sleep(2); exit(1)\n".encode())
    with unittest.mock.patch("datalad.cfg") as cfg_mock:
        cfg_mock.configure_mock(**{"obtain.return_value": "abandon"})
        bc.close(return_stderr=False)
        assert_true(bc.wait_timed_out is True)
        assert_is_none(bc.return_code)


def test_batched_close_timeout_exception():
    # Expect a timeout if the process runs longer than timeout and the config
    # for "datalad.runtime.stalled-external" is "abandon".
    bc = BatchedCommand(
        cmd=[sys.executable, "-i", "-u", "-q", "-"],
        timeout=.5,
        exception_on_timeout=True)

    # Send at least one instruction to start the subprocess
    response = bc("import time; print('a')")
    assert_equal(response, "a")
    bc.stdin_queue.put("time.sleep(2); exit(1)\n".encode())
    with unittest.mock.patch("datalad.cfg") as cfg_mock:
        cfg_mock.configure_mock(**{"obtain.return_value": "abandon"})
        assert_raises(TimeoutExpired, bc.close)


def test_batched_close_wait():
    # Expect a long wait and no timeout if the process runs longer than timeout
    # and the config for "datalad.runtime.stalled-external" has its default
    # value.
    bc = BatchedCommand(
        cmd=[sys.executable, "-i", "-u", "-q", "-"],
        timeout=.5)
    # Send at least one instruction to start the subprocess
    response = bc("import time; print('a')")
    assert_equal(response, "a")
    bc.stdin_queue.put("time.sleep(2); exit(2)\n".encode())
    bc.close(return_stderr=False)
    assert_true(bc.wait_timed_out is False)
    assert_equal(bc.return_code, 2)


def test_batched_close_ok():
    # Expect a long wait and no timeout if the process runs longer than timeout
    # seconds and the config for "datalad.runtime.stalled-external" has its
    # default value.
    bc = BatchedCommand(
        cmd=[sys.executable, "-i", "-u", "-q", "-"],
        timeout=2)
    # Send at least one instruction to start the subprocess
    response = bc("import time; print('a')")
    assert_equal(response, "a")
    bc.stdin_queue.put("time.sleep(.5); exit(3)\n".encode())
    bc.close(return_stderr=False)
    assert_true(bc.wait_timed_out is False)
    assert_equal(bc.return_code, 3)


def test_tuple_requests():
    bc = BatchedCommand(
        cmd=py2cmd(
            """
import time
import sys
print(f"{time.time()}:{sys.stdin.readline().strip()}")
            """))

    start_time_1, line = bc(("one", "line")).split(":")
    assert_equal(line, "one line")
    start_time_2, line = bc(("end", "now")).split(":")
    assert_not_equal(start_time_1, start_time_2)
    assert_equal(line, "end now")
    bc.close(return_stderr=False)


def test_batched_restart():
    # Expect that the process is restarted after exit.
    bc = BatchedCommand(
        cmd=py2cmd(
            "import os\n"
            "import sys\n"
            "print(os.getpid(), sys.stdin.readline().strip())\n"))

    # Send four lines
    lines = [f"line-{i}" for i in range(4)]
    responses = [bc(lines[i]).split() for i in range(4)]
    pid_set = set([int(r[0]) for r in responses])
    assert_equal(len(pid_set), 4)
    response_lines = [r[1] for r in responses]
    assert_equal(lines, response_lines)
    bc.close(return_stderr=False)


def test_command_fail_1():
    # Expect that a failing command raises a CommandError in which the return
    # code and the last successful request is caught, and that the command is
    # restarted when called again
    bc = BatchedCommand(
        cmd=py2cmd(
            """
print("something")
exit(3)
            """))

    # Send something to start the process
    first_request = "line one"
    result = bc(first_request)
    assert bc.return_code is None
    assert result == "something"
    with pytest.raises(BatchedCommandError) as exception_info:
        bc("line two")
    assert exception_info.value.code == 3
    assert exception_info.value.last_processed_request == first_request
    assert bc.return_code == 3

    # Check for restart
    result = bc(first_request)
    assert result == "something"
    bc.close(return_stderr=False)


def test_command_fail_2():
    # Expect that a failing command raises a BatchedCommandError in which the
    # return code and the last successful request is caught. In this case the
    # last successful request should be None.
    bc = BatchedCommand(
        cmd=py2cmd(
            """
print(a*b)
            """))

    # Send something to start the process
    first_request = "line one"
    with pytest.raises(BatchedCommandError) as exception_info:
        _ = bc(first_request)
    assert exception_info.value.code == 1
    assert exception_info.value.last_processed_request is None
    assert bc.return_code == 1
    assert bc.last_request is None
    bc.close(return_stderr=False)
