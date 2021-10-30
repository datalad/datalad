import sys
from queue import Queue

from datalad.runner.nonasyncrunner import run_command
from datalad.runner.protocol import GeneratorMixIn
from datalad.runner.coreprotocols import StdOutErrCapture

from ..runner import WitlessRunner


class TestProtocol(GeneratorMixIn, StdOutErrCapture):
    def pipe_data_received(self, fd, data):
        self.send_result((fd, data.decode()))


def test_generator_mixin_basic():

    stdin_queue = Queue()

    i = 0
    for fd, data in run_command([sys.executable, "-i", "-"], TestProtocol, stdin_queue):
        print(f"[{fd}]: {repr(data)}")
        if i > 10:
            stdin_queue.put(b"exit(0)\n")
            stdin_queue.put(None)
        else:
            stdin_queue.put(f"print({i}*{i})\n".encode())
        i += 1


def test_generator_mixin_runner():

    stdin_queue = Queue()

    runner = WitlessRunner()
    i = 0
    for fd, data in runner.run(cmd=[sys.executable, "-i", "-"], protocol=TestProtocol, stdin=stdin_queue):
        print(f"[{fd}]: {repr(data)}")
        if i > 10:
            stdin_queue.put(b"exit(0)\n")
            stdin_queue.put(None)
        else:
            stdin_queue.put(f"print({i}*{i})\n".encode())
        i += 1
