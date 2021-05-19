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
import subprocess
from time import sleep, time

from datalad.tests.utils import assert_true, eq_, with_tempfile

from ..cmd import WitlessProtocol, WitlessRunner, StdOutCapture
from ..nonasyncrunner import ReaderThread, run_command


def test_subprocess_return_code_capture():

    class KillProtocol(WitlessProtocol):

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

    signal_to_send = 13
    result_pool = dict()
    result = run_command(["sleep", "10000"],
                         KillProtocol,
                         None,
                         {
                             "signal_to_send": signal_to_send,
                             "result_pool": result_pool
                         })
    eq_(result["code"], -signal_to_send)
    assert_true(result_pool["connection_lost_called"][0])
    assert_true(result_pool["process_exited_called"])


def test_interactive_communication():

    class BidirectionalProtocol(WitlessProtocol):

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
    result = run_command(["python3", "-i"],
                         BidirectionalProtocol,
                         stdin=subprocess.PIPE,
                         protocol_kwargs={
                            "result_pool": result_pool
                         })

    eq_(result["stdout"], "2\n8\n")
    assert_true(result_pool["connection_lost_called"], True)
    assert_true(result_pool["process_exited_called"], True)


def test_thread_exit():

    (read_descriptor, write_descriptor) = os.pipe()
    read_file = os.fdopen(read_descriptor, "r")
    read_queue = queue.Queue()

    reader_thread = ReaderThread(read_file, read_queue, "test")
    reader_thread.start()

    os.write(write_descriptor, b"some data")
    assert_true(reader_thread.is_alive())
    data = read_queue.get()
    eq_(data[1], b"some data")

    reader_thread.request_exit()

    os.write(write_descriptor, b"more data")
    reader_thread.join()
    data = read_queue.get()
    eq_(data[1], b"more data")
    assert_true(read_queue.empty())


def test_inside_async():
    async def main():
        runner = WitlessRunner()
        return runner.run(["echo", "abc"], StdOutCapture)

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(main())
    eq_(result["stdout"], "abc\n")


@with_tempfile(mkdir=True)
@with_tempfile
def test_popen_invocation(src_path, dest_path):
    # https://github.com/ReproNim/testkraken/issues/93
    from datalad.distribution.dataset import Dataset
    from datalad.api import clone
    from multiprocessing import Process
    src = Dataset(src_path).create()
    (src.pathobj / "file.dat").write_bytes(b"\000")
    src.save(message="got data")
    dest = clone(source=src_path, path=dest_path)
    fetching_data = Process(target=dest.get, kwargs={"path": 'file.dat'})
    fetching_data.start()
    t0 = time()
    while fetching_data.is_alive():
        if time() - t0 > 5:
            raise AssertionError("Child is stuck!")
        sleep(0.1)
