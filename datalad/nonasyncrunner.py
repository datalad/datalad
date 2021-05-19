# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
Wrapper for command and function calls, allowing for dry runs and output handling

"""

import logging
import os
import queue
import subprocess
import threading
import time
from typing import Any


logger = logging.getLogger("datalad.runner")

STDOUT_FILENO = 1
STDERR_FILENO = 2


class ReaderThread(threading.Thread):
    def __init__(self, file, a_queue, command):
        super().__init__(daemon=True)
        self.file = file
        self.queue = a_queue
        self.command = command
        self.quit = False

    def __str__(self):
        return f"ReaderThread({self.file}, {self.queue}, {self.command})"

    def request_exit(self):
        """
        Request the thread to exit. This is not guaranteed to
        have any effect, because the thread might be waiting in
        os.read() or queue.put().
        """
        self.quit = True

    def run(self):
        logger.debug("%s started", self)

        while not self.quit:

            data = os.read(self.file.fileno(), 1024)
            if data == b"":
                logger.debug("%s exiting (stream end)", self)
                self.queue.put((self.file.fileno(), None, time.time()))
                return

            self.queue.put((self.file.fileno(), data, time.time()))


def run_command(cmd,
                protocol_class,
                stdin,
                protocol_kwargs=None,
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
    protocol : WitlessProtocol
      Protocol class to be instantiated for managing communication
      with the subprocess.
    stdin : file-like, subprocess.PIPE or None
      Passed to the subprocess as its standard input.
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

    catch_stdout = protocol_class.proc_out is not None
    catch_stderr = protocol_class.proc_err is not None

    kwargs = {
        **kwargs,
        **dict(
            bufsize=0,
            stdin=stdin,
            stdout=subprocess.PIPE if catch_stdout else None,
            stderr=subprocess.PIPE if catch_stderr else None,
            shell=True if isinstance(cmd, str) else False
        )
    }

    protocol = protocol_class(**protocol_kwargs)

    process = subprocess.Popen(cmd, **kwargs)
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

    if catch_stdout or catch_stderr:

        output_queue = queue.Queue()
        active_file_numbers = set()
        if catch_stderr:
            stderr_reader_thread = ReaderThread(process.stderr, output_queue, cmd)
            stderr_reader_thread.start()
            active_file_numbers.add(process.stderr.fileno())
        if catch_stdout:
            stdout_reader_thread = ReaderThread(process.stdout, output_queue, cmd)
            stdout_reader_thread.start()
            active_file_numbers.add(process.stdout.fileno())

        while True:
            file_number, data, time_stamp = output_queue.get()
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

    return result
