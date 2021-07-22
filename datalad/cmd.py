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

import subprocess
import sys
import logging
import os
import functools
import tempfile
from locale import getpreferredencoding
import asyncio
from collections import (
    namedtuple,
)

from .consts import GIT_SSH_COMMAND
from .dochelpers import (
    borrowdoc,
    exc_str,
)
from .support import path as op
from .support.exceptions import CommandError
from .utils import (
    auto_repr,
    ensure_unicode,
    generate_file_chunks,
    try_multiple,
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
    cmd : list or str
      Command to be executed, passed to `subprocess_exec` (list), or
      `subprocess_shell` (str).
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
    if protocol_kwargs is None:
        protocol_kwargs = {}
    cmd_done = asyncio.Future(loop=loop)
    factory = functools.partial(protocol, cmd_done, **protocol_kwargs)
    kwargs.update(
        stdin=stdin,
        # ask the protocol which streams to capture
        stdout=asyncio.subprocess.PIPE if protocol.proc_out else None,
        stderr=asyncio.subprocess.PIPE if protocol.proc_err else None,
    )
    if isinstance(cmd, str):
        proc = loop.subprocess_shell(factory, cmd, **kwargs)
    else:
        proc = loop.subprocess_exec(factory, *cmd, **kwargs)
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

    def __init__(self, done_future, encoding=None):
        """
        Parameters
        ----------
        done_future : asyncio.Future
          Future promise to be fulfilled when process exits.
        encoding : str
          Encoding to be used for process output bytes decoding. By default,
          the preferred system encoding is guessed.
        """
        self.done = done_future
        # capture output in bytearrays while the process is running
        Streams = namedtuple('Streams', ['out', 'err'])
        self.buffer = Streams(
            out=bytearray() if self.proc_out else None,
            err=bytearray() if self.proc_err else None,
        )
        self.pid = None
        super().__init__()
        self.encoding = encoding or getpreferredencoding(do_setlocale=False)

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
            log_data = ensure_unicode(data)
            # The way we log is to stay consistent with Runner.
            # TODO: later we might just log in a single entry, without
            # fd_name prefix
            lgr.log(5, "%s| %s ", fd_name, log_data)

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

    # To workaround issues where parent process does not take care about proper
    # new loop instantiation in a child process
    # https://bugs.python.org/issue21998
    _loop_pid = None
    _loop_need_new = None

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
        cmd : list or str
          Sequence of program arguments. Passing a single string causes
          execution via the platform shell.
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

        # rescue any event-loop to be able to reassign after we are done
        # with our own event loop management
        # this is how ipython does it
        try:
            is_new_proc = self._check_if_new_proc()
            event_loop = asyncio.get_event_loop()
            if is_new_proc:
                self._check_if_loop_usable(event_loop, stdin)
            if event_loop.is_closed():
                raise RuntimeError("the loop was closed - use our own")
            new_loop = False
        except RuntimeError:
            event_loop = self._get_new_event_loop()
            new_loop = True
        try:
            lgr.debug('Async run:\n cwd=%s\n cmd=%s', cwd, cmd)
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
        finally:
            if new_loop:
                # be kind to callers and leave asyncio as we found it
                asyncio.set_event_loop(None)
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

    @classmethod
    def _check_if_new_proc(cls):
        """Check if WitlessRunner is used under a new PID

        Note that this is a function that is meant to be called from within a
        particular context only. The RuntimeError is expected to be catched by
        the caller and is meant to be more like a response message than an
        exception.

        Returns
        -------
        bool

        Raises
        ------
        RuntimeError
          If it is not a new proc and we already know that we need a new loop
          in this pid
        """
        pid = os.getpid()
        is_new_proc = cls._loop_pid is None or cls._loop_pid != pid
        if is_new_proc:
            # We need to check if we can run any command smoothly
            cls._loop_pid = pid
            cls._loop_need_new = None
        elif cls._loop_need_new:
            raise RuntimeError("we know we need a new loop")
        return is_new_proc

    @classmethod
    def _check_if_loop_usable(cls, event_loop, stdin):
        """Check if given event_loop could run a simple command

        Sets _loop_need_new variable to a bool depending on what it finds

        Note that this is a function that is meant to be called from within a
        particular context only. The RuntimeError is expected to be catched by
        the caller and is meant to be more like a response message than an
        exception.

        Raises
        ------
        RuntimeError
          If loop is not reusable
        """
        # We need to check if we can run any command smoothly
        try:
            event_loop.run_until_complete(
                run_async_cmd(
                    event_loop,
                    [sys.executable, "--version"],  # fast! 0.004 sec and to be ran once per process
                    KillOutput,
                    stdin,
                )
            )
            cls._loop_need_new = False
        except OSError as e:
            # due to https://bugs.python.org/issue21998
            # exhibits in https://github.com/ReproNim/testkraken/issues/95
            lgr.debug("It seems we need a new loop when running our commands: %s", exc_str(e))
            cls._loop_need_new = True
            raise RuntimeError("the loop is not reusable")

    @staticmethod
    def _get_new_event_loop():
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
        return event_loop


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
            bundled_git_path = op.join(annex_path, 'git')
            # we only need to consider bundled git if it's actually different
            # from default. (see issue #5030)
            alongside = op.lexists(bundled_git_path) and \
                        bundled_git_path != op.realpath(find_executable('git'))

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

    def run_on_filelist_chunks(self, cmd, files, protocol=None,
                               cwd=None, env=None, **kwargs):
        """Run a git-style command multiple times if `files` is too long

        Parameters
        ----------
        cmd : list
          Sequence of program arguments.
        files : list
          List of files.
        protocol : WitlessProtocol, optional
          Protocol class handling interaction with the running process
          (e.g. output capture). A number of pre-crafted classes are
          provided (e.g `KillOutput`, `NoCapture`, `GitProgress`).
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
        assert isinstance(cmd, list)
        file_chunks = generate_file_chunks(files, cmd)

        results = None
        for i, file_chunk in enumerate(file_chunks):
            # do not pollute with message when there only ever is a single chunk
            if len(file_chunk) < len(files):
                lgr.debug('Process file list chunk %i (length %i)',
                          i, len(file_chunk))
            res = self.run(
                cmd + ['--'] + file_chunk,
                protocol=protocol,
                cwd=cwd,
                env=env,
                **kwargs)
            if results is None:
                results = res
            else:
                for k, v in res.items():
                    results[k] += v
        return results


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
