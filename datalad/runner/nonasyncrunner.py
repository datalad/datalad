# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
Thread based subprocess execution with stdout and stderr passed to protocol objects
"""

import enum
import logging
import subprocess
from collections import deque
from collections.abc import Generator
from queue import (
    Empty,
    Queue,
)
from typing import (
    Any,
    Dict,
    IO,
    List,
    Optional,
    Type,
    Union,
)

from datalad.runner.protocol import (
    GeneratorMixIn,
    WitlessProtocol,
)

from .runnerthreads import (
    BlockingOSReaderThread,
    BlockingOSWriterThread,
    IOState,
    ReadThread,
    WriteThread,
)


lgr = logging.getLogger("datalad.runner.nonasyncrunner")

STDIN_FILENO = 0
STDOUT_FILENO = 1
STDERR_FILENO = 2


class _ResultGenerator(Generator):

    class GeneratorState(enum.Enum):
        process_running = 0
        process_exited = 1
        connection_lost = 2

    def __init__(self,
                 runner: "ThreadedRunner",
                 result_queue: deque
                 ):

        super().__init__()
        self.runner = runner
        self.result_queue = result_queue
        self.return_code = None
        self.state = self.GeneratorState.process_running

    def send(self, _):
        if self.state == self.GeneratorState.process_running:

            # if the result queue is empty and no more reading/writing
            # threads are active, progress to next state
            if len(self.result_queue) == 0 and not self.runner.active_file_numbers:
                self.runner.process.wait()
                self.return_code = self.runner.process.poll()
                self.runner.protocol.process_exited()
                self.state = self.GeneratorState.process_exited
            else:
                # If we have no results in the queue, but still active
                # reading/writing threads, wait on the threaded runner queue
                while len(self.result_queue) == 0 and self.runner.active_file_numbers:
                    self.runner.process_queue()
                if len(self.result_queue) > 0:
                    return self.result_queue.popleft()
                else:
                    while True:
                        try:
                            self.runner.process.wait(timeout=self.runner.timeout)
                            break
                        except subprocess.TimeoutExpired:
                            self.runner.protocol.timeout(None)

                    self.return_code = self.runner.process.poll()
                    self.runner.protocol.process_exited()
                    self.state = self.GeneratorState.process_exited

        if self.state == self.GeneratorState.process_exited:
            if len(self.result_queue) > 0:
                return self.result_queue.popleft()
            else:
                # TODO: check exception
                self.runner.protocol.connection_lost(None)
                self.state = self.GeneratorState.connection_lost

        if self.state == self.GeneratorState.connection_lost:
            if len(self.result_queue) > 0:
                return self.result_queue.popleft()
            raise StopIteration(self.return_code)

    def throw(self, exception_type, value=None, trace_back=None):
        return Generator.throw(self, exception_type, value, trace_back)


class ThreadedRunner:
    def __init__(self,
                 cmd: Union[str, List],
                 protocol_class: Type[WitlessProtocol],
                 stdin: Any,
                 protocol_kwargs: Optional[Dict] = None,
                 timeout: Optional[float] = None,
                 **popen_kwargs
                 ):
        self.cmd = cmd
        self.protocol_class = protocol_class
        self.stdin = stdin
        self.protocol_kwargs = protocol_kwargs or {}
        self.timeout = timeout
        self.popen_kwargs = popen_kwargs
        self.catch_stdout = self.protocol_class.proc_out is not None
        self.catch_stderr = self.protocol_class.proc_err is not None
        self.generator = self.protocol_class.generator is not None

        self.write_stdin = False
        self.stdin_queue = None
        self.protocol = None
        self.process = None
        self.process_stdin_fileno = None
        self.process_stdout_fileno = None
        self.process_stderr_fileno = None
        self.fileno_mapping = None
        self.output_queue = None
        self.active_file_numbers = None

    def run(self):
        """
        Run a command in a subprocess

        This is a naive implementation that uses sub`process.Popen`
        and threads to read from sub-proccess' stdout and stderr and
        put it into a queue from which the main-thread reads.
        Upon receiving data from the queue, the main thread
        will delegate data handling to a protocol_class instance

        Parameters
        ----------
        cmd : list or str
            Command to be executed, passed to `subprocess.Popen`. If cmd
            is a str, `subprocess.Popen will be called with `shell=True`.
        protocol : WitlessProtocol class or subclass which will be
            instantiated for managing communication with the subprocess.
            If the protocol has the GeneratorMixIn-mixin, the run-method
            will return an iterator and can therefore be used in a for-clause.
        stdin : file-like, string, bytes, Queue, or None
            If stdin is a file-like, it will be directly used as stdin for the
            subprocess. The caller is resonsible for writing to it and closing
            it. If stdin is a string or bytes, those will be fed to stdin of the
            subprocess. If all data is written, stdin will be closed.
            If stdin is a Queue, all elements (bytes) put into the Queue will
            be passed to stdin until None is read from the queue. If None is
            read, stdin of the subprocess is closed.
        protocol_kwargs : dict, optional
            Passed to the Protocol class constructor.
        popen_kwargs : Pass to `subprocess.Popen`, will typically be parameters
            supported by `subprocess.Popen`. Note that `bufsize`, `stdin`,
            `stdout`, `stderr`, and `shell` will be overwritten by
            `run_command`.

        Returns
        -------
        Any
            If the protocol does not have a GeneratorMixIn-mixin, the result
            of protocol._prepare_result will be returned.

        Generator
            If the protocol has a GeneratorMixIn-mixin, a Generator will be
            returned. This allows to use this function in constructs like:

                for protocol_output in runner.run():
                    ...

            Where the iterator yields whatever protocol.pipe_data_received
            sends into the generator.
            If all output was yielded and the process has terminated, the
            generator will raise StopIteration(return_code), where
            return_code is the return code of the process. The return code
            of the process will also be stored in the "return_code"-attribute
            of the runner. So you could write:

               gen = runner.run()
               for file_descriptor, data in gen:
                   ...

               # get the return code of the process
               result = gen.return_code
        """

        if isinstance(self.stdin, (int, IO, type(None))):
            # indicate that we will not write anything to stdin, that
            # means the user can pass None, or he can pass a
            # file-like and write to it from a different thread.
            self.write_stdin = False  # the caller will write to the parameter

        elif isinstance(self.stdin, (str, bytes)):
            # Establish a queue to write to the process and
            # enqueue the input that is already provided.
            self.write_stdin = True
            self.stdin_queue = Queue()
            self.stdin_queue.put(self.stdin)
            self.stdin_queue.put(None)
        elif isinstance(self.stdin, Queue):
            # Establish a queue to write to the process.
            self.write_stdin = True
            self.stdin_queue = self.stdin
        else:
            # indicate that we will not write anything to stdin, that
            # means the user can pass None, or he can pass a
            # file-like and write to it from a different thread.
            lgr.warning(f"unknown instance class: {type(self.stdin)}, "
                        f"assuming file-like input: {self.stdin}")
            # We assume that the caller will write to the given
            # file descriptor.
            self.write_stdin = False

        self.protocol = self.protocol_class(**self.protocol_kwargs)

        kwargs = {
            **self.popen_kwargs,
            **dict(
                bufsize=0,
                stdin=subprocess.PIPE if self.write_stdin else self.stdin,
                stdout=subprocess.PIPE if self.catch_stdout else None,
                stderr=subprocess.PIPE if self.catch_stderr else None,
                shell=True if isinstance(self.cmd, str) else False
            )
        }
        self.process = subprocess.Popen(self.cmd, **kwargs)

        self.process_stdin_fileno = self.process.stdin.fileno() if self.write_stdin else None
        self.process_stdout_fileno = self.process.stdout.fileno() if self.catch_stdout else None
        self.process_stderr_fileno = self.process.stderr.fileno() if self.catch_stderr else None

        # We pass process as transport-argument. It does not have the same
        # semantics as the asyncio-signature, but since it is only used in
        # WitlessProtocol, all necessary changes can be made there.
        self.protocol.connection_made(self.process)

        # Map the pipe file numbers to stdout and stderr file number, because
        # the latter are hardcoded in the protocol code
        self.fileno_mapping = {
            self.process_stdout_fileno: STDOUT_FILENO,
            self.process_stderr_fileno: STDERR_FILENO,
            self.process_stdin_fileno: STDIN_FILENO,
        }

        self.active_file_numbers = set()
        self.output_queue = Queue()

        if self.catch_stdout or self.catch_stderr or self.write_stdin:

            if self.catch_stderr:
                self.active_file_numbers.add(self.process_stderr_fileno)
                self.stderr_reader_thread = BlockingOSReaderThread(self.process.stderr)
                self.stderr_enqueueing_thread = ReadThread(
                    identifier=self.process_stderr_fileno,
                    source_blocking_queue=self.stderr_reader_thread.queue,
                    destination_queue=self.output_queue,
                    signal_queues=[self.output_queue],
                    timeout=self.timeout)
                self.stderr_reader_thread.start()
                self.stderr_enqueueing_thread.start()

            if self.catch_stdout:
                self.active_file_numbers.add(self.process_stdout_fileno)
                self.stdout_reader_thread = BlockingOSReaderThread(self.process.stdout)
                self.stdout_enqueueing_thread = ReadThread(
                    identifier=self.process_stdout_fileno,
                    source_blocking_queue=self.stdout_reader_thread.queue,
                    destination_queue=self.output_queue,
                    signal_queues=[self.output_queue],
                    timeout=self.timeout)
                self.stdout_reader_thread.start()
                self.stdout_enqueueing_thread.start()

            if self.write_stdin:
                self.active_file_numbers.add(self.process_stdin_fileno)
                self.stdin_writer_thread = BlockingOSWriterThread(self.process.stdin)
                self.stdin_enqueueing_thread = WriteThread(
                    identifier=self.process_stdin_fileno,
                    source_queue=self.stdin_queue,
                    destination_blocking_queue=self.stdin_writer_thread.queue,
                    signal_queues=[self.output_queue, self.stdin_writer_thread.queue],
                    timeout=self.timeout)
                self.stdin_writer_thread.start()
                self.stdin_enqueueing_thread.start()

        if issubclass(self.protocol_class, GeneratorMixIn):
            assert isinstance(self.protocol, GeneratorMixIn)
            return _ResultGenerator(self, self.protocol.result_queue)
        else:
            while self.active_file_numbers:
                self.process_queue()

            # The blocking stdin writer thread may not have seen a
            # close signal (which would have been a None-data object in
            # its queue) because it is still waiting to write to
            # the process and has a full queue. This would load to an
            # indefinite wait for the subprocess exit.
            # We close stdin therefore here. This might lead to loss of
            # data, but at some point we have to decide between waiting
            # and giving up.
            # TODO: clean up signaling in blocking writer thread, or allow closing in writer thread
            for fd in (self.process.stdin, self.process.stdout, self.process.stderr):
                if fd is not None:
                    fd.close()

            while True:
                try:
                    self.process.wait(timeout=self.timeout)
                    break
                except subprocess.TimeoutExpired:
                    if self.protocol.timeout(None) is True:
                        break

            result = self.protocol._prepare_result()
            self.protocol.process_exited()
            self.protocol.connection_lost(None)  # TODO: check exception
            for fd in (self.process.stdin, self.process.stdout, self.process.stderr):
                if fd is not None:
                    fd.close()
            return result

    def process_queue(self):
        """
        Get a single event from the queue
        """
        data = None
        while True:
            # We do not need a timeout here. If self.timeout is None,
            # no timeouts are reported anyway. If self.timeout is not
            # None, and any enqueuing (stdin) or dequeuing (stdout,
            # stderr) operation took longer than self.timeout, we should
            # have a queue entry for that.
            file_number, state, data = self.output_queue.get()

            if state == IOState.ok:
                break

            # Handle timeouts
            if state == IOState.timeout:
                # If the timeout handler returns True, remove
                # the file number that caused the timeout from
                # active files and return.
                if self.protocol.timeout(self.fileno_mapping[file_number]):
                    self.active_file_numbers.remove(file_number)
                    return

        # No timeout occurred, we have proper data or stream end marker, i.e. None
        if self.write_stdin and file_number == self.process_stdin_fileno:
            # The only data-signal we expect from stdin thread
            # is None, indicating that the thread ended
            assert data is None
            self.protocol.pipe_connection_lost(
                self.fileno_mapping[self.process_stdin_fileno],
                None)  # TODO: check exception
            self.active_file_numbers.remove(self.process_stdin_fileno)

        elif self.catch_stderr or self.catch_stdout:
            if data is None:
                self.protocol.pipe_connection_lost(
                    self.fileno_mapping[file_number],
                    None)  # TODO: check exception
                self.active_file_numbers.remove(file_number)
                # TODO: fix this
                if file_number == self.process_stdout_fileno:
                    self.process.stdout.close()
                if file_number == self.process_stderr_fileno:
                    self.process.stderr.close()
            else:
                assert isinstance(data, bytes)
                self.protocol.pipe_data_received(self.fileno_mapping[file_number], data)


def run_command(cmd: Union[str, List],
                protocol: Type[WitlessProtocol],
                stdin: Any,
                protocol_kwargs: Optional[Dict] = None,
                timeout: Optional[float] = None,
                **kwargs) -> Any:

    runner = ThreadedRunner(
        cmd=cmd,
        protocol_class=protocol,
        stdin=stdin,
        protocol_kwargs=protocol_kwargs,
        timeout=timeout,
        **kwargs
    )

    return runner.run()
