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
import queue
import subprocess
import threading
import time
from typing import (
    IO,
    Any,
    Dict,
    List,
    Optional,
    Type,
    Union,
)

from datalad.utils import on_windows
from .protocol import WitlessProtocol

lgr = logging.getLogger("datalad.runner.nonasyncrunner")

STDIN_FILENO = 0
STDOUT_FILENO = 1
STDERR_FILENO = 2


class _ReaderThread(threading.Thread):

    def __init__(self,
                 file: IO,
                 q: queue.Queue,
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
        return f"ReaderThread({self.file}, {self.queue}, {self.command})"

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
            if data == b"":
                lgr.log(5, "%s exiting (stream end)", self)
                self.queue.put((self.file.fileno(), None, time.time()))
                return

            self.queue.put((self.file.fileno(), data, time.time()))


class _StdinWriterThread(threading.Thread):
    def __init__(self, stdin_data, process, stdin_fileno, q, command=""):
        """
        Parameters
        ----------
        stdin_data:
          Data that should be written to the file given by `stdin_fileno´.
        process:
          a subprocess.Popen-instance. It is mainly used to access
          popen._stdin_write(...)
        q:
          A queue into which the thread writes a None-data object to
          indicate that all stdin_data was written.
        command:
          The command for which the thread was created. This
          is mainly used to improve debug output messages.
        """
        super().__init__(daemon=True)
        self.stdin_data = stdin_data
        self.process = process
        self.stdin_fileno = stdin_fileno
        self.queue = q
        self.command = command

    def __str__(self):
        return (
            f"WriterThread(stdin_data[0 ... {len(self.stdin_data) - 1}], "
            f"{self.process}, {self.stdin_fileno}, {self.command})")

    def run(self):
        lgr.log(5, "%s started", self)

        # (ab)use internal helper that takes care of a bunch of corner cases
        # and closes stdin at the end
        self.process._stdin_write(self.stdin_data)

        lgr.log(5, "%s exiting (write completed or interrupted)", self)
        self.queue.put((self.stdin_fileno, None, time.time()))


def run_command(cmd: Union[str, List],
                protocol: Type[WitlessProtocol],
                stdin: Any,
                protocol_kwargs: Optional[Dict] = None,
                **kwargs) -> Any:
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
    protocol : WitlessProtocol class or subclass
      Protocol class to be instantiated for managing communication
      with the subprocess.
    stdin : file-like, subprocess.PIPE, str, bytes or None
      Passed to the subprocess as its standard input. In the case of a str
      or bytes objects, the subprocess stdin is set to subprocess.PIPE
      and the given input is written to it after the process has started.
    protocol_kwargs : dict, optional
       Passed to the Protocol class constructor.
    kwargs : Pass to `subprocess.Popen`, will typically be parameters
       supported by `subprocess.Popen`. Note that `bufsize`, `stdin`,
       `stdout`, `stderr`, and `shell` will be overwritten by
       `run_command`.

    Returns
    -------
    undefined
      The nature of the return value is determined by the method
      `_prepare_result` of the given protocol class or its superclass.
    """

    protocol_kwargs = {} if protocol_kwargs is None else protocol_kwargs

    catch_stdout = protocol.proc_out is not None
    catch_stderr = protocol.proc_err is not None

    if isinstance(stdin, (str, bytes)):
        # we got something that is not readily usable stdin, but must be
        # fed to the processes stdin
        stdin_data = stdin
    else:
        # indicate that there is nothing to write to stdin
        stdin_data = None

    write_stdin = stdin_data is not None

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

    protocol = protocol(**protocol_kwargs)

    try:
        process = subprocess.Popen(cmd, **kwargs)
    except OSError as e:
        if not on_windows and "argument list too long" in str(e).lower():
            lgr.error(
                "Caught exception suggesting too large stack size limits. "
                "Hint: use 'ulimit -s' command to see current limit and "
                "e.g. 'ulimit -s 8192' to reduce it to avoid this exception. "
                "See https://github.com/datalad/datalad/issues/6106 for more "
                "information."
            )
        raise
    process_stdin_fileno = process.stdin.fileno() if write_stdin else None
    process_stdout_fileno = process.stdout.fileno() if catch_stdout else None
    process_stderr_fileno = process.stderr.fileno() if catch_stderr else None

    # We pass process as transport-argument. It does not have the same
    # semantics as the asyncio-signature, but since it is only used in
    # WitlessProtocol, all necessary changes can be made there.
    protocol.connection_made(process)

    # Map the pipe file numbers to stdout and stderr file number, because
    # the latter are hardcoded in the protocol code
    fileno_mapping = {
        process_stdout_fileno: STDOUT_FILENO,
        process_stderr_fileno: STDERR_FILENO
    }

    if catch_stdout or catch_stderr or write_stdin:

        output_queue = queue.Queue()
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
            stdin_writer_thread = _StdinWriterThread(stdin_data, process, process_stdin_fileno, output_queue, cmd)
            stdin_writer_thread.start()

        while True:

            file_number, data, time_stamp = output_queue.get()
            if write_stdin and file_number == process_stdin_fileno:
                # Input writing is transparent to the main thread,
                # we just check whether the input writer is still running.
                active_file_numbers.remove(process_stdin_fileno)
            else:
                if isinstance(data, bytes):
                    protocol.pipe_data_received(fileno_mapping[file_number], data)
                else:
                    protocol.pipe_connection_lost(fileno_mapping[file_number], data)
                    active_file_numbers.remove(file_number)

            if not active_file_numbers:
                break

    process.wait()
    result = protocol._prepare_result()
    protocol.process_exited()
    protocol.connection_lost(None)  # TODO: check exception
    for fd in (process.stdin, process.stdout, process.stderr):
        if fd is not None:
            fd.close()

    return result
