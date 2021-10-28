import sys
from queue import Queue

from datalad.runner.nonasyncrunner import run_command
from datalad.runner.protocol import GeneratorMixIn
from datalad.runner.coreprotocols import StdOutErrCapture


class TestProtocol(GeneratorMixIn, StdOutErrCapture):
    def pipe_data_received(self, fd, data):
        self.send_result((fd, data.decode()))


def test_generator_mixin_basic():

    stdin_queue = Queue()
    i = 0
    for fd, data in run_command("python3 -i -", TestProtocol, stdin_queue):
        print(f"[{fd}]: {repr(data)}")
        if i > 10:
            stdin_queue.put(b"exit(0)\n")
            stdin_queue.put(None)
        else:
            stdin_queue.put(f"print({i}*{i})\n".encode())
        i += 1
