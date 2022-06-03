import random
import threading
import time

from ..coreprotocols import StdOutCapture
from ..nonasyncrunner import ThreadedRunner
from ..protocol import GeneratorMixIn
from .utils import py2cmd
from datalad.tests.utils import (
    assert_in,
    assert_raises,
)


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


def test_thread_reentry_detection():
    # expect that two run calls on the same runner with a generator-protocol
    # and an active generator create a runtime error

    # make in-thread exceptions visible to test thread
    def new_hook(*args):
        exceptions.append(args[0].exc_type)

    threading.excepthook = new_hook

    exceptions = []

    shared_runner = ThreadedRunner(
        cmd=py2cmd("for i in range(5): print(i)"),
        protocol_class=MinimalGeneratorProtocol,
        stdin=None)

    thread_1 = threading.Thread(target=shared_runner.run)
    thread_2 = threading.Thread(target=shared_runner.run)

    thread_1.start()
    thread_2.start()

    thread_1.join()
    thread_2.join()

    assert_in(RuntimeError, exceptions)


def test_thread_serialization():
    def run_on(runner: ThreadedRunner):
        for _ in runner.run():
            time.sleep(random.random())

    # make in-thread exceptions visible to test thread
    def new_hook(*args):
        exceptions.append(args[0].exc_type)

    threading.excepthook = new_hook

    exceptions = []

    shared_runner = ThreadedRunner(
        cmd=py2cmd("for i in range(5): print(i)"),
        protocol_class=StdOutCapture,
        stdin=None)

    thread_1 = threading.Thread(target=run_on, args=(shared_runner,))
    thread_2 = threading.Thread(target=run_on, args=(shared_runner,))

    thread_1.start()
    thread_2.start()

    thread_1.join()
    thread_2.join()
    assert exceptions == []


def test_reentry_detection():

    runner = ThreadedRunner(
        cmd=py2cmd("for i in range(5): print(i)"),
        protocol_class=MinimalGeneratorProtocol,
        stdin=None)

    runner.run()
    assert_raises(RuntimeError, runner.run)


def test_leave_handling():

    runner = ThreadedRunner(
        cmd=py2cmd("for i in range(5): print(i)"),
        protocol_class=MinimalStdOutGeneratorProtocol,
        stdin=None)

    iteration_1_result = tuple(runner.run())
    iteration_2_result = tuple(runner.run())

    str1 = "".join(e[1] for e in iteration_1_result)
    str2 = "".join(e[1] for e in iteration_2_result)
    assert str1 == str2


def test_thread_leave_handling():
    # expect no exception on repeated call to run of a runner with
    # generator-protocol, if the generator was exhausted before the second call

    def run_on(runner: ThreadedRunner):
        for _ in runner.run():
            time.sleep(random.random())

    # make in-thread exceptions visible to test thread
    def new_hook(*args):
        exceptions.append(args[0].exc_type)

    threading.excepthook = new_hook

    exceptions = []

    shared_runner = ThreadedRunner(
        cmd=py2cmd("for i in range(5): print(i)"),
        protocol_class=MinimalStdOutGeneratorProtocol,
        stdin=None)

    thread_1 = threading.Thread(target=run_on, args=(shared_runner,))
    thread_2 = threading.Thread(target=run_on, args=(shared_runner,))

    thread_1.start()
    thread_1.join()

    thread_2.start()
    thread_2.join()

    assert exceptions == []
