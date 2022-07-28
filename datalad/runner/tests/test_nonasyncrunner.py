# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test the thread based runner (aka. non asyncio based runner).
"""
from __future__ import annotations

import asyncio
import os
import queue
import signal
import subprocess
import sys
from itertools import count
from time import sleep
from typing import Optional
from unittest.mock import (
    MagicMock,
    patch,
)

from datalad.tests.utils_pytest import (
    assert_false,
    assert_raises,
    assert_true,
    eq_,
    known_failure_osx,
    known_failure_windows,
    with_tempfile,
)
from datalad.utils import on_windows

from .. import (
    NoCapture,
    Protocol,
    Runner,
    StdOutCapture,
    StdOutErrCapture,
)
from ..nonasyncrunner import (
    IOState,
    ThreadedRunner,
    run_command,
)
from ..protocol import GeneratorMixIn
from ..runnerthreads import (
    ReadThread,
    WriteThread,
)
from .utils import py2cmd


# Protocol classes used for a set of generator tests later
class GenStdoutStderr(GeneratorMixIn, StdOutErrCapture):
    def __init__(self,
                 done_future=None,
                 encoding=None):

        StdOutErrCapture.__init__(
            self,
            done_future=done_future,
            encoding=encoding)
        GeneratorMixIn.__init__(self)

    def timeout(self, fd: Optional[int]) -> bool:
        return True


class GenNothing(GeneratorMixIn, NoCapture):
    def __init__(self,
                 done_future=None,
                 encoding=None):

        NoCapture.__init__(
            self,
            done_future=done_future,
            encoding=encoding)
        GeneratorMixIn.__init__(self)


def test_subprocess_return_code_capture():

    class KillProtocol(Protocol):

        proc_out = True
        proc_err = True

        def __init__(self, signal_to_send: int, result_pool: dict):
            super().__init__()
            self.signal_to_send = signal_to_send
            self.result_pool = result_pool

        def connection_made(self, process):
            super().connection_made(process)
            process.send_signal(self.signal_to_send)

        def connection_lost(self, exc):
            self.result_pool["connection_lost_called"] = (True, exc)

        def process_exited(self):
            self.result_pool["process_exited_called"] = True

    # windows doesn't support SIGINT but would need a Ctrl-C
    signal_to_send = signal.SIGTERM if on_windows else signal.SIGINT
    result_pool = dict()
    result = run_command(["waitfor", "/T", "10000", "TheComputerTurnsIntoATulip"]
                         if on_windows
                         else ["sleep", "10000"],
                         KillProtocol,
                         None,
                         {
                             "signal_to_send": signal_to_send,
                             "result_pool": result_pool
                         },
                         exception_on_error=False)
    if not on_windows:
        # this one specifically tests the SIGINT case, which is not supported
        # on windows
        eq_(result["code"], -signal_to_send)
    assert_true(result_pool["connection_lost_called"][0])
    assert_true(result_pool["process_exited_called"])


def test_interactive_communication():

    class BidirectionalProtocol(Protocol):

        proc_out = True
        proc_err = True

        def __init__(self, result_pool: dict):
            super().__init__()
            self.state = 0
            self.result_pool = result_pool

        def connection_made(self, process):
            super().connection_made(process)
            os.write(self.process.stdin.fileno(), b"1 + 1\n")

        def connection_lost(self, exc):
            self.result_pool["connection_lost_called"] = True

        def process_exited(self):
            self.result_pool["process_exited_called"] = True

        def pipe_data_received(self, fd, data):
            super().pipe_data_received(fd, data)
            if self.state == 0:
                self.state += 1
                os.write(self.process.stdin.fileno(), b"2 ** 3\n")
            if self.state == 1:
                self.state += 1
                os.write(self.process.stdin.fileno(), b"exit(0)\n")

    result_pool = dict()
    result = run_command([sys.executable, "-i"],
                         BidirectionalProtocol,
                         stdin=subprocess.PIPE,
                         protocol_kwargs={
                            "result_pool": result_pool
                         })

    lines = [line.strip() for line in result["stdout"].splitlines()]
    eq_(lines, ["2", "8"])
    assert_true(result_pool["connection_lost_called"], True)
    assert_true(result_pool["process_exited_called"], True)


def test_blocking_thread_exit():
    read_queue = queue.Queue()

    (read_descriptor, write_descriptor) = os.pipe()
    read_file = os.fdopen(read_descriptor, "rb")
    read_thread = ReadThread(
        identifier="test thread",
        user_info=read_descriptor,
        source=read_file,
        destination_queue=read_queue,
        signal_queues=[]
    )
    read_thread.start()

    os.write(write_descriptor, b"some data")
    assert_true(read_thread.is_alive())
    identifier, state, data = read_queue.get()
    eq_(data, b"some data")

    read_thread.request_exit()

    # Check the blocking part
    sleep(.3)
    assert_true(read_thread.is_alive())

    # Check actual exit, we will not get
    # "more data" when exit was requested,
    # because the thread will not attempt
    # a write
    os.write(write_descriptor, b"more data")
    read_thread.join()
    print(read_queue.queue)
    assert_true(read_queue.empty())


def test_blocking_read_exception_catching():
    read_queue = queue.Queue()

    (read_descriptor, write_descriptor) = os.pipe()
    read_file = os.fdopen(read_descriptor, "rb")
    read_thread = ReadThread(
        identifier="test thread",
        user_info=read_descriptor,
        source=read_file,
        destination_queue=read_queue,
        signal_queues=[read_queue]
    )
    read_thread.start()

    os.write(write_descriptor, b"some data")
    assert_true(read_thread.is_alive())
    identifier, state, data = read_queue.get()
    eq_(data, b"some data")
    os.close(write_descriptor)
    read_thread.join()
    identifier, state, data = read_queue.get()
    eq_(data, None)


def test_blocking_read_closing():
    # Expect that a reader thread exits when os.read throws an error.
    class FakeFile:
        def fileno(self):
            return -1

        def close(self):
            pass

    def fake_read(*args):
        raise ValueError("test exception")

    read_queue = queue.Queue()
    with patch("datalad.runner.runnerthreads.os.read") as read:
        read.side_effect = fake_read

        read_thread = ReadThread(
            identifier="test thread",
            user_info=None,
            source=FakeFile(),
            destination_queue=None,
            signal_queues=[read_queue])

        read_thread.start()
        read_thread.join()

    identifier, state, data = read_queue.get()
    eq_(data, None)


def test_blocking_write_exception_catching():
    # Expect that a blocking writer catches exceptions and exits gracefully.

    write_queue = queue.Queue()
    signal_queue = queue.Queue()

    (read_descriptor, write_descriptor) = os.pipe()
    write_file = os.fdopen(write_descriptor, "rb")
    write_thread = WriteThread(
        identifier="test thread",
        user_info=write_descriptor,
        source_queue=write_queue,
        destination=write_file,
        signal_queues=[signal_queue]
    )
    write_thread.start()

    write_queue.put(b"some data")
    data = os.read(read_descriptor, 1024)
    eq_(data, b"some data")

    os.close(read_descriptor)
    os.close(write_descriptor)

    write_queue.put(b"more data")
    write_thread.join()
    eq_(signal_queue.get(), (write_descriptor, IOState.ok, None))


def test_blocking_writer_closing():
    # Expect that a blocking writer closes its file when `None` is sent to it.
    write_queue = queue.Queue()
    signal_queue = queue.Queue()

    (read_descriptor, write_descriptor) = os.pipe()
    write_file = os.fdopen(write_descriptor, "rb")
    write_thread = WriteThread(
        identifier="test thread",
        user_info=write_descriptor,
        source_queue=write_queue,
        destination=write_file,
        signal_queues=[signal_queue]
    )
    write_thread.start()

    write_queue.put(b"some data")
    data = os.read(read_descriptor, 1024)
    eq_(data, b"some data")

    write_queue.put(None)
    write_thread.join()
    eq_(signal_queue.get(), (write_descriptor, IOState.ok, None))


def test_blocking_writer_closing_timeout_signal():
    # Expect that writer or reader do not block forever on a full signal queue

    write_queue = queue.Queue()
    signal_queue = queue.Queue(1)
    signal_queue.put("This is data")

    (read_descriptor, write_descriptor) = os.pipe()
    write_file = os.fdopen(write_descriptor, "rb")
    write_thread = WriteThread(
        identifier="test thread",
        user_info=write_descriptor,
        source_queue=write_queue,
        destination=write_file,
        signal_queues=[signal_queue]
    )
    write_thread.start()

    write_queue.put(b"some data")
    data = os.read(read_descriptor, 1024)
    eq_(data, b"some data")

    write_queue.put(None)
    write_thread.join()
    eq_(signal_queue.get(), "This is data")


def test_blocking_writer_closing_no_signal():
    # Expect that writer or reader do not block forever on a full signal queue

    write_queue = queue.Queue()
    signal_queue = queue.Queue(1)
    signal_queue.put("This is data")

    (read_descriptor, write_descriptor) = os.pipe()
    write_file = os.fdopen(write_descriptor, "rb")
    write_thread = WriteThread(
        identifier="test thread",
        user_info=write_descriptor,
        source_queue=write_queue,
        destination=write_file,
        signal_queues=[signal_queue]
    )
    write_thread.start()

    write_queue.put(b"some data")
    data = os.read(read_descriptor, 1024)
    eq_(data, b"some data")

    write_queue.put(None)
    write_thread.join()


def test_inside_async():
    async def main():
        runner = Runner()
        return runner.run(
            (["cmd.exe", "/c"] if on_windows else []) + ["echo", "abc"],
            StdOutCapture)

    result = asyncio.run(main())
    eq_(result["stdout"], "abc" + os.linesep)


# Both Windows and OSX suffer from wrapt's object proxy insufficiency
# NotImplementedError: object proxy must define __reduce_ex__()
@known_failure_osx
@known_failure_windows
@with_tempfile(mkdir=True)
@with_tempfile
def test_popen_invocation(src_path=None, dest_path=None):
    # https://github.com/ReproNim/testkraken/issues/93
    from multiprocessing import Process

    from datalad.api import clone
    from datalad.distribution.dataset import Dataset

    src = Dataset(src_path).create()
    (src.pathobj / "file.dat").write_bytes(b"\000")
    src.save(message="got data")

    dest = clone(source=src_path, path=dest_path)
    fetching_data = Process(target=dest.get, kwargs={"path": 'file.dat'})
    fetching_data.start()
    fetching_data.join(5.0)
    assert_false(fetching_data.is_alive(), "Child is stuck!")


def test_timeout():
    # Expect timeout protocol calls on long running process
    # if the specified timeout is short enough
    class TestProtocol(StdOutErrCapture):

        received_timeouts = list()

        def __init__(self):
            StdOutErrCapture.__init__(self)
            self.counter = count()

        def timeout(self, fd: Optional[int]):
            TestProtocol.received_timeouts.append((self.counter.__next__(), fd))

    run_command(
        ["waitfor", "/T", "1", "TheComputerTurnsIntoATulip"]
        if on_windows
        else ["sleep", "1"],
        stdin=None,
        protocol=TestProtocol,
        timeout=.1
    )
    assert_true(len(TestProtocol.received_timeouts) > 0)
    assert_true(all(map(lambda e: e[1] in (1, 2, None), TestProtocol.received_timeouts)))


def test_timeout_nothing():
    # Expect timeout protocol calls for the process on long running processes,
    # if the specified timeout is short enough.
    class TestProtocol(NoCapture):
        def __init__(self,
                     timeout_queue: list):
            NoCapture.__init__(self)
            self.timeout_queue = timeout_queue
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            self.timeout_queue.append(fd)
            return False

    stdin_queue = queue.Queue()
    for i in range(12):
        stdin_queue.put(b"\x00" * 1024)
    stdin_queue.put(None)

    timeout_queue = []
    run_command(
        py2cmd("import time; time.sleep(.4)\n"),
        stdin=stdin_queue,
        protocol=TestProtocol,
        timeout=.1,
        protocol_kwargs=dict(timeout_queue=timeout_queue)
    )
    # Ensure that we have only process timeouts and at least one
    assert_true(all(map(lambda e: e is None, timeout_queue)))
    assert_true(len(timeout_queue) > 0)


def test_timeout_stdout_stderr():
    # Expect timeouts on stdin, stdout, stderr, and the process
    class TestProtocol(StdOutErrCapture):
        def __init__(self,
                     timeout_queue: list):
            StdOutErrCapture.__init__(self)
            self.timeout_queue = timeout_queue
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            self.timeout_queue.append((self.counter.__next__(), fd))
            return False

    stdin_queue = queue.Queue()
    for i in range(12):
        stdin_queue.put(b"\x00" * 1024)
    stdin_queue.put(None)

    timeout_queue = []
    run_command(
        py2cmd("import time;time.sleep(.5)\n"),
        stdin=stdin_queue,
        protocol=TestProtocol,
        timeout=.1,
        protocol_kwargs=dict(timeout_queue=timeout_queue)
    )

    # Expect at least one timeout for stdout and stderr.
    # there might be more.
    sources = (1, 2)
    assert_true(len(timeout_queue) >= len(sources))
    for source in sources:
        assert_true(any(filter(lambda t: t[1] == source, timeout_queue)))


def test_timeout_process():
    # Expect timeouts on stdin, stdout, stderr, and the process
    class TestProtocol(StdOutErrCapture):
        def __init__(self,
                     timeout_queue: list):
            StdOutErrCapture.__init__(self)
            self.timeout_queue = timeout_queue
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            self.timeout_queue.append((self.counter.__next__(), fd))
            return False

    stdin_queue = queue.Queue()
    for i in range(12):
        stdin_queue.put(b"\x00" * 1024)
    stdin_queue.put(None)

    timeout_queue = []
    run_command(
        py2cmd("import time;time.sleep(.5)\n"),
        stdin=stdin_queue,
        protocol=TestProtocol,
        timeout=.1,
        protocol_kwargs=dict(timeout_queue=timeout_queue)
    )

    # Expect at least one timeout for stdout and stderr.
    # there might be more.
    sources = (1, 2)
    assert_true(len(timeout_queue) >= len(sources))
    for source in sources:
        assert_true(any(filter(lambda t: t[1] == source, timeout_queue)))


def test_exit_3():
    # Expect the process to be closed after
    # the generator exits.
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenStdoutStderr,
                        timeout=.5,
                        exception_on_error=False)
    tuple(rt.run())
    assert_true(rt.process.poll() is not None)


def test_exit_4():
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenNothing,
                        timeout=.5)
    tuple(rt.run())
    assert_true(rt.process.poll() is not None)


def test_generator_throw():
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenNothing,
                        timeout=.5)
    gen = rt.run()
    assert_raises(ValueError, gen.throw, ValueError, ValueError("abcdefg"))


def test_exiting_process():
    result = run_command(py2cmd("import time\ntime.sleep(3)\nprint('exit')"),
                         protocol=NoCapture,
                         stdin=None)
    eq_(result["code"], 0)


def test_stalling_detection_1():
    runner = ThreadedRunner("something", StdOutErrCapture, None)
    runner.stdout_enqueueing_thread = None
    runner.stderr_enqueueing_thread = None
    runner.process_waiting_thread = None
    with patch("datalad.runner.nonasyncrunner.lgr") as logger:
        runner.process_queue()
    eq_(logger.method_calls[0][0], "warning")
    eq_(logger.method_calls[0][1][0], "ThreadedRunner.process_queue(): stall detected")


def test_stalling_detection_2():
    thread_mock = MagicMock()
    thread_mock.is_alive.return_value = False
    runner = ThreadedRunner("something", StdOutErrCapture, None)
    runner.stdout_enqueueing_thread = thread_mock
    runner.stderr_enqueueing_thread = thread_mock
    runner.process_waiting_thread = thread_mock
    with patch("datalad.runner.nonasyncrunner.lgr") as logger:
        runner.process_queue()
    eq_(logger.method_calls[0][0], "warning")
    eq_(logger.method_calls[0][1][0], "ThreadedRunner.process_queue(): stall detected")
