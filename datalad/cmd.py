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

import time
import subprocess
import sys
import logging
import os
import atexit
import functools
import tempfile
from locale import getpreferredencoding
import asyncio
from collections import (
    defaultdict,
    namedtuple,
    OrderedDict,
)

from .consts import GIT_SSH_COMMAND
from .dochelpers import (
    borrowdoc,
    exc_str,
)
from .support import path as op
from .support.exceptions import CommandError
from .support.protocol import (
    NullProtocol,
    ExecutionTimeProtocol,
    ExecutionTimeExternalsProtocol,
)
from .utils import (
    assure_bytes,
    assure_unicode,
    auto_repr,
    ensure_unicode,
    generate_file_chunks,
    get_tempfile_kwargs,
    split_cmdline,
    unlink,
)

lgr = logging.getLogger('datalad.cmd')

# In python3 to split byte stream on newline, it must be bytes
linesep_bytes = os.linesep.encode()

_TEMP_std = sys.stdout, sys.stderr
# To be used in the temp file name to distinguish the ones we create
# in Runner so we take care about their removal, in contrast to those
# which might be created outside and passed into Runner
_MAGICAL_OUTPUT_MARKER = "_runneroutput_"

from io import IOBase as file_class


def _decide_to_log(v):
    """Hacky workaround for now so we could specify per each which to
    log online and which to the log"""
    if isinstance(v, bool) or callable(v):
        return v
    elif v in {'online'}:
        return True
    elif v in {'offline'}:
        return False
    else:
        raise ValueError("can be bool, callable, 'online' or 'offline'")


def _get_output_stream(log_std, false_value):
    """Helper to prepare output stream for Popen and use file for 'offline'

    Necessary to avoid lockdowns when both stdout and stderr are pipes
    """
    if log_std:
        if log_std == 'offline':
            # we will open a temporary file

            tf = tempfile.mktemp(
                **get_tempfile_kwargs({}, prefix=_MAGICAL_OUTPUT_MARKER)
            )
            return open(tf, 'w')  # XXX PY3 should be 'b' may be?
        else:
            return subprocess.PIPE
    else:
        return false_value


def _cleanup_output(stream, std):
    if isinstance(stream, file_class) and \
        _MAGICAL_OUTPUT_MARKER in getattr(stream, 'name', ''):
        if not stream.closed:
            stream.close()
        if op.exists(stream.name):
            unlink(stream.name)
    elif stream == subprocess.PIPE:
        std.close()


def run_gitcommand_on_file_list_chunks(func, cmd, files, *args, **kwargs):
    """Run a git command multiple times if `files` is too long

    Parameters
    ----------
    func : callable
      Typically a Runner.run variant. Assumed to return a 2-tuple with stdout
      and stderr as strings.
    cmd : list
      Base Git command argument list, to be amended with '--', followed
      by a file list chunk.
    files : list
      List of files.
    args, kwargs :
      Passed to `func`

    Returns
    -------
    str, str
        Concatenated stdout and stderr.
    """
    assert isinstance(cmd, list)
    if not files:
        file_chunks = [[]]
    else:
        file_chunks = generate_file_chunks(files, cmd)

    results = []
    for i, file_chunk in enumerate(file_chunks):
        if file_chunk:
            lgr.debug('Process file list chunk %i (length %i)',
                      i, len(file_chunk))
            results.append(func(cmd + ['--'] + file_chunk, *args, **kwargs))
        else:
            results.append(func(cmd, *args, **kwargs))
    # if it was a WitlessRunner.run -- we would get dicts.
    # If old Runner -- stdout, stderr strings
    if results:
        if isinstance(results[0], dict):
            result = defaultdict(str)
            for r in results:
                for k, v in r.items():
                    if k in ('stdout', 'stderr'):
                        result[k] += v
                    elif k == 'status':
                        if k:
                            # this wrapper expects commands to succeed or exception
                            # being thrown
                            raise RuntimeError(
                                "Running %s with WitlessRunner resulted in "
                                "exit %d but there were no exception" % (cmd, k))
                    elif v:
                        raise RuntimeError(
                            "Have no clue what to do about %s=%r" % (k, v))
            return result['stdout'], result['stderr']
        else:
            return ''.join(r[0] for r in results), \
                   ''.join(r[1] for r in results)


async def run_async_cmd(loop, cmd, protocol, stdin, protocol_kwargs=None,
                        **kwargs):
    """Run a command in a subprocess managed by asyncio

    This implementation has been inspired by
    https://pymotw.com/3/asyncio/subprocesses.html

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
      asyncio event loop instance. Must support subprocesses on the
      target platform.
    cmd : list
      Command to be executed, passed to `subprocess_exec`.
    protocol : WitlessProtocol
      Protocol class to be instantiated for managing communication
      with the subprocess.
    stdin : file-like or None
      Passed to the subprocess as its standard input.
    protocol_kwargs : dict, optional
      Passed to the Protocol class constructor.
    kwargs : Pass to `subprocess_exec`, will typically be parameters
      supported by `subprocess.Popen`.

    Returns
    -------
    undefined
      The nature of the return value is determined by the given
      protocol class.
    """
    lgr.debug('Async run %s', cmd)

    if protocol_kwargs is None:
        protocol_kwargs = {}
    cmd_done = asyncio.Future(loop=loop)
    factory = functools.partial(protocol, cmd_done, **protocol_kwargs)
    proc = loop.subprocess_exec(
        factory,
        *cmd,
        stdin=stdin,
        # ask the protocol which streams to capture
        stdout=asyncio.subprocess.PIPE if protocol.proc_out else None,
        stderr=asyncio.subprocess.PIPE if protocol.proc_err else None,
        **kwargs
    )
    transport = None
    result = None
    try:
        lgr.debug('Launching process %s', cmd)
        transport, protocol = await proc
        lgr.debug('Waiting for process %i to complete', transport.get_pid())
        # The next wait is a workaround that avoids losing the output of
        # quickly exiting commands (https://bugs.python.org/issue41594).
        await asyncio.ensure_future(transport._wait())
        await cmd_done
        result = protocol._prepare_result()
    finally:
        # protect against a crash whe launching the process
        if transport:
            transport.close()

    return result


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

    FD_NAMES = ['stdin', 'stdout', 'stderr']

    proc_out = None
    proc_err = None

    def __init__(self, done_future):
        # future promise to be fulfilled when process exits
        self.done = done_future
        # capture output in bytearrays while the process is running
        Streams = namedtuple('Streams', ['out', 'err'])
        self.buffer = Streams(
            out=bytearray() if self.proc_out else None,
            err=bytearray() if self.proc_err else None,
        )
        self.pid = None
        super().__init__()
        self.encoding = getpreferredencoding(do_setlocale=False)

        self._log_outputs = False
        if lgr.isEnabledFor(5):
            try:
                from . import cfg
                self._log_outputs = cfg.getbool('datalad.log', 'outputs', default=False)
            except ImportError:
                pass
            self._log = self._log_summary
        else:
            self._log = self._log_nolog

    def _log_nolog(self, *args):
        pass

    def _log_summary(self, fd, data):
        fd_name = self.FD_NAMES[fd]
        lgr.log(5, 'Read %i bytes from %i[%s]%s',
                len(data), self.pid, fd_name, ':' if self._log_outputs else '')
        if self._log_outputs:
            log_data = assure_unicode(data)
            # The way we log is to stay consistent with Runner.
            # TODO: later we might just log in a single entry, without
            # fd_name prefix
            lgr.log(5, "%s| %s " % (fd_name, log_data))

    def connection_made(self, transport):
        self.transport = transport
        self.pid = transport.get_pid()
        lgr.debug('Process %i started', self.pid)

    def pipe_data_received(self, fd, data):
        self._log(fd, data)
        # store received output if stream was to be captured
        if self.buffer[fd - 1] is not None:
            self.buffer[fd - 1].extend(data)

    def _prepare_result(self):
        """Prepares the final result to be returned to the runner

        Note for derived classes overwriting this method:

        The result must be a dict with keys that do not unintentionally
        conflict with the API of CommandError, as the result dict is passed to
        this exception class as kwargs on error. The Runner will overwrite
        'cmd' and 'cwd' on error, if they are present in the result.
        """
        return_code = self.transport.get_returncode()
        lgr.debug(
            'Process %i exited with return code %i',
            self.pid, return_code)
        # give captured process output back to the runner as string(s)
        results = {
            name:
            bytes(byt).decode(self.encoding)
            if byt else ''
            for name, byt in zip(self.FD_NAMES[1:], self.buffer)
        }
        results['code'] = return_code
        return results

    def process_exited(self):
        # actually fulfill the future promise and let the execution finish
        self.done.set_result(True)


class NoCapture(WitlessProtocol):
    """WitlessProtocol that captures no subprocess output

    As this is identical with the behavior of the WitlessProtocol base class,
    this class is merely a more readable convenience alias.
    """
    pass


class StdOutCapture(WitlessProtocol):
    """WitlessProtocol that only captures and returns stdout of a subprocess"""
    proc_out = True


class StdErrCapture(WitlessProtocol):
    """WitlessProtocol that only captures and returns stderr of a subprocess"""
    proc_err = True


class StdOutErrCapture(WitlessProtocol):
    """WitlessProtocol that captures and returns stdout/stderr of a subprocess
    """
    proc_out = True
    proc_err = True


class KillOutput(WitlessProtocol):
    """WitlessProtocol that swallows stdout/stderr of a subprocess
    """
    proc_out = True
    proc_err = True

    def pipe_data_received(self, fd, data):
        if lgr.isEnabledFor(5):
            lgr.log(
                5,
                'Discarded %i bytes from %i[%s]',
                len(data), self.pid, self.FD_NAMES[fd])


class WitlessRunner(object):
    """Minimal Runner with support for online command output processing

    It aims to be as simple as possible, providing only essential
    functionality.
    """
    __slots__ = ['cwd', 'env']

    def __init__(self, cwd=None, env=None):
        """
        Parameters
        ----------
        cwd : path-like, optional
          If given, commands are executed with this path as PWD,
          the PWD of the parent process is used otherwise.
        env : dict, optional
          Environment to be used for command execution. If `cwd`
          was given, 'PWD' in the environment is set to its value.
          This must be a complete environment definition, no values
          from the current environment will be inherited.
        """
        self.env = env
        # stringify to support Path instances on PY35
        self.cwd = str(cwd) if cwd is not None else None

    def _get_adjusted_env(self, env=None, cwd=None, copy=True):
        """Return an adjusted copy of an execution environment

        Or return an unaltered copy of the environment, if no adjustments
        need to be made.
        """
        if copy:
            env = env.copy() if env else None
        if cwd and env is not None:
            # if CWD was provided, we must not make it conflict with
            # a potential PWD setting
            env['PWD'] = cwd
        return env

    def run(self, cmd, protocol=None, stdin=None, cwd=None, env=None, **kwargs):
        """Execute a command and communicate with it.

        Parameters
        ----------
        cmd : list
          Sequence of program arguments. Passing a single string means
          that it is simply the name of the program, no complex shell
          commands are supported.
        protocol : WitlessProtocol, optional
          Protocol class handling interaction with the running process
          (e.g. output capture). A number of pre-crafted classes are
          provided (e.g `KillOutput`, `NoCapture`, `GitProgress`).
        stdin : byte stream, optional
          File descriptor like, used as stdin for the process. Passed
          verbatim to subprocess.Popen().
        cwd : path-like, optional
          If given, commands are executed with this path as PWD,
          the PWD of the parent process is used otherwise. Overrides
          any `cwd` given to the constructor.
        env : dict, optional
          Environment to be used for command execution. If `cwd`
          was given, 'PWD' in the environment is set to its value.
          This must be a complete environment definition, no values
          from the current environment will be inherited. Overrides
          any `env` given to the constructor.
        kwargs :
          Passed to the Protocol class constructor.

        Returns
        -------
        dict
          At minimum there will be keys 'stdout', 'stderr' with
          unicode strings of the cumulative standard output and error
          of the process as values.

        Raises
        ------
        CommandError
          On execution failure (non-zero exit code) this exception is
          raised which provides the command (cmd), stdout, stderr,
          exit code (status), and a message identifying the failed
          command, as properties.
        FileNotFoundError
          When a given executable does not exist.
        """
        if protocol is None:
            # by default let all subprocess stream pass through
            protocol = NoCapture

        cwd = cwd or self.cwd
        env = self._get_adjusted_env(
            env or self.env,
            cwd=cwd,
        )

        # start a new event loop, which we will close again further down
        # if this is not done events like this will occur
        #   BlockingIOError: [Errno 11] Resource temporarily unavailable
        #   Exception ignored when trying to write to the signal wakeup fd:
        # It is unclear to me why it happens when reusing an event looped
        # that it stopped from time to time, but starting fresh and doing
        # a full termination seems to address the issue
        if sys.platform == "win32":
            # use special event loop that supports subprocesses on windows
            event_loop = asyncio.ProactorEventLoop()
        else:
            event_loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(event_loop)
        # include the subprocess manager in the asyncio event loop
        results = event_loop.run_until_complete(
            run_async_cmd(
                event_loop,
                cmd,
                protocol,
                stdin,
                protocol_kwargs=kwargs,
                cwd=cwd,
                env=env,
            )
        )
        # terminate the event loop, cannot be undone, hence we start a fresh
        # one each time (see BlockingIOError notes above)
        event_loop.close()

        # log before any exception is raised
        lgr.log(8, "Finished running %r with status %s", cmd, results['code'])

        # make it such that we always blow if a protocol did not report
        # a return code at all
        if results.get('code', True) not in [0, None]:
            # the runner has a better idea, doc string warns Protocol
            # implementations not to return these
            results.pop('cmd', None)
            results.pop('cwd', None)
            raise CommandError(
                # whatever the results were, we carry them forward
                cmd=cmd,
                cwd=self.cwd,
                **results,
            )
        # denoise, must be zero at this point
        results.pop('code', None)
        return results


class Runner(object):
    """Provides a wrapper for calling functions and commands.

    An object of this class provides a methods that calls shell commands or
    python functions, allowing for protocolling the calls and output handling.

    Outputs (stdout and stderr) can be either logged or streamed to system's
    stdout/stderr during execution.
    This can be enabled or disabled for both of them independently.
    Additionally, a protocol object can be a used with the Runner. Such a
    protocol has to implement datalad.support.protocol.ProtocolInterface, is
    able to record calls and allows for dry runs.
    """

    __slots__ = ['commands', 'dry', 'cwd', 'env', 'protocol',
                 '_log_opts']

    def __init__(self, cwd=None, env=None, protocol=None, log_outputs=None):
        """
        Parameters
        ----------
        cwd: string, optional
             Base current working directory for commands.  Could be overridden
             per run call via cwd option
        env: dict, optional
             Custom environment to use for calls. Could be overridden per run
             call via env option
        protocol: ProtocolInterface
             Protocol object to write to.
        log_outputs : bool, optional
             Switch to instruct whether outputs should be logged or not.  If not
             set (default), config 'datalad.log.outputs' would be consulted
        """

        self.cwd = cwd
        self.env = env
        if protocol is None:
            # TODO: config cmd.protocol = null
            protocol_str = os.environ.get('DATALAD_CMD_PROTOCOL', 'null')
            protocol = {
                'externals-time': ExecutionTimeExternalsProtocol,
                'time': ExecutionTimeProtocol,
                'null': NullProtocol
            }[protocol_str]()
            if protocol_str != 'null':
                # we need to dump it into a file at the end
                # TODO: config cmd.protocol_prefix = protocol
                filename = '%s-%s.log' % (
                    os.environ.get('DATALAD_CMD_PROTOCOL_PREFIX', 'protocol'),
                    id(self)
                )
                atexit.register(functools.partial(protocol.write_to_file, filename))

        self.protocol = protocol
        # Various options for logging
        self._log_opts = {}
        # we don't know yet whether we need to log every output or not
        if log_outputs is not None:
            self._log_opts['outputs'] = log_outputs

    def __call__(self, cmd, *args, **kwargs):
        """Convenience method

        This will call run() or call() depending on the kind of `cmd`.
        If `cmd` is a string it is interpreted as the to be executed command.
        Otherwise it is expected to be a callable.
        Any other argument is passed to the respective method.

        Parameters
        ----------
        cmd: str or callable
           command string to be executed via shell or callable to be called.

        `*args`:
        `**kwargs`:
           see Runner.run() and Runner.call() for available arguments.

        Raises
        ------
        TypeError
          if cmd is neither a string nor a callable.
        """

        if isinstance(cmd, str) or isinstance(cmd, list):
            return self.run(cmd, *args, **kwargs)
        elif callable(cmd):
            return self.call(cmd, *args, **kwargs)
        else:
            raise TypeError("Argument 'command' is neither a string, "
                            "nor a list nor a callable.")

    def _opt_env_adapter(v):
        """If value is a string, split by ,"""
        if v:
            if v.isdigit():
                log_env = bool(int(v))
            else:
                log_env = v.split(',')
            return log_env
        else:
            return False

    _LOG_OPTS_ADAPTERS = OrderedDict([
        ('outputs', None),
        ('cwd', None),
        ('env', _opt_env_adapter),
        ('stdin', None),
    ])

    def _get_log_setting(self, opt, default=False):
        try:
            return self._log_opts[opt]
        except KeyError:
            try:
                from . import cfg
            except ImportError:
                return default
            adapter = self._LOG_OPTS_ADAPTERS.get(opt, None)
            self._log_opts[opt] = \
                (cfg.getbool if not adapter else cfg.get_value)(
                    'datalad.log', opt, default=default)
            if adapter:
                self._log_opts[opt] = adapter(self._log_opts[opt])
            return self._log_opts[opt]

    @property
    def log_outputs(self):
        return self._get_log_setting('outputs')

    @property
    def log_cwd(self):
        return self._get_log_setting('cwd')

    @property
    def log_stdin(self):
        return self._get_log_setting('stdin')

    @property
    def log_env(self):
        return self._get_log_setting('env')

    # Two helpers to encapsulate formatting/output
    def _log_out(self, line):
        if line and self.log_outputs:
            self.log("stdout| " + line.rstrip('\n'))

    def _log_err(self, line, expected=False):
        if line and self.log_outputs:
            self.log("stderr| " + line.rstrip('\n'),
                     level={True: 5,
                            False: 11}[expected])

    def _get_output_online(self, proc,
                           log_stdout, log_stderr,
                           outputstream, errstream,
                           expect_stderr=False, expect_fail=False):
        """

        If log_stdout or log_stderr are callables, they will be given a read
        line to be processed, and return processed result.  So if they need to
        'swallow' the line from being logged, should just return None

        Parameters
        ----------
        proc
        log_stdout: bool or callable or 'online' or 'offline'
        log_stderr: : bool or callable or 'online' or 'offline'
          If any of those 'offline', we would call proc.communicate at the
          end to grab possibly outstanding output from it
        expect_stderr
        expect_fail

        Returns
        -------

        """
        stdout, stderr = bytes(), bytes()

        log_stdout_ = _decide_to_log(log_stdout)
        log_stderr_ = _decide_to_log(log_stderr)
        log_stdout_is_callable = callable(log_stdout_)
        log_stderr_is_callable = callable(log_stderr_)

        # arguments to be passed into _process_one_line
        stdout_args = (
                'stdout',
                proc, log_stdout_, log_stdout_is_callable
        )
        stderr_args = (
                'stderr',
                proc, log_stderr_, log_stderr_is_callable,
                expect_stderr or expect_fail
        )

        while proc.poll() is None:
            # see for a possibly useful approach to processing output
            # in another thread http://codereview.stackexchange.com/a/17959
            # current problem is that if there is no output on stderr
            # it stalls
            # Monitor if anything was output and if nothing, sleep a bit
            stdout_, stderr_ = None, None
            if log_stdout_:
                stdout_ = self._process_one_line(*stdout_args)
                stdout += stdout_
            if log_stderr_:
                stderr_ = self._process_one_line(*stderr_args)
                stderr += stderr_
            if stdout_ is None and stderr_ is None:
                # no output was really produced, so sleep a tiny bit
                time.sleep(0.001)

        # Handle possible remaining output
        if log_stdout_ and log_stderr_:
            # If Popen was called with more than two pipes, calling
            # communicate() after we partially read the stream will return
            # empty output.
            stdout += self._process_remaining_output(
                outputstream, proc.stdout.read(), *stdout_args)
            stderr += self._process_remaining_output(
                errstream, proc.stderr.read(), *stderr_args)
        stdout_, stderr_ = proc.communicate()
        # ??? should we condition it on log_stdout in {'offline'} ???
        stdout += self._process_remaining_output(outputstream, stdout_, *stdout_args)
        stderr += self._process_remaining_output(errstream, stderr_, *stderr_args)

        return stdout, stderr

    def _process_remaining_output(self, stream, out_, *pargs):
        """Helper to process output which might have been obtained from popen or
        should be loaded from file"""
        out = bytes()
        if isinstance(stream, file_class) and \
                _MAGICAL_OUTPUT_MARKER in getattr(stream, 'name', ''):
            assert out_ is None, "should have gone into a file"
            if not stream.closed:
                stream.close()
            with open(stream.name, 'rb') as f:
                for line in f:
                    out += self._process_one_line(*pargs, line=line)
        else:
            if out_:
                # resolving a once in a while failing test #2185
                if isinstance(out_, str):
                    out_ = out_.encode('utf-8')
                for line in out_.split(linesep_bytes):
                    out += self._process_one_line(
                        *pargs, line=line, suf=linesep_bytes)
        return out

    def _process_one_line(self, out_type, proc, log_, log_is_callable,
                          expected=False, line=None, suf=None):
        if line is None:
            lgr.log(3, "Reading line from %s", out_type)
            line = {'stdout': proc.stdout, 'stderr': proc.stderr}[out_type].readline()
        else:
            lgr.log(3, "Processing provided line")
        if line and log_is_callable:
            # Let it be processed
            line = log_(assure_unicode(line))
            if line is not None:
                # we are working with binary type here
                line = assure_bytes(line)
        if line:
            if out_type == 'stdout':
                self._log_out(assure_unicode(line))
            elif out_type == 'stderr':
                self._log_err(line.decode('utf-8'),
                              expected)
            else:  # pragma: no cover
                raise RuntimeError("must not get here")
            return (line + suf) if suf else line
        # it was output already directly but for code to work, return ""
        return bytes()

    def run(self, cmd, log_stdout=True, log_stderr=True, log_online=False,
            expect_stderr=False, expect_fail=False,
            cwd=None, env=None, shell=None, stdin=None):
        """Runs the command `cmd` using shell.

        In case of dry-mode `cmd` is just added to `commands` and it is
        actually executed otherwise.
        Allows for separately logging stdout and stderr  or streaming it to
        system's stdout or stderr respectively.

        Note: Using a string as `cmd` and shell=True allows for piping,
              multiple commands, etc., but that implies split_cmdline() is not
              used. This is considered to be a security hazard.
              So be careful with input.

        Parameters
        ----------
        cmd : str, list
          String (or list) defining the command call.  No shell is used if cmd
          is specified as a list

        log_stdout: bool, optional
            If True, stdout is logged. Goes to sys.stdout otherwise.

        log_stderr: bool, optional
            If True, stderr is logged. Goes to sys.stderr otherwise.

        log_online: bool, optional
            Whether to log as output comes in.  Setting to True is preferable
            for running user-invoked actions to provide timely output

        expect_stderr: bool, optional
            Normally, having stderr output is a signal of a problem and thus it
            gets logged at level 11.  But some utilities, e.g. wget, use
            stderr for their progress output.  Whenever such output is expected,
            set it to True and output will be logged at level 5 unless
            exit status is non-0 (in non-online mode only, in online -- would
            log at 5)

        expect_fail: bool, optional
            Normally, if command exits with non-0 status, it is considered an
            error and logged at level 11 (above DEBUG). But if the call intended
            for checking routine, such messages are usually not needed, thus
            it will be logged at level 5.

        cwd : string, optional
            Directory under which run the command (passed to Popen)

        env : string, optional
            Custom environment to pass

        shell: bool, optional
            Run command in a shell.  If not specified, then it runs in a shell
            only if command is specified as a string (not a list)

        stdin: file descriptor
            input stream to connect to stdin of the process.

        Returns
        -------
        (stdout, stderr) - bytes!

        Raises
        ------
        CommandError
           if command's exitcode wasn't 0 or None. exitcode is passed to
           CommandError's `code`-field. Command's stdout and stderr are stored
           in CommandError's `stdout` and `stderr` fields respectively.
        """
        outputstream = _get_output_stream(log_stdout, sys.stdout)
        errstream = _get_output_stream(log_stderr, sys.stderr)

        popen_env = env or self.env
        popen_cwd = cwd or self.cwd

        if popen_cwd and popen_env and 'PWD' in popen_env:
            # we must have inherited PWD, but cwd was provided, so we must
            # adjust it
            popen_env = popen_env.copy()  # to avoid side-effects
            popen_env['PWD'] = popen_cwd

        # TODO: if outputstream is sys.stdout and that one is set to StringIO
        #       we have to "shim" it with something providing fileno().
        # This happens when we do not swallow outputs, while allowing nosetest's
        # StringIO to be provided as stdout, crashing the Popen requiring
        # fileno().  In out swallow_outputs, we just use temporary files
        # to overcome this problem.
        # For now necessary test code should be wrapped into swallow_outputs cm
        # to avoid the problem
        log_msgs = ["Running: %s"]
        log_args = [cmd]
        if self.log_cwd:
            log_msgs += ['cwd=%r']
            log_args += [popen_cwd]
        if self.log_stdin:
            log_msgs += ['stdin=%r']
            log_args += [stdin]
        log_env = self.log_env
        if log_env and popen_env:
            log_msgs += ["env=%r"]
            log_args.append(
                popen_env if log_env is True
                else {k: popen_env[k] for k in log_env if k in popen_env}
            )
        log_msg = '\n'.join(log_msgs)
        self.log(log_msg, *log_args)

        if self.protocol.do_execute_ext_commands:

            if shell is None:
                shell = isinstance(cmd, str)

            if self.protocol.records_ext_commands:
                prot_exc = None
                prot_id = self.protocol.start_section(
                    split_cmdline(cmd)
                    if isinstance(cmd, str)
                    else cmd)
            try:
                proc = subprocess.Popen(cmd,
                                        stdout=outputstream,
                                        stderr=errstream,
                                        shell=shell,
                                        cwd=popen_cwd,
                                        env=popen_env,
                                        stdin=stdin)

            except Exception as e:
                prot_exc = e
                lgr.log(11, "Failed to start %r%r: %s" %
                        (cmd, " under %r" % cwd if cwd else '', exc_str(e)))
                raise

            finally:
                if self.protocol.records_ext_commands:
                    self.protocol.end_section(prot_id, prot_exc)

            try:
                if log_online:
                    out = self._get_output_online(proc,
                                                  log_stdout, log_stderr,
                                                  outputstream, errstream,
                                                  expect_stderr=expect_stderr,
                                                  expect_fail=expect_fail)
                else:
                    out = proc.communicate()

                # Decoding was delayed to this point
                def decode_if_not_None(x):
                    return "" if x is None else bytes.decode(x)
                out = tuple(map(decode_if_not_None, out))

                status = proc.poll()

                # needs to be done after we know status
                if not log_online:
                    self._log_out(out[0])
                    if status not in [0, None]:
                        self._log_err(out[1], expected=expect_fail)
                    else:
                        # as directed
                        self._log_err(out[1], expected=expect_stderr)

                if status not in [0, None]:
                    exc = CommandError(
                        cmd=cmd,
                        code=status,
                        stdout=out[0],
                        stderr=out[1],
                        cwd=popen_cwd,
                    )
                    lgr.log(5 if expect_fail else 11, str(exc))
                    raise exc
                else:
                    self.log("Finished running %r with status %s" % (cmd, status),
                             level=8)

            except CommandError:
                # do not bother with reacting to "regular" CommandError
                # exceptions.  Somehow if we also terminate here for them
                # some processes elsewhere might stall:
                # see https://github.com/datalad/datalad/pull/3794
                raise

            except BaseException as exc:
                exc_info = sys.exc_info()
                # KeyboardInterrupt is subclass of BaseException
                lgr.debug("Terminating process for %s upon exception: %s",
                          cmd, exc_str(exc))
                try:
                    # there are still possible (although unlikely) cases when
                    # we fail to interrupt but we
                    # should not crash if we fail to terminate the process
                    proc.terminate()
                except BaseException as exc2:
                    lgr.warning("Failed to terminate process for %s: %s",
                                cmd, exc_str(exc2))
                raise exc_info[1]

            finally:
                # Those streams are for us to close if we asked for a PIPE
                # TODO -- assure closing the files
                _cleanup_output(outputstream, proc.stdout)
                _cleanup_output(errstream, proc.stderr)

        else:
            if self.protocol.records_ext_commands:
                self.protocol.add_section(split_cmdline(cmd)
                                          if isinstance(cmd, str)
                                          else cmd, None)
            out = ("DRY", "DRY")

        return out

    def call(self, f, *args, **kwargs):
        """Helper to unify collection of logging all "dry" actions.

        Calls `f` if `Runner`-object is not in dry-mode. Adds `f` along with
        its arguments to `commands` otherwise.

        Parameters
        ----------
        f: callable
        """
        if self.protocol.do_execute_callables:
            if self.protocol.records_callables:
                prot_exc = None
                prot_id = self.protocol.start_section(
                    [str(f), "args=%s" % str(args), "kwargs=%s" % str(kwargs)])

            try:
                return f(*args, **kwargs)
            except Exception as e:
                prot_exc = e
                raise
            finally:
                if self.protocol.records_callables:
                    self.protocol.end_section(prot_id, prot_exc)
        else:
            if self.protocol.records_callables:
                self.protocol.add_section(
                    [str(f), "args=%s" % str(args), "kwargs=%s" % str(kwargs)],
                    None)

    def log(self, msg, *args, **kwargs):
        """log helper

        Logs at level 5 by default and adds "Protocol:"-prefix in order to
        log the used protocol.
        """
        level = kwargs.pop('level', 5)
        if isinstance(self.protocol, NullProtocol):
            lgr.log(level, msg, *args, **kwargs)
        else:
            if args:
                msg = msg % args
            lgr.log(level, "{%s} %s" % (
                self.protocol.__class__.__name__, msg)
            )


class GitRunnerBase(object):
    """
    Mix-in class for Runners to be used to run git and git annex commands

    Overloads the runner class to check & update GIT_DIR and
    GIT_WORK_TREE environment variables set to the absolute path
    if is defined and is relative path
    """
    _GIT_PATH = None

    @staticmethod
    def _check_git_path():
        """If using bundled git-annex, we would like to use bundled with it git

        Thus we will store _GIT_PATH a path to git in the same directory as annex
        if found.  If it is empty (but not None), we do nothing
        """
        if GitRunnerBase._GIT_PATH is None:
            from distutils.spawn import find_executable
            # with all the nesting of config and this runner, cannot use our
            # cfg here, so will resort to dark magic of environment options
            if (os.environ.get('DATALAD_USE_DEFAULT_GIT', '0').lower()
                    in ('1', 'on', 'true', 'yes')):
                git_fpath = find_executable("git")
                if git_fpath:
                    GitRunnerBase._GIT_PATH = ''
                    lgr.log(9, "Will use default git %s", git_fpath)
                    return  # we are done - there is a default git avail.
                # if not -- we will look for a bundled one
            GitRunnerBase._GIT_PATH = GitRunnerBase._get_bundled_path()
            lgr.log(9, "Will use git under %r (no adjustments to PATH if empty "
                       "string)", GitRunnerBase._GIT_PATH)
            assert(GitRunnerBase._GIT_PATH is not None)  # we made the decision!

    @staticmethod
    def _get_bundled_path():
        from distutils.spawn import find_executable
        annex_fpath = find_executable("git-annex")
        if not annex_fpath:
            # not sure how to live further anyways! ;)
            alongside = False
        else:
            annex_path = op.dirname(op.realpath(annex_fpath))
            alongside = op.lexists(op.join(annex_path, 'git'))
        return annex_path if alongside else ''

    @staticmethod
    def get_git_environ_adjusted(env=None):
        """
        Replaces GIT_DIR and GIT_WORK_TREE with absolute paths if relative path and defined
        """
        # if env set copy else get os environment
        git_env = env.copy() if env else os.environ.copy()
        if GitRunnerBase._GIT_PATH:
            git_env['PATH'] = op.pathsep.join([GitRunnerBase._GIT_PATH, git_env['PATH']]) \
                if 'PATH' in git_env \
                else GitRunnerBase._GIT_PATH

        for varstring in ['GIT_DIR', 'GIT_WORK_TREE']:
            var = git_env.get(varstring)
            if var:                                    # if env variable set
                if not op.isabs(var):                   # and it's a relative path
                    git_env[varstring] = op.abspath(var)  # to absolute path
                    lgr.log(9, "Updated %s to %s", varstring, git_env[varstring])

        if 'GIT_SSH_COMMAND' not in git_env:
            git_env['GIT_SSH_COMMAND'] = GIT_SSH_COMMAND
            git_env['GIT_SSH_VARIANT'] = 'ssh'

        # We are parsing error messages and hints. For those to work more
        # reliably we are doomed to sacrifice i18n effort of git, and enforce
        # consistent language of the messages
        git_env['LC_MESSAGES'] = 'C'
		# But since LC_ALL takes precedence, over LC_MESSAGES, we cannot
		# "leak" that one inside, and are doomed to pop it
        git_env.pop('LC_ALL', None)

        return git_env


class GitRunner(Runner, GitRunnerBase):
    """A Runner for git and git-annex commands.

    See GitRunnerBase it mixes in for more details
    """

    @borrowdoc(Runner)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._check_git_path()

    def run(self, cmd, env=None, *args, **kwargs):
        out, err = super().run(
            cmd,
            env=self.get_git_environ_adjusted(env),
            *args, **kwargs)
        # All communication here will be returned as unicode
        # TODO: do that instead within the super's run!
        return assure_unicode(out), assure_unicode(err)


class GitWitlessRunner(WitlessRunner, GitRunnerBase):
    """A WitlessRunner for git and git-annex commands.

    See GitRunnerBase it mixes in for more details
    """

    @borrowdoc(WitlessRunner)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._check_git_path()

    def _get_adjusted_env(self, env=None, cwd=None, copy=True):
        env = GitRunnerBase.get_git_environ_adjusted(env=env)
        return super()._get_adjusted_env(
            env=env,
            cwd=cwd,
            # git env above is already a copy, so we have no choice,
            # but we can prevent duplication
            copy=False,
        )


def readline_rstripped(stdout):
    #return iter(stdout.readline, b'').next().rstrip()
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
        self.output_proc = output_proc if output_proc else readline_rstripped
        self._process = None
        self._stderr_out = None
        self._stderr_out_fname = None

    def _initialize(self):
        lgr.debug("Initiating a new process for %s" % repr(self))
        lgr.log(5, "Command: %s" % self.cmd)
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
        lgr.log(5, "Sending %r to batched command %s" % (entry, self))
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
        stdout = assure_unicode(self.output_proc(process.stdout)) \
            if not process.stdout.closed else None
        if stderr:
            lgr.warning("Received output in stderr: %r", stderr)
        lgr.log(5, "Received output: %r" % stdout)
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
            process.wait()
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
