import random
import threading
import time
from threading import Thread
from typing import (
    Any,
    List,
    Tuple,
)

from ..coreprotocols import StdOutCapture
from ..nonasyncrunner import ThreadedRunner
from ..protocol import GeneratorMixIn
from .utils import py2cmd
from datalad.tests.utils import assert_raises


class MinimalGeneratorProtocol(GeneratorMixIn, StdOutCapture):
    def __init__(self):
        StdOutCapture.__init__(self)
        GeneratorMixIn.__init__(self)


class MinimalStdOutGeneratorProtocol(GeneratorMixIn, StdOutCapture):
    def __init__(self):
        StdOutCapture.__init__(self)
        GeneratorMixIn.__init__(self)

    def pipe_data_received(self, fd, data):
        for line in data.decode().splitlines():
            self.send_result((fd, line))


def _runner_with_protocol(protocol) -> ThreadedRunner:
    return ThreadedRunner(
        cmd=py2cmd("for i in range(5): print(i)"),
        protocol_class=protocol,
        stdin=None)


def _run_on(runner: ThreadedRunner,
            iterate: bool,
            exceptions: List
            ):
    try:
        gen = runner.run()
        if iterate:
            for _ in gen:
                time.sleep(random.random())
    except Exception as e:
        exceptions.append(e.__class__)


def _get_run_on_threads(protocol: Any,
                        iterate: bool
                        ) -> Tuple[Thread, Thread, List]:

    runner = _runner_with_protocol(protocol)

    args = (runner, iterate, [])
    thread_1 = threading.Thread(target=_run_on, args=args)
    thread_2 = threading.Thread(target=_run_on, args=args)

    return thread_1, thread_2, args[2]


def _reentry_detection_run(protocol: Any,
                           iterate: bool
                           ) -> List:

    thread_1, thread_2, exception = _get_run_on_threads(protocol, iterate)

    thread_1.start()
    thread_2.start()

    thread_1.join()
    thread_2.join()
    return exception


def test_thread_reentry_detection():
    # expect that two run calls on the same runner with a generator-protocol
    # and an active generator create a runtime error

    exceptions = _reentry_detection_run(MinimalGeneratorProtocol, False)
    assert exceptions == [RuntimeError]


def test_thread_serialization():
    # expect that two run calls on the same runner with a non-generator-protocol
    # do not create a runtime error (executions are serialized though)

    exceptions = _reentry_detection_run(StdOutCapture, True)
    assert exceptions == []


def test_reentry_detection():
    runner = _runner_with_protocol(MinimalGeneratorProtocol)
    runner.run()
    assert_raises(RuntimeError, runner.run)


def test_leave_handling():
    runner = _runner_with_protocol(MinimalStdOutGeneratorProtocol)
    all_results = [
        "".join(e[1] for e in runner.run())
        for _ in (0, 1)
    ]

    assert all_results[0] == all_results[1]


def test_thread_leave_handling():
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
