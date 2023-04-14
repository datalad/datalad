from __future__ import annotations

import random
import threading
import time
from threading import Thread

from datalad.tests.utils_pytest import assert_raises

from ..coreprotocols import StdOutCapture
from ..nonasyncrunner import ThreadedRunner
from ..protocol import (
    GeneratorMixIn,
    WitlessProtocol,
)
from .utils import py2cmd


class MinimalGeneratorProtocol(GeneratorMixIn, StdOutCapture):
    def __init__(self) -> None:
        StdOutCapture.__init__(self)
        GeneratorMixIn.__init__(self)


class MinimalStdOutGeneratorProtocol(GeneratorMixIn, StdOutCapture):
    def __init__(self) -> None:
        StdOutCapture.__init__(self)
        GeneratorMixIn.__init__(self)

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        for line in data.decode().splitlines():
            self.send_result((fd, line))


def _runner_with_protocol(protocol: type[WitlessProtocol]) -> ThreadedRunner:
    return ThreadedRunner(
        cmd=py2cmd("for i in range(5): print(i)"),
        protocol_class=protocol,
        stdin=None)


def _run_on(runner: ThreadedRunner,
            iterate: bool,
            exceptions: list[type[BaseException]]
            ):
    try:
        gen = runner.run()
        if iterate:
            for _ in gen:
                time.sleep(random.random())
    except Exception as e:
        exceptions.append(e.__class__)


def _get_run_on_threads(protocol: type[WitlessProtocol],
                        iterate: bool
                        ) -> tuple[Thread, Thread, list]:

    runner = _runner_with_protocol(protocol)

    args: tuple[ThreadedRunner, bool, list] = (runner, iterate, [])
    thread_1 = threading.Thread(target=_run_on, args=args)
    thread_2 = threading.Thread(target=_run_on, args=args)

    return thread_1, thread_2, args[2]


def _reentry_detection_run(protocol: type[WitlessProtocol],
                           iterate: bool
                           ) -> list:

    thread_1, thread_2, exception = _get_run_on_threads(protocol, iterate)

    thread_1.start()
    thread_2.start()

    thread_1.join()
    thread_2.join()
    return exception


def test_thread_serialization() -> None:
    # expect that two run calls on the same runner with a non-generator-protocol
    # do not create a runtime error (executions are serialized though)

    exceptions = _reentry_detection_run(StdOutCapture, True)
    assert exceptions == []


def test_reentry_detection() -> None:
    runner = _runner_with_protocol(MinimalGeneratorProtocol)
    runner.run()
    assert_raises(RuntimeError, runner.run)


def test_leave_handling() -> None:
    runner = _runner_with_protocol(MinimalStdOutGeneratorProtocol)
    all_results = [
        "".join(e[1] for e in runner.run())
        for _ in (0, 1)
    ]

    assert all_results[0] == all_results[1]


def test_thread_leave_handling() -> None:
    # expect no exception on repeated call to run of a runner with
    # generator-protocol, if the generator was exhausted before the second call

    thread_1, thread_2, exception = _get_run_on_threads(
        MinimalStdOutGeneratorProtocol,
        True
    )

    thread_1.start()
    thread_1.join()

    thread_2.start()
    thread_2.join()

    assert exception == []
