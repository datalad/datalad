from __future__ import annotations

import sys
from queue import Queue
from typing import (
    Any,
    Optional,
)

from datalad.runner.coreprotocols import (
    NoCapture,
    StdOutErrCapture,
)
from datalad.runner.nonasyncrunner import (
    _ResultGenerator,
    run_command,
)
from datalad.runner.protocol import GeneratorMixIn
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_raises,
)

from ..exception import CommandError
from ..runner import WitlessRunner
from .utils import py2cmd


class TestProtocol(GeneratorMixIn, StdOutErrCapture):

    __test__ = False  # class is not a class of tests

    def __init__(self,
                 done_future: Any = None,
                 encoding: Optional[str] = None) -> None:

        StdOutErrCapture.__init__(
            self,
            done_future=done_future,
            encoding=encoding)
        GeneratorMixIn.__init__(self)

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        self.send_result((fd, data.decode()))


def test_generator_mixin_basic() -> None:

    stdin_queue: Queue[Optional[bytes]] = Queue()

    i = 0
    for fd, data in run_command([sys.executable, "-i", "-"], TestProtocol, stdin_queue):
        if i > 10:
            stdin_queue.put(b"exit(0)\n")
            stdin_queue.put(None)
        else:
            stdin_queue.put(f"print({i}*{i})\n".encode())
        i += 1


def test_generator_mixin_runner() -> None:

    stdin_queue: Queue[Optional[bytes]] = Queue()

    runner = WitlessRunner()
    i = 0
    for fd, data in runner.run(cmd=[sys.executable, "-i", "-"], protocol=TestProtocol, stdin=stdin_queue):
        if i > 10:
            stdin_queue.put(b"exit(0)\n")
            stdin_queue.put(None)
        else:
            stdin_queue.put(f"print({i}*{i})\n".encode())
        i += 1


def test_post_pipe_callbacks() -> None:
    # Expect that the process_exited and connection_lost callbacks
    # are also called in a GeneratorMixIn protocol
    class TestPostPipeProtocol(GeneratorMixIn, StdOutErrCapture):
        def __init__(self) -> None:
            GeneratorMixIn.__init__(self)
            StdOutErrCapture.__init__(self)

        def process_exited(self) -> None:
            self.send_result(1)
            self.send_result(2)

        def connection_lost(self, exc: Optional[BaseException]) -> None:
            self.send_result(3)
            self.send_result(4)

    runner = WitlessRunner()
    results = list(runner.run(cmd=["echo", "a"], protocol=TestPostPipeProtocol))
    assert_equal(results, [1, 2, 3, 4])


def test_file_number_activity_detection() -> None:
    # Expect an output queue that just has the process exit notification.
    # empty output queue without active threads
    # waits for the process and progresses the generator state
    # to `_ResultGenerator.GeneratorState.process_exited`.
    class TestFNADProtocol(GeneratorMixIn, NoCapture):
        def __init__(self) -> None:
            GeneratorMixIn.__init__(self)
            NoCapture.__init__(self)

        def process_exited(self) -> None:
            self.send_result(3)

        def connection_lost(self, exc: Optional[BaseException]) -> None:
            self.send_result(4)

    wl_runner = WitlessRunner()
    result_generator = wl_runner.run(cmd=["echo", "a"], protocol=TestFNADProtocol)
    assert isinstance(result_generator, _ResultGenerator)

    runner = result_generator.runner
    output_queue = runner.output_queue
    assert len(result_generator.runner.active_file_numbers) == 1
    while runner.should_continue():
        runner.process_queue()

    # Expect process exited and connection lost to be called.
    assert_equal(result_generator.send(None), 3)
    assert_equal(result_generator.send(None), 4)
    assert_raises(StopIteration, result_generator.send, None)


def test_failing_process():
    class TestProtocol(GeneratorMixIn, NoCapture):
        def __init__(self) -> None:
            GeneratorMixIn.__init__(self)
            NoCapture.__init__(self)

    try:
        for _ in run_command(py2cmd("exit(1)"),
                             protocol=TestProtocol,
                             stdin=None):
            pass
        assert_equal(1, 2)
    except CommandError:
        return
    assert_equal(2, 3)
