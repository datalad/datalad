# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test the thread based runner (aka. non asyncio based runner).
"""
import asyncio
import os
import queue
import signal
import subprocess
import sys
from itertools import count
from time import sleep
from typing import (
    List,
    Optional,
)
from unittest.mock import patch

from datalad.tests.utils import (
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
from ..protocol import (
    GeneratorMixIn,
    WitlessProtocol,
)
from ..runnerthreads import (
    BlockingOSReaderThread,
    BlockingOSWriterThread,
)
from .utils import py2cmd


# Protocol classes used for a set of generator tests later
class GenStdoutStderr(GeneratorMixIn, StdOutErrCapture):
    def timeout(self, fd: Optional[int]) -> bool:
        return True


class GenNothing(GeneratorMixIn, NoCapture):
    pass


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
    result = run_command(['timeout', '3'] if on_windows else ["sleep", "10000"],
                         KillProtocol,
                         None,
                         {
                             "signal_to_send": signal_to_send,
                             "result_pool": result_pool
                         })
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
    (read_descriptor, write_descriptor) = os.pipe()
    read_file = os.fdopen(read_descriptor, "rb")

    reader_thread = BlockingOSReaderThread(read_file)
    reader_thread.start()
    read_queue = reader_thread.queue

    os.write(write_descriptor, b"some data")
    assert_true(reader_thread.is_alive())
    data = read_queue.get()
    eq_(data, b"some data")

    reader_thread.request_exit()

    # Check the blocking part
    sleep(3)
    assert_true(reader_thread.is_alive())

    # Check actual exit, we will not get
    # "more data" when exit was requested,
    # because the thread will not attempt
    # a write
    os.write(write_descriptor, b"more data")
    reader_thread.join()
    assert_true(read_queue.empty())


def test_blocking_read_exception_catching():
    (read_descriptor, write_descriptor) = os.pipe()
    read_file = os.fdopen(read_descriptor, "rb")

    reader_thread = BlockingOSReaderThread(read_file)
    reader_thread.start()
    read_queue = reader_thread.queue

    os.write(write_descriptor, b"some data")
    assert_true(reader_thread.is_alive())
    data = read_queue.get()
    eq_(data, b"some data")
    os.close(write_descriptor)
    reader_thread.join()
    data = read_queue.get()
    eq_(data, None)


def test_blocking_read_closing():
    # Expect that the blocking OS reader thread
    # exits when os.read throws an error.
    class FakeFile:
        def fileno(self):
            return -1

    def fake_read(*args):
        raise ValueError("test exception")

    with patch("datalad.runner.runnerthreads.os.read") as read:
        read.side_effect = fake_read

        reader_thread = BlockingOSReaderThread(FakeFile())
        reader_thread.start()
        reader_thread.join()

    read_queue = reader_thread.queue
    data = read_queue.get()
    eq_(data, None)


def test_blocking_write_exception_catching():
    # Expect that the blocking OS writer catches exceptions
    # and exits gracefully.
    (read_descriptor, write_descriptor) = os.pipe()
    write_file = os.fdopen(write_descriptor, "rb")
    signal_queue = queue.Queue()
    writer_thread = BlockingOSWriterThread(write_file, signal_queue)
    writer_thread.start()
    writer_queue = writer_thread.queue

    writer_queue.put(b"some data")
    data = os.read(read_descriptor, 1024)
    eq_(data, b"some data")

    os.close(read_descriptor)
    os.close(write_descriptor)

    writer_queue.put(b"more data")
    writer_thread.join()
    eq_(signal_queue.get(), None)


def test_blocking_writer_closing():
    # Expect that the blocking OS writer closes
    # its file when `None` is sent to it.
    (read_descriptor, write_descriptor) = os.pipe()
    write_file = os.fdopen(write_descriptor, "rb")
    signal_queue = queue.Queue()
    writer_thread = BlockingOSWriterThread(write_file, signal_queue)
    writer_thread.start()
    writer_queue = writer_thread.queue

    writer_queue.put(b"some data")
    data = os.read(read_descriptor, 1024)
    eq_(data, b"some data")

    writer_queue.put(None)
    writer_thread.join()
    eq_(signal_queue.get(), None)


def test_blocking_writer_closing_timeout_signal():
    # Expect that the blocking OS writer does not
    # block forever on a full signal queue
    (read_descriptor, write_descriptor) = os.pipe()
    write_file = os.fdopen(write_descriptor, "rb")
    signal_queue = queue.Queue(1)
    signal_queue.put("This is data")

    writer_thread = BlockingOSWriterThread(write_file, signal_queue)
    writer_thread.start()
    writer_queue = writer_thread.queue

    writer_queue.put(b"some data")
    data = os.read(read_descriptor, 1024)
    eq_(data, b"some data")

    writer_queue.put(None)
    writer_thread.join()
    eq_(signal_queue.get(), "This is data")


def test_blocking_writer_closing_no_signal():
    (read_descriptor, write_descriptor) = os.pipe()
    write_file = os.fdopen(write_descriptor, "rb")
    writer_thread = BlockingOSWriterThread(write_file)
    writer_thread.start()
    writer_queue = writer_thread.queue

    writer_queue.put(b"some data")
    data = os.read(read_descriptor, 1024)
    eq_(data, b"some data")

    writer_queue.put(None)
    writer_thread.join()


def test_inside_async():
    async def main():
        runner = Runner()
        return runner.run(
            (["cmd.exe", "/c"] if on_windows else []) + ["echo", "abc"],
            StdOutCapture)

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(main())
    eq_(result["stdout"], "abc" + os.linesep)


# Both Windows and OSX suffer from wrapt's object proxy insufficiency
# NotImplementedError: object proxy must define __reduce_ex__()
@known_failure_osx
@known_failure_windows
@with_tempfile(mkdir=True)
@with_tempfile
def test_popen_invocation(src_path, dest_path):
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
    class TestProtocol(WitlessProtocol):

        received_timeouts = list()

        def __init__(self):
            WitlessProtocol.__init__(self)
            self.counter = count()

        def timeout(self, fd: Optional[int]):
            TestProtocol.received_timeouts.append((self.counter.__next__(), fd))

    result = run_command(
        ['timeout', '3'] if on_windows else ["sleep", "5"],
        stdin=None,
        protocol=TestProtocol,
        timeout=1
    )
    assert_true(len(TestProtocol.received_timeouts) > 0)
    assert_true(all(map(lambda e: e[1] is None, TestProtocol.received_timeouts)))


def test_timeout_nothing():
    # Expect timeout protocol calls on long running process
    # if the specified timeout is short enough
    class TestProtocol(NoCapture):
        def __init__(self,
                     timeout_queue: List):
            NoCapture.__init__(self)
            self.timeout_queue = timeout_queue
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            if fd is not None:
                self.timeout_queue.append((self.counter.__next__(), fd))
            return True

    stdin_queue = queue.Queue()
    for i in range(72):
        stdin_queue.put(b"\x00" * 1024)
    stdin_queue.put(None)

    timeout_queue = []
    run_command(
        py2cmd("import time; time.sleep(.6)\n"),
        stdin=stdin_queue,
        protocol=TestProtocol,
        timeout=.1,
        protocol_kwargs=dict(timeout_queue=timeout_queue)
    )
    eq_(len(timeout_queue), 1)


def test_timeout_all():
    # Expect timeouts on stdin, stdout, stderr, and the process
    class TestProtocol(StdOutErrCapture):
        def __init__(self,
                     timeout_queue: List):
            StdOutErrCapture.__init__(self)
            self.timeout_queue = timeout_queue
            self.counter = count()

        def timeout(self, fd: Optional[int]) -> bool:
            self.timeout_queue.append((self.counter.__next__(), fd))
            return True

    stdin_queue = queue.Queue()
    for i in range(72):
        stdin_queue.put(b"\x00" * 1024)
    stdin_queue.put(None)

    timeout_queue = []
    run_command(
        py2cmd("import time; time.sleep(.5)\n"),
        stdin=stdin_queue,
        protocol=TestProtocol,
        timeout=.1,
        protocol_kwargs=dict(timeout_queue=timeout_queue)
    )
    print(timeout_queue)
    # This is not a very nice, but on some systems the
    # stdin pipe might not be filled with the data that
    # we wrote, and will therefore not create a timeout,
    # e.g. on Windows.
    assert_true(len(timeout_queue) in (3, 4))


def test_exit_0():
    # Expect check_process_state to correctly
    # detect the process state.
    rt = ThreadedRunner(cmd=["sleep", "2"],
                        stdin=None,
                        protocol_class=GenStdoutStderr)
    rt.run()
    while rt.process_running is True:
        rt.check_process_state()
    assert_true(rt.process_running is False)
    rt.check_process_state()


def test_exit_1():
    # Expect wait_for_process to correctly
    # wait for the running process
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenNothing,
                        timeout=.5)
    rt.run()
    while rt.wait_for_process() is True:
       pass
    assert_true(rt.process.poll() is not None)


def test_exit_2():
    # Expect wait_for_process to correctly
    # wait for the running process, and
    # close file handles
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenStdoutStderr,
                        timeout=.5)
    rt.run()
    while rt.wait_for_process() is True:
       pass
    assert_true(rt.process.poll() is not None)


def test_exit_3():
    # Expect the process to be closed after
    # the generator exits.
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenStdoutStderr,
                        timeout=.5,
                        exception_on_error=False)
    for x in rt.run():
        print(x)
    assert_true(rt.process.poll() is not None)


def test_generator_exit_3():
    # Expect generator to wait for process exit
    # after the result queue is empty in
    # `GeneratorState.process_running`.
    patch_state = [0]

    def fake_wait_for_process():
        if patch_state[0] == 0:
            patch_state[0] = 1
            return True
        patch_state[0] += 1
        return False

    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenStdoutStderr,
                        timeout=.5,
                        exception_on_error=False)
    rt.wait_for_process = fake_wait_for_process
    rt.wait_for_threads = lambda: None
    for _ in rt.run():
        pass
    assert_true(rt.process.poll() is None)


def test_exit_4():
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenNothing,
                        timeout=.5)
    for x in rt.run():
        print(x)
    assert_true(rt.process.poll() is not None)


def test_process_queue():
    called = []
    rt = ThreadedRunner(cmd=["sleep", "4"],
                        stdin=None,
                        protocol_class=GenNothing,
                        timeout=.5)
    rt.output_queue = queue.Queue()

    def fake_check():
        called.append(True)
        rt.output_queue.put((1000, IOState.ok, b"XXXX"))

    rt.check_process_state = fake_check
    rt.process_queue()
    eq_(called, [True])


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
