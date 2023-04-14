# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base class of a protocol to be used with the DataLad runner
"""

from __future__ import annotations

import logging
import subprocess
import warnings
from collections import deque
from locale import getpreferredencoding
from typing import (
    Any,
    Optional,
)

from datalad.utils import ensure_unicode

from .exception import CommandError

lgr = logging.getLogger('datalad.runner.protocol')


class GeneratorMixIn:
    """ Protocol mix in that will instruct runner.run to return a generator

    When this class is in the parent of a protocol given to runner.run (and
    some other functions/methods) the run-method will return a `Generator`,
    which yields whatever the protocol callbacks send to the `Generator`,
    via the `send_result`-method of this class.

    This allows to use runner.run() in constructs like:

        for result in runner.run(...):
            # do something, for example write to stdin of the subprocess

    """
    def __init__(self):
        self.result_queue = deque()

    def send_result(self, result):
        self.result_queue.append(result)


class WitlessProtocol:
    """Subprocess communication protocol base class for `run_async_cmd`

    This class implements basic subprocess output handling. Derived classes
    like `StdOutCapture` should be used for subprocess communication that need
    to capture and return output. In particular, the `pipe_data_received()`
    method can be overwritten to implement "online" processing of process
    output.

    This class defines a default return value setup that causes
    `run_async_cmd()` to return a 2-tuple with the subprocess's exit code
    and a list with bytestrings of all captured output streams.
    """

    proc_out = False
    proc_err = False

    def __init__(self, done_future: Any = None, encoding: Optional[str] = None) -> None:
        """
        Parameters
        ----------
        done_future: Any
          Ignored parameter, kept for backward compatibility (DEPRECATED)
        encoding : str
          Encoding to be used for process output bytes decoding. By default,
          the preferred system encoding is guessed.
        """

        if done_future is not None:
            warnings.warn("`done_future` argument is ignored "
                          "and will be removed in a future release",
                          DeprecationWarning)

        self.fd_infos: dict[int, tuple[str, Optional[bytearray]]] = {}

        self.process: Optional[subprocess.Popen] = None
        self.stdout_fileno = 1
        self.stderr_fileno = 2

        # capture output in bytearrays while the process is running
        self.fd_infos[self.stdout_fileno] = ("stdout", bytearray()) if self.proc_out else ("stdout", None)
        self.fd_infos[self.stderr_fileno] = ("stderr", bytearray()) if self.proc_err else ("stderr", None)

        super().__init__()
        self.encoding = encoding or getpreferredencoding(do_setlocale=False)

        self._log_outputs = False
        if lgr.isEnabledFor(5):
            try:
                from datalad import cfg
                self._log_outputs = cfg.getbool('datalad.log', 'outputs', default=False)
            except ImportError:
                pass
            self._log = self._log_summary
        else:
            self._log = self._log_nolog

    def _log_nolog(self, fd: int, data: str | bytes) -> None:
        pass

    def _log_summary(self, fd: int, data: str | bytes) -> None:
        fd_name = self.fd_infos[fd][0]
        assert self.process is not None
        lgr.log(5, 'Read %i bytes from %i[%s]%s',
                len(data), self.process.pid, fd_name, ':' if self._log_outputs else '')
        if self._log_outputs:
            log_data = ensure_unicode(data)
            # The way we log is to stay consistent with Runner.
            # TODO: later we might just log in a single entry, without
            # fd_name prefix
            lgr.log(5, "%s| %s ", fd_name, log_data)

    def connection_lost(self, exc: Optional[BaseException]) -> None:
        """Called when the connection is lost or closed.

        The argument is an exception object or None (the latter
        meaning a regular EOF is received or the connection was
        aborted or closed).
        """

    def connection_made(self, process: subprocess.Popen) -> None:
        self.process = process
        lgr.log(8, 'Process %i started', self.process.pid)

    def pipe_connection_lost(self, fd: int, exc: Optional[BaseException]) -> None:
        """Called when a file descriptor associated with the child process is
        closed.

        fd is the int file descriptor that was closed.
        """

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        self._log(fd, data)
        # Store received output if stream was to be captured.
        fd_name, buffer = self.fd_infos[fd]
        if buffer is not None:
            buffer.extend(data)

    def timeout(self, fd: Optional[int]) -> bool:
        """
        Called if the timeout parameter to WitlessRunner.run()
        is not `None` and a process file descriptor could not
        be read (stdout or stderr) or not be written (stdin)
        within the specified time in seconds, or if waiting for
        a subprocess to exit takes longer than the specified time.

        stdin timeouts are only caught when the type of the `stdin`-
        parameter to WitlessRunner.run() is either a `Queue`,
        a `str`, or `bytes`. `Stdout` or `stderr` timeouts
        are only caught of proc_out and proc_err are `True` in the
        protocol class. Process wait timeouts are
        always caught if `timeout` is not `None`. In this case the
        `fd`-argument will be `None`.

        fd:
          The file descriptor that timed out or `None` if no
          progress was made at all, i.e. no stdin element was
          enqueued and no output was read from either stdout
          or stderr.

        return:
          If the callback returns `True`, the file descriptor
          (if any was given) will be closed and no longer monitored.
          If the return values is anything else than `True`,
          the file-descriptor will be monitored further
          and additional timeouts might occur indefinitely.
          If `None` was given, i.e. a process runtime-timeout
          was detected, and `True` is returned, the process
          will be terminated.
        """
        return False

    def _prepare_result(self) -> dict:
        """Prepares the final result to be returned to the runner

        Note for derived classes overwriting this method:

        The result must be a dict with keys that do not unintentionally
        conflict with the API of CommandError, as the result dict is passed to
        this exception class as kwargs on error. The Runner will overwrite
        'cmd' and 'cwd' on error, if they are present in the result.
        """
        assert self.process is not None
        return_code = self.process.poll()
        if return_code is None:
            raise CommandError(
                msg=f"Got None as a return_code for the process {self.process.pid}")
        lgr.log(
            8,
            'Process %i exited with return code %i',
            self.process.pid, return_code)
        # give captured process output back to the runner as string(s)
        results: dict[str, Any] = {
            name: (
                bytes(byt).decode(self.encoding)
                if byt is not None
                else '')
            for name, byt in self.fd_infos.values()
        }
        results['code'] = return_code
        return results

    def process_exited(self) -> None:
        pass
