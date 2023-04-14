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
import time
from collections.abc import (
    Generator,
    Iterator,
)
from itertools import count
from queue import Queue
from threading import Thread
from time import sleep
from typing import (
    Any,
    Optional,
)
from unittest.mock import (
    MagicMock,
    patch,
)

import pytest

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
from ..utils import LineSplitter
from .utils import py2cmd


# Protocol classes used for a set of generator tests later
class GenStdoutStderr(GeneratorMixIn, StdOutErrCapture):
    def __init__(self,
                 done_future: Any = None,
                 encoding: Optional[str] = None) -> None:

        StdOutErrCapture.__init__(
            self,
            done_future=done_future,
            encoding=encoding)
        GeneratorMixIn.__init__(self)

    def timeout(self, fd: Optional[int]) -> bool:
        return True


class GenNothing(GeneratorMixIn, NoCapture):
    def __init__(self,
                 done_future: Any = None,
                 encoding: Optional[str] = None) -> None:

        NoCapture.__init__(
            self,
            done_future=done_future,
            encoding=encoding)
        GeneratorMixIn.__init__(self)


class GenStdoutLines(GeneratorMixIn, StdOutCapture):
    """A generator-based protocol yielding individual subprocess' stdout lines

    This is a simple implementation that is good enough for tests, i.e. with
    controlled inpute. It will fail if data is delivered in parts to
    self.pipe_data_received that are split inside an encoded character.
    """
    def __init__(self,
                 done_future: Any = None,
                 encoding: Optional[str] = None) -> None:

        StdOutCapture.__init__(
            self,
            done_future=done_future,
            encoding=encoding)
        GeneratorMixIn.__init__(self)
        self.line_splitter = LineSplitter()

    def timeout(self, fd: Optional[int]) -> bool:
        return True

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        for line in self.line_splitter.process(data.decode(self.encoding)):
            self.send_result(line)

    def pipe_connection_lost(self, fd: int, exc: Optional[BaseException]) -> None:
        remaining_line = self.line_splitter.finish_processing()
        if remaining_line is not None:
            self.send_result(remaining_line)


def test_subprocess_return_code_capture() -> None:

    class KillProtocol(Protocol):

        proc_out = True
        proc_err = True

        def __init__(self, signal_to_send: int, result_pool: dict) -> None:
            super().__init__()
            self.signal_to_send = signal_to_send
            self.result_pool = result_pool

        def connection_made(self, process: subprocess.Popen) -> None:
            super().connection_made(process)
            process.send_signal(self.signal_to_send)

        def connection_lost(self, exc: Optional[BaseException]) -> None:
            self.result_pool["connection_lost_called"] = (True, exc)

        def process_exited(self) -> None:
            self.result_pool["process_exited_called"] = True

    # windows doesn't support SIGINT but would need a Ctrl-C
    signal_to_send = signal.SIGTERM if on_windows else signal.SIGINT
    result_pool: dict[str, Any] = dict()
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
    assert isinstance(result, dict)
    if not on_windows:
        # this one specifically tests the SIGINT case, which is not supported
        # on windows
        eq_(result["code"], -signal_to_send)
    assert_true(result_pool["connection_lost_called"][0])
    assert_true(result_pool["process_exited_called"])


def test_interactive_communication() -> None:

    class BidirectionalProtocol(Protocol):

        proc_out = True
        proc_err = True

        def __init__(self, result_pool: dict[str, bool]) -> None:
            super().__init__()
            self.state = 0
            self.result_pool = result_pool

        def connection_made(self, process: subprocess.Popen) -> None:
            super().connection_made(process)
            assert self.process is not None
            assert self.process.stdin is not None
            os.write(self.process.stdin.fileno(), b"1 + 1\n")

        def connection_lost(self, exc: Optional[BaseException]) -> None:
            self.result_pool["connection_lost_called"] = True

        def process_exited(self) -> None:
            self.result_pool["process_exited_called"] = True

        def pipe_data_received(self, fd: int, data: bytes) -> None:
            super().pipe_data_received(fd, data)
            assert self.process is not None
            assert self.process.stdin is not None
            if self.state == 0:
                self.state += 1
                os.write(self.process.stdin.fileno(), b"2 ** 3\n")
            if self.state == 1:
                self.state += 1
                os.write(self.process.stdin.fileno(), b"exit(0)\n")

    result_pool: dict[str, bool] = dict()
    result = run_command([sys.executable, "-i"],
                         BidirectionalProtocol,
                         stdin=subprocess.PIPE,
                         protocol_kwargs={
                            "result_pool": result_pool
                         })

    assert isinstance(result, dict)
    lines = [line.strip() for line in result["stdout"].splitlines()]
    eq_(lines, ["2", "8"])
    assert_true(result_pool["connection_lost_called"], True)
    assert_true(result_pool["process_exited_called"], True)


def test_blocking_thread_exit() -> None:
    read_queue: Queue[tuple[Any, IOState, bytes]] = queue.Queue()

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


def test_blocking_read_exception_catching() -> None:
    read_queue: Queue[tuple[Any, IOState, Any]] = queue.Queue()

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


def test_blocking_read_closing() -> None:
    # Expect that a reader thread exits when os.read throws an error.
    fake_file = MagicMock(**{"fileno.return_value": -1, "close.return_value": None})

    def fake_read(*args: Any) -> None:
        raise ValueError("test exception")

    read_queue: Queue[tuple[Any, IOState, Optional[bytes]]] = queue.Queue()
    destination_queue: Queue[tuple[Any, IOState, bytes]] = queue.Queue()
    with patch("datalad.runner.runnerthreads.os.read") as read:
        read.side_effect = fake_read

        read_thread = ReadThread(
            identifier="test thread",
            user_info=None,
            source=fake_file,
            destination_queue=destination_queue,
            signal_queues=[read_queue])

        read_thread.start()
        read_thread.join()

    identifier, state, data = read_queue.get()
    eq_(data, None)


def test_blocking_write_exception_catching() -> None:
    # Expect that a blocking writer catches exceptions and exits gracefully.

    write_queue: Queue[Optional[bytes]] = queue.Queue()
    signal_queue: Queue[tuple[Any, IOState, Optional[bytes]]] = queue.Queue()

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


def test_blocking_writer_closing() -> None:
    # Expect that a blocking writer closes its file when `None` is sent to it.
    write_queue: Queue[Optional[bytes]] = queue.Queue()
    signal_queue: Queue[tuple[Any, IOState, Optional[bytes]]] = queue.Queue()

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


def test_blocking_writer_closing_timeout_signal() -> None:
    # Expect that writer or reader do not block forever on a full signal queue

    write_queue: Queue[Optional[bytes]] = queue.Queue()
    signal_queue: Queue[tuple[Any, IOState, Optional[bytes]]] = queue.Queue(1)
    signal_queue.put(("This is data", IOState.ok, None))

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
    eq_(signal_queue.get(), ("This is data", IOState.ok, None))


def test_blocking_writer_closing_no_signal() -> None:
    # Expect that writer or reader do not block forever on a full signal queue

    write_queue: Queue[Optional[bytes]] = queue.Queue()
    signal_queue: Queue[tuple[Any, IOState, Optional[bytes]]] = queue.Queue(1)
    signal_queue.put(("This is data", IOState.ok, None))

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


def test_inside_async() -> None:
    async def main() -> dict:
        runner = Runner()
        res = runner.run(
            (["cmd.exe", "/c"] if on_windows else []) + ["echo", "abc"],
            StdOutCapture)
        assert isinstance(res, dict)
        return res

    result = asyncio.run(main())
    eq_(result["stdout"], "abc" + os.linesep)


# Both Windows and OSX suffer from wrapt's object proxy insufficiency
# NotImplementedError: object proxy must define __reduce_ex__()
@known_failure_osx
@known_failure_windows
@with_tempfile(mkdir=True)
@with_tempfile
def test_popen_invocation(src_path: str = "", dest_path: str = "") -> None:
    # https://github.com/ReproNim/testkraken/issues/93
    from multiprocessing import Process

    from datalad.api import clone  # type: ignore[attr-defined]
    from datalad.distribution.dataset import Dataset

    src = Dataset(src_path).create()
    (src.pathobj / "file.dat").write_bytes(b"\000")
    src.save(message="got data")

    dest = clone(source=src_path, path=dest_path)
    fetching_data = Process(target=dest.get, kwargs={"path": 'file.dat'})
    fetching_data.start()
    fetching_data.join(5.0)
    assert_false(fetching_data.is_alive(), "Child is stuck!")


def test_timeout() -> None:
    # Expect timeout protocol calls on long running process
    # if the specified timeout is short enough
    class TestProtocol(StdOutErrCapture):

        received_timeouts: list[tuple[int, Optional[int]]] = []

        def __init__(self) -> None:
            StdOutErrCapture.__init__(self)
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            TestProtocol.received_timeouts.append((next(self.counter), fd))
            return False

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


def test_timeout_nothing() -> None:
    # Expect timeout protocol calls for the process on long running processes,
    # if the specified timeout is short enough.
    class TestProtocol(NoCapture):
        def __init__(self,
                     timeout_queue: list[Optional[int]]) -> None:
            NoCapture.__init__(self)
            self.timeout_queue = timeout_queue
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            self.timeout_queue.append(fd)
            return False

    stdin_queue: Queue[Optional[bytes]] = queue.Queue()
    for i in range(12):
        stdin_queue.put(b"\x00" * 1024)
    stdin_queue.put(None)

    timeout_queue: list[Optional[int]] = []
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


def test_timeout_stdout_stderr() -> None:
    # Expect timeouts on stdin, stdout, stderr, and the process
    class TestProtocol(StdOutErrCapture):
        def __init__(self,
                     timeout_queue: list[tuple[int, Optional[int]]]) -> None:
            StdOutErrCapture.__init__(self)
            self.timeout_queue = timeout_queue
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            self.timeout_queue.append((next(self.counter), fd))
            return False

    stdin_queue: Queue[Optional[bytes]] = queue.Queue()
    for i in range(12):
        stdin_queue.put(b"\x00" * 1024)
    stdin_queue.put(None)

    timeout_queue: list[tuple[int, Optional[int]]] = []
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
        assert_true(any(fd == source for _, fd in timeout_queue))


def test_timeout_process() -> None:
    # Expect timeouts on stdin, stdout, stderr, and the process
    class TestProtocol(StdOutErrCapture):
        def __init__(self,
                     timeout_queue: list[tuple[int, Optional[int]]]) -> None:
            StdOutErrCapture.__init__(self)
            self.timeout_queue = timeout_queue
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            self.timeout_queue.append((next(self.counter), fd))
            return False

    stdin_queue: Queue[Optional[bytes]] = queue.Queue()
    for i in range(12):
        stdin_queue.put(b"\x00" * 1024)
    stdin_queue.put(None)

    timeout_queue: list[tuple[int, Optional[int]]] = []
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
        assert_true(any(fd == source for _, fd in timeout_queue))


def test_exit_3() -> None:
    # Expect the process to be closed after
    # the generator exits.
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenStdoutStderr,
                        timeout=.5,
                        exception_on_error=False)
    tuple(rt.run())
    assert_true(rt.return_code is not None)


def test_exit_4() -> None:
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenNothing,
                        timeout=.5)
    tuple(rt.run())
    assert_true(rt.return_code is not None)


def test_generator_throw() -> None:
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenNothing,
                        timeout=.5)
    gen = rt.run()
    assert isinstance(gen, Generator)
    assert_raises(ValueError, gen.throw, ValueError, ValueError("abcdefg"))


def test_exiting_process() -> None:
    result = run_command(py2cmd("import time\ntime.sleep(3)\nprint('exit')"),
                         protocol=NoCapture,
                         stdin=None)
    assert isinstance(result, dict)
    eq_(result["code"], 0)


def test_stalling_detection_1() -> None:
    runner = ThreadedRunner("something", StdOutErrCapture, None)
    runner.stdout_enqueueing_thread = None
    runner.stderr_enqueueing_thread = None
    runner.process_waiting_thread = None
    with patch("datalad.runner.nonasyncrunner.lgr") as logger:
        runner.process_queue()
    eq_(logger.method_calls[0][0], "warning")
    eq_(logger.method_calls[0][1][0], "ThreadedRunner.process_queue(): stall detected")


def test_stalling_detection_2() -> None:
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


def test_concurrent_waiting_run() -> None:
    from threading import Thread

    threaded_runner = ThreadedRunner(
        py2cmd("import time; time.sleep(1)"),
        protocol_class=NoCapture,
        stdin=None,
    )

    start = time.time()

    number_of_threads = 5
    caller_threads = []
    for c in range(number_of_threads):
        caller_thread = Thread(target=threaded_runner.run)
        caller_thread.start()
        caller_threads.append(caller_thread)

    while caller_threads:
        t = caller_threads.pop()
        t.join()

    # If the threads are serialized, the duration should at least
    # be one second per thread.
    duration = time.time() - start
    assert duration >= 1.0 * number_of_threads


def test_concurrent_generator_reading() -> None:
    number_of_lines = 40
    number_of_threads = 100
    output_queue: Queue[tuple[int, Optional[str]]] = Queue()

    threaded_runner = ThreadedRunner(
        py2cmd(f"for i in range({number_of_lines}): print(f'result#{{i}}')"),
        protocol_class=GenStdoutLines,
        stdin=None,
    )
    result_generator = threaded_runner.run()

    def thread_main(thread_number: int, result_generator: Iterator[str], output_queue: Queue[tuple[int, Optional[str]]]) -> None:
        while True:
            try:
                output = next(result_generator)
            except StopIteration:
                output_queue.put((thread_number, None))
                break
            output_queue.put((thread_number, output))

    caller_threads = []
    for c in range(number_of_threads):
        caller_thread = Thread(
            target=thread_main,
            args=(c, result_generator, output_queue)
        )
        caller_thread.start()
        caller_threads.append(caller_thread)

    while caller_threads:
        t = caller_threads.pop()
        t.join()

    collected_outputs = [
        output_tuple[1]
        for output_tuple in output_queue.queue
        if output_tuple[1] is not None
    ]
    assert len(collected_outputs) == number_of_lines
    assert collected_outputs == [
        f"result#{i}"
        for i in range(number_of_lines)
    ]


def test_same_thread_reenter_detection() -> None:
    threaded_runner = ThreadedRunner(
        py2cmd(f"print('hello')"),
        protocol_class=GenStdoutLines,
        stdin=None,
    )
    threaded_runner.run()
    with pytest.raises(RuntimeError) as error:
        threaded_runner.run()
    assert "re-entered by already" in str(error.value)


def test_reenter_generator_detection() -> None:
    threaded_runner = ThreadedRunner(
        py2cmd(f"print('hello')"),
        protocol_class=GenStdoutLines,
        stdin=None,
    )

    def target(threaded_runner: ThreadedRunner, output_queue: Queue[tuple[str, float | BaseException]]) -> None:
        try:
            start_time = time.time()
            tuple(threaded_runner.run())
            output_queue.put(("result", time.time() - start_time))
        except RuntimeError as exc:
            output_queue.put(("exception", exc))

    output_queue: Queue[tuple[str, float | BaseException]] = Queue()

    for sleep_time in range(1, 4):
        other_thread = Thread(
            target=target,
            args=(threaded_runner, output_queue)
        )

        gen = threaded_runner.run()
        other_thread.start()
        time.sleep(sleep_time)
        tuple(gen)
        other_thread.join()

        assert len(list(output_queue.queue)) == 1
        result_type, value = output_queue.get()
        assert result_type == "result"
        assert isinstance(value, float)
        assert value >= sleep_time
