import sys
from queue import Queue
from typing import Optional

from datalad.runner.nonasyncrunner import run_command
from datalad.runner.protocol import GeneratorMixIn
from datalad.runner.coreprotocols import (
    NoCapture,
    StdOutErrCapture,
)
from datalad.tests.utils import (
    assert_equal,
    assert_raises,
)

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


def test_post_pipe_callbacks():
    # Expect that the process_exited and connection_lost callbacks
    # are also called in a GeneratorMixIn protocol
    class TestPostPipeProtocol(GeneratorMixIn, StdOutErrCapture):
        def __init__(self):
            GeneratorMixIn.__init__(self)
            StdOutErrCapture.__init__(self)

        def process_exited(self):
            self.send_result(1)
            self.send_result(2)

        def connection_lost(self, exc: Optional[Exception]) -> None:
            self.send_result(3)
            self.send_result(4)

    runner = WitlessRunner()
    results = list(runner.run(cmd=["echo", "a"], protocol=TestPostPipeProtocol))
    assert_equal(results, [1, 2, 3, 4])


def test_file_number_activity_detection():
    # Expect that an empty output queue without active threads
    # waits for the process and progresses the generator state
    # to `_ResultGenerator.GeneratorState.process_exited`.
    class TestFNADProtocol(GeneratorMixIn, NoCapture):
        def __init__(self):
            GeneratorMixIn.__init__(self)
            NoCapture.__init__(self)

        def pipe_data_received(self, fd, data):
            self.send_result(1)

        def pipe_connection_lost(self, fd: int, exc: Optional[Exception]) -> None:
            self.send_result(2)

        def process_exited(self):
            self.send_result(3)

        def connection_lost(self, exc: Optional[Exception]) -> None:
            self.send_result(4)

    runner = WitlessRunner()
    result_generator = runner.run(cmd=["echo", "a"], protocol=TestFNADProtocol)
    output_queue = result_generator.runner.output_queue
    assert len(result_generator.runner.active_file_numbers) == 0
    while not output_queue.empty():
        output_queue.get()

    # Expect process exited and connection lost to be called.
    assert_equal(result_generator.send(None), 3)
    assert_equal(result_generator.send(None), 4)
    assert_raises(StopIteration, result_generator.send, None)


def test_exiting_process():

    result = run_command([sys.executable, "-c", "import time\ntime.sleep(3)\nprint('exit')"], protocol=NoCapture, stdin=None)
    print(result)


def generator_mixin_interactive_demo():

    stdin_queue = Queue()
    for fd, data in run_command([sys.executable, "-i", "-v"], TestProtocol, stdin_queue):
        if fd == 1:
            sys.stdout.write(f"{data}\n")
        else:
            sys.stderr.write(data)
            if data == ">>> ":
                stdin_queue.put((input() + "\n").encode())
