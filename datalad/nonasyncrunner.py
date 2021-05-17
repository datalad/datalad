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
    def __init__(self, file, q):
        super().__init__(daemon=True)
        self.file = file
        self.queue = q
        self.quit = False

    def __str__(self):
        return f"ReaderThread({self.file}, {self.queue})"

    def request_exit(self):
        """
        Request the thread to exit. This is not guaranteed to
        have any effect, because the thread might be waiting in
        os.read() or queue.put(). We are closing the file that read
        is reading from here, but the queue has to be emptied in
        another thread in order to ensure thread-exiting.
        """
        self.quit = True
        self.file.close()

    def run(self):
        logger.debug(f"ReaderThread({self.file}, {self.queue}) started")
        while not self.quit:
            try:
                data = os.read(self.file.fileno(), 1024)
            except BrokenPipeError as exc:
                logger.debug("%s exiting (broken pipe)", self)
                self.queue.put((self.file.fileno(), exc, time.time()))
                return

            if data == b"":
                logger.debug(f"{self} exiting (stream end)")
                self.queue.put((self.file.fileno(), None, time.time()))
                return

            self.queue.put((self.file.fileno(), data, time.time()))


def run_command(cmd,
                protocol_class,
                stdin,
                protocol_kwargs=None,
                **kwargs) -> Any:

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

    process = subprocess.Popen(cmd, **kwargs)
    process_stdout_fileno = process.stdout.fileno() if catch_stdout else None
    process_stderr_fileno = process.stderr.fileno() if catch_stderr else None
    protocol = protocol_class(**protocol_kwargs)

    # We pass process as transport-argument. It does not have the same
    # semantics as the asyncio-signature, but since it is only used in
    # WitlessProtocol, we can change it there.
    protocol.connection_made(process)

    # Map the pipe file numbers to stdout and stderr file number, because
    # the latter are hardcoded in the protocol code
    # TODO: the fixed file numbers seem to be a side-effect of using
    #  SubprocessProtocol. Some datalad-code relies on this. Shall
    #  we replace hard coded stdout, stderr-file numbers with parameters?

    fileno_mapping = {
        process_stdout_fileno: STDOUT_FILENO,
        process_stderr_fileno: STDERR_FILENO
    }

    if catch_stdout or catch_stderr:

        output_queue = queue.Queue()
        active_file_numbers = set()
        if catch_stderr:
            stderr_reader_thread = ReaderThread(process.stderr, output_queue)
            stderr_reader_thread.start()
            active_file_numbers.add(process.stderr.fileno())
        if catch_stdout:
            stdout_reader_thread = ReaderThread(process.stdout, output_queue)
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
