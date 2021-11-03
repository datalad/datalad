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
from time import sleep
from typing import (
    List,
    Optional,
)
from itertools import count

from datalad.tests.utils import (
    assert_false,
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
from ..nonasyncrunner import run_command
from ..protocol import WitlessProtocol
from ..runnerthreads import (
    BlockingOSReaderThread,
    BlockingOSWriterThread,
)


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
    class FakeFile:
        def fileno(self):
            return 33

    reader_thread = BlockingOSReaderThread(FakeFile())
    reader_thread.start()
    read_queue = reader_thread.queue

    reader_thread.join()
    data = read_queue.get()
    eq_(data, None)


def test_blocking_write_exception_catching():
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

    class TestProtocol(WitlessProtocol):
        def __init__(self):
            WitlessProtocol.__init__(self)
            self.received_timeouts = list()
            self.counter = count()

        def timeout(self, fd: Optional[int]):
            print(self.counter.__next__(), "YYY", fd)

    result = run_command(
        ['timeout', '3'] if on_windows else ["sleep", "5"],
        stdin=None,
        protocol=TestProtocol,
        timeout=1
    )


def test_timeout_nothing():

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
        [
            "python",
            "-c",
            "import time; time.sleep(5)\n"
        ],
        stdin=stdin_queue,
        protocol=TestProtocol,
        timeout=1,
        protocol_kwargs=dict(timeout_queue=timeout_queue)
    )
    eq_(len(timeout_queue), 1)


def test_timeout_all():

    class TestProtocol(StdOutErrCapture):
        def __init__(self,
                     timeout_queue: List):
            StdOutErrCapture.__init__(self)
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
        [
            "python",
            "-c",
            "import time; time.sleep(5)\n"
        ],
        stdin=stdin_queue,
        protocol=TestProtocol,
        timeout=1,
        protocol_kwargs=dict(timeout_queue=timeout_queue)
    )
    eq_(len(timeout_queue), 3)
