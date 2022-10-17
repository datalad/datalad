# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
Class the starts a subprocess and keeps it around to communicate with it
via stdin. For each instruction send over stdin, a response is read and
returned. The response structure is determined by "output_proc"

"""
from __future__ import annotations

import logging
import os
import queue
import sys
import warnings
from queue import Queue
from subprocess import TimeoutExpired
from typing import (
    Any,
    Callable,
    List,
    Optional,
    Tuple,
    Union,
)
from datetime import datetime
from operator import attrgetter
from weakref import WeakValueDictionary, ReferenceType, ref

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
from datalad.runner.nonasyncrunner import run_command
from datalad.runner.protocol import WitlessProtocol
from datalad.runner.runner import WitlessRunner
from datalad.support.exceptions import CommandError
# end of legacy import block

from datalad.runner.coreprotocols import StdOutErrCapture
from datalad.runner.nonasyncrunner import (
    STDERR_FILENO,
    STDOUT_FILENO,
    _ResultGenerator,
)
from datalad.runner.protocol import GeneratorMixIn
from datalad.runner.runner import WitlessRunner
from datalad.runner.utils import LineSplitter
from datalad.utils import (
    auto_repr,
    ensure_unicode,
)


__docformat__ = "restructuredtext"


class BatchedCommandError(CommandError):
    def __init__(self,
                 cmd="",
                 last_processed_request="",
                 msg="",
                 code=None,
                 stdout="",
                 stderr="",
                 cwd=None,
                 **kwargs):
        """
        This exception extends a CommandError that is raised by the command,
        that is executed by `BatchedCommand`. It extends the `CommandError` by
        `last_processed_request`. This attribute contains the last request, i.e.
        argument to `BatchedCommand.__call__()`, that was successfully
        processed, i.e. for which a result was received from the command (that
        does not imply that the result was positive).

        :param last_processed_request: the last request for which a response was
            received from the underlying command. This could be used to restart
            an interrupted process.

        For all other arguments see `CommandError`.
        """
        CommandError.__init__(
            self,
            cmd=cmd,
            msg=msg,
            code=code,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
            **kwargs
        )
        self.last_processed_request = last_processed_request


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


class BatchedCommandProtocol(GeneratorMixIn, StdOutErrCapture):
    def __init__(self,
                 batched_command: "BatchedCommand",
                 done_future: Any = None,
                 encoding: Optional[str] = None,
                 output_proc: Callable = None,
                 ):
        GeneratorMixIn.__init__(self)
        StdOutErrCapture.__init__(self, done_future, encoding)
        self.batched_command = batched_command
        self.output_proc = output_proc
        self.line_splitter = LineSplitter()

    def pipe_data_received(self, fd: int, data: bytes):
        if fd == STDERR_FILENO:
            self.send_result((fd, data))
        elif fd == STDOUT_FILENO:
            for line in self.line_splitter.process(data.decode(self.encoding)):
                self.send_result((fd, line))
        else:
            raise ValueError(f"unknown file descriptor: {fd}")

    def pipe_connection_lost(self, fd: int, exc: Optional[Exception]):
        if fd == STDOUT_FILENO:
            remaining_line = self.line_splitter.finish_processing()
            if remaining_line is not None:
                lgr.debug("unterminated line: %s", remaining_line)
                self.send_result((fd, remaining_line))

    def timeout(self, fd: Optional[int]) -> bool:
        timeout_error = self.batched_command.get_timeout_exception(fd)
        if timeout_error:
            raise timeout_error
        self.send_result(("timeout", fd))
        return False


class ReadlineEmulator:
    """
    This class implements readline() on the basis of an instance of
    BatchedCommand. Its purpose is to emulate stdout's for output_procs,
    This allows us to provide a BatchedCommand API that is identical
    to the old version, but with an implementation that is based on the
    threaded runner.
    """
    def __init__(self,
                 batched_command: "BatchedCommand"):
        self.batched_command = batched_command

    def readline(self):
        """
        Read from the stdout provider until we have a line or None (which
        indicates some error).
        """
        return self.batched_command.get_one_line()


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
    """
    Container for a running subprocess. Supports communication with the
    subprocess via stdin and stdout.
    """

    # Collection of active BatchedCommands as a mapping from object IDs to
    # instances
    _active_instances: WeakValueDictionary[int, BatchedCommand] = WeakValueDictionary()

    def __init__(self,
                 cmd: Union[str, Tuple, List],
                 path: Optional[str] = None,
                 output_proc: Callable = None,
                 timeout: Optional[float] = None,
                 exception_on_timeout: bool = False,
                 ):

        command = cmd
        self.command: list = [command] if not isinstance(command, List) else command
        self.path: Optional[str] = path
        self.output_proc: Optional[Callable] = output_proc
        self.timeout: Optional[float] = timeout
        self.exception_on_timeout: bool = exception_on_timeout

        self.stderr_output = b""
        self.runner: Optional[WitlessRunner] = None
        self.encoding = None
        self.wait_timed_out = None
        self.return_code: Optional[int] = None
        self._abandon_cache = None
        self.last_request: Optional[str] = None

        self._active = 0
        self._active_last = _now()
        self.clean_inactive()
        assert id(self) not in self._active_instances
        self._active_instances[id(self)] = self

        # pure declarations
        self.stdin_queue: Queue
        self.generator: _ResultGenerator

    @classmethod
    def clean_inactive(cls):
        from . import cfg
        max_batched = cfg.obtain("datalad.runtime.max-batched")
        max_inactive_age = cfg.obtain("datalad.runtime.max-inactive-age")
        if len(cls._active_instances) > max_batched:
            active_qty = 0
            inactive = []
            for c in cls._active_instances.values():
                if c._active:
                    active_qty += 1
                else:
                    inactive.append(c)
            inactive.sort(key=attrgetter("_active_last"))
            to_close = len(cls._active_instances) - max_batched
            if to_close <= 0:
                return
            too_young = 0
            now = _now()
            for i, c in enumerate(inactive):
                if (now - c._active_last).total_seconds() <= max_inactive_age:
                    too_young = len(inactive) - i
                    break
                elif c._active:
                    active_qty += 1
                else:
                    c.close()
                    cls._active_instances.pop(id(c), None)
                    to_close -= 1
                    if to_close <= 0:
                        break
            if to_close > 0:
                lgr.debug(
                    "Too many BatchedCommands remaining after cleanup;"
                    " %d active, %d went inactive recently",
                    active_qty,
                    too_young,
                )

    def _initialize(self):

        lgr.debug("Starting new runner for %s", repr(self))
        lgr.log(5, "Command: %s", self.command)

        self.stdin_queue = queue.Queue()
        self.stderr_output = b""
        self.wait_timed_out = None
        self.return_code = None
        self.last_request = None

        self.runner = WitlessRunner(
            cwd=self.path,
            env=GitRunnerBase.get_git_environ_adjusted()
        )
        self.generator = self.runner.run(
            cmd=self.command,
            protocol=BatchedCommandProtocol,
            stdin=self.stdin_queue,
            cwd=self.path,
            # This mimics the behavior of the old implementation w.r.t
            # timeouts when waiting for the closing process
            timeout=self.timeout or 11.0,
            # Keyword arguments for the protocol
            batched_command=self,
            output_proc=self.output_proc,
        )
        self.encoding = self.generator.runner.protocol.encoding

        self._active_last = _now()

    def process_running(self) -> bool:
        if self.runner:
            result = self.generator.runner.process.poll()
            if result is None:
                return True
            self.return_code = result
            self.runner = None
            if result != 0:
                raise BatchedCommandError(
                    cmd=" ".join(self.command),
                    last_processed_request=self.last_request,
                    msg=f"{type(self).__name__}: exited with {result} after "
                        f"request: {self.last_request}",
                    code=result
                ) from CommandError
        return False

    def __call__(self,
                 cmds: Union[str, Tuple, List]):
        """
        Send requests to the subprocess and return the responses. We expect one
        response per request. How the response is structured is determined by
        output_proc. If output_proc returns not-None, the responses is
        considered to be a response.

        If output_proc is not provided, we assume that a single response is
        a single line.

        If the subprocess does not exist yet it is started before the first
        command is sent.

        Parameters
        ----------
        cmds : str or tuple or list of (str or tuple)
            request for the subprocess

        Returns
        -------
        str or list
            Responses received from process. Either a string, or a list of
            strings, if cmds was a list.
        """
        self._active += 1
        requests = cmds

        input_multiple = isinstance(requests, list)
        if not input_multiple:
            requests = [requests]

        responses = []
        try:
            # This code assumes that each processing request is
            # a single line and leads to a response that triggers a
            # `send_result` in the protocol.
            for request in requests:
                while True:
                    try:
                        responses.append(self.process_request(request))
                        self.last_request = request
                        break
                    except StopIteration:
                        # The process finished executing, store the last return
                        # code and restart the process.
                        lgr.debug("%s: command exited", self)
                        self.return_code = self.generator.return_code
                        self.runner = None

        except CommandError as command_error:
            # Convert CommandError into BatchedCommandError
            self.runner = None
            self.return_code = command_error.code
            raise BatchedCommandError(
                cmd=command_error.cmd,
                last_processed_request=self.last_request,
                msg=command_error.msg,
                code=command_error.code,
                stdout=command_error.stdout,
                stderr=command_error.stderr,
                cwd=command_error.cwd,
                **command_error.kwargs
            ) from command_error

        finally:
            self._active -= 1
        return responses if input_multiple else responses[0] if responses else None

    def process_request(self,
                        request: Union[Tuple, str]) -> str:

        self._active += 1
        try:

            if not self.process_running():
                self._initialize()

            # Remember request and send it to subprocess
            if not isinstance(request, str):
                request = ' '.join(request)
            self.stdin_queue.put((request + "\n").encode())

            # Get the response from the generator. We only consider
            # data received on stdout as a response.
            if self.output_proc:
                # If we have an output procedure, let the output procedure
                # read stdout and decide about the nature of the response
                response = self.output_proc(ReadlineEmulator(self))
            else:
                # If there is no output procedure we assume that a response
                # is one line.
                response = self.get_one_line()
                if response is not None:
                    response = response.rstrip()
            return response

        finally:
            self._active -= 1

    def proc1(self,
              single_command: str):
        """
        Simulate the old interface. This method is used only once in
        AnnexRepo.get_metadata()
        """
        self._active += 1
        try:
            assert isinstance(single_command, str)
            return self(single_command)
        finally:
            self._active -= 1

    def get_one_line(self) -> Optional[str]:
        """
        Get a single stdout line from the generator.

        If timeout was specified, and exception_on_timeout is False,
        and if a timeout occurs, return None. Otherwise, return the
        string that was read from the generator.
        """

        # Implementation remarks:
        # 1. We know that BatchedCommandProtocol only returns complete lines on
        #    stdout, that makes this code simple.
        # 2. stderr is handled transparently within this method,
        #    by adding all stderr-content to an internal buffer.
        while True:
            source, data = self.generator.send(None)
            if source == STDERR_FILENO:
                self.stderr_output += data
            elif source == STDOUT_FILENO:
                return data
            elif source == "timeout":
                # TODO: we should restart the subprocess on timeout, otherwise
                #  we might end up with results from a previous instruction,
                #  when handling multiple instructions at once. Until this is
                #  done properly, communication timeouts are ignored in order
                #  to avoid errors.
                pass
            else:
                raise ValueError(f"{self}: unknown source: {source}")

    def close(self, return_stderr=False):
        """
        Close communication and wait for process to terminate. If the "timeout"
        parameter to the constructor was not None, and if the configuration
        setting "datalad.runtime.stalled-external" is set to "abandon",
        the method will return latest after "timeout" seconds. If the subprocess
        did not exit within this time, the attribute "wait_timed_out" will
        be set to "True".

        Parameters
        ----------
        return_stderr: bool
          if set to "True", the call will return all collected stderr content
          as string. In addition, if return_stderr is True and the log level
          is 5 or lower, and the configuration setting "datalad.log.outputs"
          evaluates to "True", the content of stderr will be logged.

        Returns
        -------
        str, optional
          stderr output if return_stderr is True, None otherwise
        """

        if self.runner:

            abandon = self._get_abandon()

            # Close stdin to let the process know that we want to end
            # communication. We also close stdout and stderr to inform
            # the generator that we do not care about them anymore. This
            # will trigger process wait timeouts.
            self.generator.runner.close_stdin()

            # Process all remaining messages until the subprocess exits.
            remaining = []
            timeout = False
            try:
                for source, data in self.generator:
                    if source == STDERR_FILENO:
                        self.stderr_output += data
                    elif source == STDOUT_FILENO:
                        remaining.append(data)
                    elif source == "timeout":
                        if data is None and abandon is True:
                            timeout = True
                            break
                    else:
                        raise ValueError(f"{self}: unknown source: {source}")
                self.return_code = self.generator.return_code

            except CommandError as command_error:
                lgr.error("%s subprocess failed with %s", self, command_error)
                self.return_code = command_error.code

            if remaining:
                lgr.debug("%s: remaining content: %s", self, remaining)

            self.wait_timed_out = timeout is True
            if self.wait_timed_out:
                lgr.debug(
                    "%s: timeout while waiting for subprocess to exit", self)
                lgr.warning(
                    "Batched process (%s) "
                    "did not finish, abandoning it without killing it",
                    self.generator.runner.process.pid,
                )

        result = self.get_requested_error_output(return_stderr)
        self.runner = None
        self.stderr_output = b""
        return result

    def get_requested_error_output(self, return_stderr: bool):
        if not self.runner:
            return None

        stderr_content = ensure_unicode(self.stderr_output)
        if lgr.isEnabledFor(5):
            from . import cfg
            if cfg.getbool("datalad.log", "outputs", default=False):
                stderr_lines = stderr_content.splitlines()
                lgr.log(
                    5,
                    "stderr of %s had %d lines:",
                    self.generator.runner.process.pid,
                    len(stderr_lines))
                for line in stderr_lines:
                    lgr.log(5, "| " + line)
        if return_stderr:
            return stderr_content
        return None

    def get_timeout_exception(self,
                              fd: Optional[int]
                              ) -> Optional[TimeoutExpired]:
        """
        Get a process timeout exception if timeout exceptions should
        be generated for a process that continues longer than timeout
        seconds after self.close() was initiated.
        """
        if self.timeout is None \
                or fd is not None \
                or self.exception_on_timeout is False\
                or self._get_abandon() == "wait":
            return None
        return TimeoutExpired(
            cmd=self.command,
            timeout=self.timeout or 11.0,
            stderr=self.stderr_output)

    def _get_abandon(self):
        if self._abandon_cache is None:
            from . import cfg
            cfg_var = "datalad.runtime.stalled-external"
            cfg_val = cfg.obtain(cfg_var)
            if cfg_val not in ("wait", "abandon"):
                raise ValueError(f"Unexpected value: {cfg_var}={cfg_val!r}")
            self._abandon_cache = cfg_val == "abandon"
        return self._abandon_cache


def _now():
    return datetime.now().astimezone()
