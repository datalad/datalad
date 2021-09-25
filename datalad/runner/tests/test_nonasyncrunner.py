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
    Protocol,
    Runner,
    StdOutCapture,
)
from ..nonasyncrunner import (
    _ReaderThread,
    run_command,
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


def test_thread_exit():

    (read_descriptor, write_descriptor) = os.pipe()
    read_file = os.fdopen(read_descriptor, "rb")
    read_queue = queue.Queue()

    reader_thread = _ReaderThread(read_file, read_queue, "test")
    reader_thread.start()

    os.write(write_descriptor, b"some data")
    assert_true(reader_thread.is_alive())
    data = read_queue.get()
    eq_(data[1], b"some data")

    reader_thread.request_exit()

    # Check the blocking part
    sleep(5)
    assert_true(reader_thread.is_alive())

    # Check actual exit
    os.write(write_descriptor, b"more data")
    reader_thread.join()
    data = read_queue.get()
    eq_(data[1], b"more data")
    assert_true(read_queue.empty())


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
