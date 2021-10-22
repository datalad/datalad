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

import logging
import os
import subprocess
import threading
import time
from queue import Queue
from typing import (
    IO,
    Any,
    Dict,
    List,
    Optional,
    Type,
    Union,
)


lgr = logging.getLogger("datalad.runner.nonasyncrunner")
logging.basicConfig(level=3)

STDIN_FILENO = 0
STDOUT_FILENO = 1
STDERR_FILENO = 2


class _ReaderThread(threading.Thread):

    def __init__(self,
                 file: IO,
                 q: Queue,
                 command: Union[str, List]):
        """
        Parameters
        ----------
        file:
          File object from which the thread will read data
          and write it into the queue. This is usually the
          read end of a pipe.
        q:
          A queue into which the thread writes what it reads
          from file.
        command:
          The command for which the thread was created. This
          is mainly used to improve debug output messages.
        """
        super().__init__(daemon=True)
        self.file = file
        self.queue = q
        self.command = command
        self.quit = False

    def __str__(self):
        return f"ReaderThread({self.queue}, {self.file}, {self.command})"

    def request_exit(self):
        """
        Request the thread to exit. This is not guaranteed to
        have any effect, because the thread might be waiting in
        `os.read()` or on `queue.put()`, if the queue size is finite.
        To ensure thread termination, you can ensure that another thread
        empties the queue, and try to trigger a read on `self.file.fileno()`,
        e.g. by writing into the write-end of a pipe that is connected to
        `self.file.fileno()`.
        """
        self.quit = True

    def run(self):
        lgr.log(5, "%s started", self)

        while not self.quit:
            data = os.read(self.file.fileno(), 1024)
            print(f"READER: {data}")
            if data == b"" or self.quit is True:
                break
            self.queue.put((self.file.fileno(), data, time.time()))

        lgr.log(5, "%s exiting (stream end or quit requested)", self)
        print("READER EXITING")
        self.queue.put((self.file.fileno(), None, time.time()))


class _StdinWriterThread(threading.Thread):
    def __init__(self,
                 file: IO,
                 input_queue: Queue,
                 output_queue: Queue,
                 command: Union[str, List] = ""):
        """
        Parameters
        ----------
        file:
          file-like representing stdin of the subprocess
        input_queue:
          A queue from which data is read and written to the process,
          a None-data object indicates that all stdin_data was written
          and will lead to this thread exiting.
        output_queue:
          A queue to signal the main thread, when we are exiting.
        command:
          The command for which the thread was created. This
          is mainly used to improve debug output messages.
        """
        super().__init__(daemon=True)
        self.file = file
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.command = command
        self.quit = False

    def __str__(self):
        return (
            f"WriterThread({self.file}, {self.input_queue}, "
            f"{self.output_queue}, {self.command})")

    def request_exit(self):
        """
        Request the thread to exit. This is not guaranteed to
        have any effect, because the thread might be waiting in
        `os.write()` or on `queue.get()`, if the queue is empty.
        To ensure thread termination, you can ensure that another thread
        writes None to the queue, and ensure that the sub process is
        actually reading from stdin`.
        """
        self.quit = True

    def _write(self, data):
        try:
            os.write(self.file.fileno(), data.encode())
        except BrokenPipeError:
            lgr.debug(f"{self} broken pipe")

    def run(self):
        lgr.log(5, "%s started", self)

        while not self.quit:
            data = self.input_queue.get()
            print(f"WRITER: {data}")
            if data is None or self.quit is True:
                break
            self._write(data)

        print("WRITER EXITING")
        lgr.log(5, "%s exiting (read completed or interrupted)", self)
        self.output_queue.put((self.file.fileno(), None, time.time()))


def yielding_run_command(cmd: Union[str, List],
                         stdin: Optional[Union[str, bytes, IO, Queue]] = None,
                         catch_stdout: bool = False,
                         catch_stderr: bool = False,
                         **kwargs):
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
    stdin : file-like, subprocess.PIPE, str, bytes, Queue, or None
      Passed to the subprocess as its standard input. In the case of a str
      or bytes objects, the subprocess stdin is set to subprocess.PIPE
      and the given input is written to it after the process has started.
    kwargs : Pass to `subprocess.Popen`, will typically be parameters
       supported by `subprocess.Popen`. Note that `bufsize`, `stdin`,
       `stdout`, `stderr`, and `shell` will be overwritten by
       `run_command`.

    Returns
    -------
    :Returns: int return code of the process
    """

    if isinstance(stdin, (IO, type(None))):
        # indicate that we will not write anything to stdin, that
        # means the user can pass None, or he can pass a
        # file-like and write to it from a different thread.
        write_stdin = False  # the caller will write to the parameter

    elif isinstance(stdin, (str, bytes, Queue)):
        # establish infrastructure to write to the process
        write_stdin = True
        if not isinstance(stdin, Queue):
            # if input is already provided, enqueue it.
            stdin_queue = Queue()
            stdin_queue.put(stdin)
            stdin_queue.put(None)
        else:
            stdin_queue = stdin
    else:
        raise ValueError(f"unsupported stdin type: {stdin}")

    kwargs = {
        **kwargs,
        **dict(
            bufsize=0,
            stdin=subprocess.PIPE if write_stdin else stdin,
            stdout=subprocess.PIPE if catch_stdout else None,
            stderr=subprocess.PIPE if catch_stderr else None,
            shell=True if isinstance(cmd, str) else False
        )
    }

    process = subprocess.Popen(cmd, **kwargs)
    process_stdin_fileno = process.stdin.fileno() if write_stdin else None
    process_stdout_fileno = process.stdout.fileno() if catch_stdout else None
    process_stderr_fileno = process.stderr.fileno() if catch_stderr else None

    # Map the pipe file numbers to stdout and stderr file number, because
    # the latter are hardcoded in the protocol code
    fileno_mapping = {
        process_stdin_fileno: STDIN_FILENO,
        process_stdout_fileno: STDOUT_FILENO,
        process_stderr_fileno: STDERR_FILENO
    }

    if catch_stdout or catch_stderr or write_stdin:

        output_queue = Queue()
        active_file_numbers = set()
        if catch_stderr:
            active_file_numbers.add(process_stderr_fileno)
            stderr_reader_thread = _ReaderThread(process.stderr, output_queue, cmd)
            stderr_reader_thread.start()
        if catch_stdout:
            active_file_numbers.add(process_stdout_fileno)
            stdout_reader_thread = _ReaderThread(process.stdout, output_queue, cmd)
            stdout_reader_thread.start()
        if write_stdin:
            active_file_numbers.add(process_stdin_fileno)
            stdin_writer_thread = _StdinWriterThread(process.stdin,
                                                     stdin_queue,
                                                     output_queue,
                                                     cmd)
            stdin_writer_thread.start()

        process_exited = False
        while not process_exited and active_file_numbers:

            return_value = process.poll()
            if return_value is not None:
                process_exited = True
                print("PROCESS EXITED 1")

            file_number, data, time_stamp = output_queue.get()

            return_value = process.poll()
            if return_value is not None:
                process_exited = True
                print("PROCESS EXITED 2")

            if write_stdin and file_number == process_stdin_fileno:
                # If we receive anything from the writer thread, it should
                # be `None`, indicating that all data was written.
                assert data is None, \
                    f"expected None-data from writer thread, got {data}"
                active_file_numbers.remove(process_stdin_fileno)
            else:
                if data is None:
                    active_file_numbers.remove(file_number)
                else:
                    yield fileno_mapping[file_number], data, time_stamp

            if not active_file_numbers:
                break

    process.wait()

    for fd in (process.stdin, process.stdout, process.stderr):
        if fd is not None:
            fd.close()

    return process.returncode
