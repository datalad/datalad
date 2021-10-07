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
import subprocess
import sys
import tempfile
import warnings

# start of legacy import block
# to avoid breakage of code written before datalad.runner
from datalad.runner.coreprotocols import (
    KillOutput,
    NoCapture,
    StdErrCapture,
    StdOutCapture,
    StdOutErrCapture,
)
from datalad.runner.gitrunner import (
    GIT_SSH_COMMAND,
    GitRunnerBase,
    GitWitlessRunner,
)
from datalad.runner.runner import WitlessRunner
from datalad.runner.protocol import WitlessProtocol
from datalad.runner.nonasyncrunner import run_command
from datalad.support.exceptions import CommandError
# end of legacy import block

from datalad.utils import (
    auto_repr,
    ensure_unicode,
    try_multiple,
    unlink,
)

lgr = logging.getLogger('datalad.cmd')

# TODO unused?
# In python3 to split byte stream on newline, it must be bytes
linesep_bytes = os.linesep.encode()

# TODO unused?
_TEMP_std = sys.stdout, sys.stderr

# TODO unused?
# To be used in the temp file name to distinguish the ones we create
# in Runner so we take care about their removal, in contrast to those
# which might be created outside and passed into Runner
_MAGICAL_OUTPUT_MARKER = "_runneroutput_"


def readline_rstripped(stdout):
    warnings.warn("the function `readline_rstripped()` is deprecated "
                  "and will be removed in a future release",
                  DeprecationWarning)
    return _readline_rstripped(stdout)


def _readline_rstripped(stdout):
    """Internal helper for BatchedCommand"""
    return stdout.readline().rstrip()


class SafeDelCloseMixin(object):
    """A helper class to use where __del__ would call .close() which might
    fail if "too late in GC game"
    """
    def __del__(self):
        try:
            self.close()
        except TypeError:
            if os.fdopen is None or lgr.debug is None:
                # if we are late in the game and things already gc'ed in py3,
                # it is Ok
                return
            raise


@auto_repr
class BatchedCommand(SafeDelCloseMixin):
    """Container for a process which would allow for persistent communication
    """

    def __init__(self, cmd, path=None, output_proc=None):
        if not isinstance(cmd, list):
            cmd = [cmd]
        self.cmd = cmd
        self.path = path
        self.output_proc = output_proc if output_proc else _readline_rstripped
        self._process = None
        self._stderr_out = None
        self._stderr_out_fname = None

    def _initialize(self):
        lgr.debug("Initiating a new process for %s", repr(self))
        lgr.log(5, "Command: %s", self.cmd)
        # according to the internet wisdom there is no easy way with subprocess
        # while avoid deadlocks etc.  We would need to start a thread/subprocess
        # to timeout etc
        # kwargs = dict(bufsize=1, universal_newlines=True) if PY3 else {}
        self._stderr_out, self._stderr_out_fname = tempfile.mkstemp()
        self._process = subprocess.Popen(
            self.cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_out,
            env=GitRunnerBase.get_git_environ_adjusted(),
            cwd=self.path,
            bufsize=1,
            universal_newlines=True  # **kwargs
        )

    def _check_process(self, restart=False):
        """Check if the process was terminated and restart if restart

        Returns
        -------
        bool
          True if process was alive.
        str
          stderr if any recorded if was terminated
        """
        process = self._process
        ret = True
        ret_stderr = None
        if process and process.poll():
            lgr.warning("Process %s was terminated with returncode %s" % (process, process.returncode))
            ret_stderr = self.close(return_stderr=True)
            ret = False
        if self._process is None and restart:
            lgr.warning("Restarting the process due to previous failure")
            self._initialize()
        return ret, ret_stderr

    def __call__(self, cmds):
        """

        Parameters
        ----------
        cmds : str or tuple or list of (str or tuple)

        Returns
        -------
        str or list
          Output received from process.  list in case if cmds was a list
        """
        input_multiple = isinstance(cmds, list)
        if not input_multiple:
            cmds = [cmds]

        output = [o for o in self.yield_(cmds)]
        return output if input_multiple else output[0]

    def yield_(self, cmds):
        """Same as __call__, but requires `cmds` to be an iterable

        and yields results for each item."""
        for entry in cmds:
            if not isinstance(entry, str):
                entry = ' '.join(entry)
            yield self.proc1(entry)

    def proc1(self, arg):
        """Same as __call__, but only takes a single command argument

        and returns a single result.
        """
        # TODO: add checks -- may be process died off and needs to be reinitiated
        if not self._process:
            self._initialize()

        entry = arg + '\n'
        lgr.log(5, "Sending %r to batched command %s", entry, self)
        # apparently communicate is just a one time show
        # stdout, stderr = self._process.communicate(entry)
        # according to the internet wisdom there is no easy way with subprocess
        self._check_process(restart=True)
        process = self._process  # _check_process might have restarted it
        process.stdin.write(entry)
        process.stdin.flush()
        lgr.log(5, "Done sending.")
        still_alive, stderr = self._check_process(restart=False)
        # TODO: we might want to handle still_alive, e.g. to allow for
        #       a number of restarts/resends, but it should be per command
        #       since for some we cannot just resend the same query. But if
        #       it is just a "get"er - we could resend it few times
        # The default output_proc expects a single line output.
        # TODO: timeouts etc
        stdout = ensure_unicode(self.output_proc(process.stdout)) \
            if not process.stdout.closed else None
        if stderr:
            lgr.warning("Received output in stderr: %r", stderr)
        lgr.log(5, "Received output: %r", stdout)
        return stdout

    def close(self, return_stderr=False):
        """Close communication and wait for process to terminate

        Returns
        -------
        str
          stderr output if return_stderr and stderr file was there.
          None otherwise
        """
        ret = None
        process = self._process
        if self._stderr_out:
            # close possibly still open fd
            lgr.debug(
                "Closing stderr of %s", process)
            os.fdopen(self._stderr_out).close()
            self._stderr_out = None
        if process:
            lgr.debug(
                "Closing stdin of %s and waiting process to finish", process)
            process.stdin.close()
            process.stdout.close()
            from . import cfg
            cfg_var = 'datalad.runtime.stalled-external'
            cfg_val = cfg.obtain(cfg_var)
            if cfg_val == 'wait':
                process.wait()
            elif cfg_val == 'abandon':
                # try waiting for the annex process to finish 3 times for 3 sec
                # with 1s pause in between
                try:
                    try_multiple(
                        # ntrials
                        3,
                        # exception to catch
                        subprocess.TimeoutExpired,
                        # base waiting period
                        1.0,
                        # function to run
                        process.wait,
                        timeout=3.0,
                    )
                except subprocess.TimeoutExpired:
                    lgr.warning(
                        "Batched process %s did not finish, abandoning it without killing it",
                        process)
            else:
                raise ValueError(f"Unexpected {cfg_var}={cfg_val!r}")
            self._process = None
            lgr.debug("Process %s has finished", process)

        # It is hard to debug when something is going wrong. Hopefully logging stderr
        # if generally asked might be of help
        if lgr.isEnabledFor(5):
            from . import cfg
            log_stderr = cfg.getbool('datalad.log', 'outputs', default=False)
        else:
            log_stderr = False

        if self._stderr_out_fname and os.path.exists(self._stderr_out_fname):
            if return_stderr or log_stderr:
                with open(self._stderr_out_fname, 'r') as f:
                    stderr = f.read()
            if return_stderr:
                ret = stderr
            if log_stderr:
                stderr = ensure_unicode(stderr)
                stderr = stderr.splitlines()
                lgr.log(5, "stderr of %s had %d lines:", process.pid, len(stderr))
                for l in stderr:
                    lgr.log(5, "| " + l)

            # remove the file where we kept dumping stderr
            unlink(self._stderr_out_fname)
            self._stderr_out_fname = None
        return ret
