import random
import sys
import threading
import time

import pytest

from datalad.runner.coreprotocols import StdOutCapture
from datalad.runner.nonasyncrunner import ThreadedRunner
from datalad.runner.protocol import GeneratorMixIn
from datalad.runner.tests.utils import py2cmd


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
        protocol_class=MinimalGeneratorProtocol,
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

    assert exceptions == [RuntimeError]


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
    assert iteration_1_result == iteration_2_result


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
