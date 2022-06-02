import random
import threading
import time
from typing import (
    List,
    Optional,
)

import pytest

from ..coreprotocols import StdOutCapture
from ..nonasyncrunner import ThreadedRunner
from ..protocol import GeneratorMixIn
from ..tests.utils import py2cmd


class MinimalGeneratorProtocol(GeneratorMixIn, StdOutCapture):
    def __init__(self):
        StdOutCapture.__init__(self)
        GeneratorMixIn.__init__(self)


class MinimalStdOutGeneratorProtocol(GeneratorMixIn, StdOutCapture):
    def __init__(self):
        StdOutCapture.__init__(self)
        GeneratorMixIn.__init__(self)

    def pipe_data_received(self, fd, data):
        self.send_result((fd, data.decode()))


def test_thread_reentry_detection():
    def run_on(runner: ThreadedRunner,
               condition: threading.Condition,
               wait_for_condition: bool):

        if wait_for_condition:
            condition.wait()

        for _ in runner.run():
            if not wait_for_condition:
                condition.notify()
            time.sleep(random.random())

    # make exceptions visible to test thread
    def new_hook(*args):
        exceptions.append(args[0].exc_type)

    threading.excepthook = new_hook

    exceptions = []

    shared_runner = ThreadedRunner(
        cmd=py2cmd("for i in range(10): print(i)"),
        protocol_class=MinimalGeneratorProtocol,
        stdin=None)

    enter_condition = threading.Condition()
    thread_1 = threading.Thread(
        name="thread_1",
        target=run_on,
        args=(shared_runner, enter_condition, False))

    thread_2 = threading.Thread(
        name="thread_2",
        target=run_on,
        args=(shared_runner, enter_condition, True))

    thread_1.start()
    thread_2.start()

    thread_1.join()
    thread_2.join()

    assert exceptions == [RuntimeError]


def test_thread_serialization():
    def run_on(runner: ThreadedRunner):
        for _ in runner.run():
            time.sleep(random.random())

    # make exceptions visible to test thread
    def new_hook(*args):
        exceptions.append(args[0].exc_type)

    threading.excepthook = new_hook

    exceptions = []

    shared_runner = ThreadedRunner(
        cmd=py2cmd("for i in range(10): print(i)"),
        protocol_class=StdOutCapture,
        stdin=None)

    thread_1 = threading.Thread(
        name="thread_1",
        target=run_on,
        args=(shared_runner,))

    thread_2 = threading.Thread(
        name="thread_2",
        target=run_on,
        args=(shared_runner,))

    thread_1.start()
    thread_2.start()

    thread_1.join()
    thread_2.join()
    assert exceptions == []


def test_reentry_detection():

    runner = ThreadedRunner(
        cmd=py2cmd("for i in range(10): print(i)"),
        protocol_class=MinimalGeneratorProtocol,
        stdin=None)

    runner.run()
    with pytest.raises(RuntimeError):
        runner.run()


def test_leave_handling():

    runner = ThreadedRunner(
        cmd=py2cmd("for i in range(10): print(i)"),
        protocol_class=MinimalStdOutGeneratorProtocol,
        stdin=None)

    iteration_1_result = tuple(runner.run())
    iteration_2_result = tuple(runner.run())

    str1 = "".join(e[1] for e in iteration_1_result)
    str2 = "".join(e[1] for e in iteration_2_result)
    assert str1 == str2


def test_thread_leave_handling():
    def run_on(runner: ThreadedRunner):
        for _ in runner.run():
            time.sleep(random.random())

    # make exceptions visible to test thread
    def new_hook(*args):
        exceptions.append(args[0].exc_type)

    threading.excepthook = new_hook

    exceptions = []

    shared_runner = ThreadedRunner(
        cmd=py2cmd("for i in range(10): print(i)"),
        protocol_class=MinimalStdOutGeneratorProtocol,
        stdin=None)

    thread_1 = threading.Thread(
        name="thread_1",
        target=run_on,
        args=(shared_runner,))

    thread_2 = threading.Thread(
        name="thread_2",
        target=run_on,
        args=(shared_runner,))

    thread_1.start()
    thread_1.join()

    thread_2.start()
    thread_2.join()

    assert exceptions == []
