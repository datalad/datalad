# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base class of a protocol to be used with the DataLad runner
"""

import asyncio
import logging
import warnings
from locale import getpreferredencoding

from .exception import CommandError
from .utils import ensure_unicode

lgr = logging.getLogger('datalad.runner.protocol')


class WitlessProtocol(asyncio.SubprocessProtocol):
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

    proc_out = None
    proc_err = None

    def __init__(self, done_future=None, encoding=None):
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

        self.fd_infos = {}

        self.process = None
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

    def _log_nolog(self, *args):
        pass

    def _log_summary(self, fd, data):
        fd_name = self.fd_infos[fd][0]
        lgr.log(5, 'Read %i bytes from %i[%s]%s',
                len(data), self.process.pid, fd_name, ':' if self._log_outputs else '')
        if self._log_outputs:
            log_data = ensure_unicode(data)
            # The way we log is to stay consistent with Runner.
            # TODO: later we might just log in a single entry, without
            # fd_name prefix
            lgr.log(5, "%s| %s ", fd_name, log_data)

    def connection_made(self, process):
        self.process = process
        lgr.log(8, 'Process %i started', self.process.pid)

    def pipe_data_received(self, fd, data):
        self._log(fd, data)
        # store received output if stream was to be captured
        fd_name, buffer = self.fd_infos[fd]
        if buffer is not None:
            buffer.extend(data)

    def _prepare_result(self):
        """Prepares the final result to be returned to the runner

        Note for derived classes overwriting this method:

        The result must be a dict with keys that do not unintentionally
        conflict with the API of CommandError, as the result dict is passed to
        this exception class as kwargs on error. The Runner will overwrite
        'cmd' and 'cwd' on error, if they are present in the result.
        """
        return_code = self.process.poll()
        if return_code is None:
            raise CommandError(
                "Got None as a return_code for the process %i",
                self.process.pid)
        lgr.log(
            8,
            'Process %i exited with return code %i',
            self.process.pid, return_code)
        # give captured process output back to the runner as string(s)
        results = {
            name: (
                bytes(byt).decode(self.encoding)
                if byt is not None
                else '')
            for name, byt in self.fd_infos.values()
        }
        results['code'] = return_code
        return results

    def process_exited(self):
        pass
