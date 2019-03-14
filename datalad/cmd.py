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
import shlex
import atexit
import functools
import tempfile

from collections import OrderedDict
from six import (
    PY3,
    PY2,
    string_types,
    binary_type,
    text_type,
)
from .support import path as op
from .consts import GIT_SSH_COMMAND
from .dochelpers import exc_str
from .support.exceptions import CommandError
from .support.protocol import (
    NullProtocol,
    ExecutionTimeProtocol,
    ExecutionTimeExternalsProtocol,
)
from .utils import (
    on_windows,
    get_tempfile_kwargs,
    assure_unicode,
    assure_bytes,
    unlink,
)
from .dochelpers import borrowdoc

lgr = logging.getLogger('datalad.cmd')

# In python3 to split byte stream on newline, it must be bytes
linesep_bytes = os.linesep.encode()

_TEMP_std = sys.stdout, sys.stderr
# To be used in the temp file name to distinguish the ones we create
# in Runner so we take care about their removal, in contrast to those
# which might be created outside and passed into Runner
_MAGICAL_OUTPUT_MARKER = "_runneroutput_"

if PY2:
    # TODO apparently there is a recommended substitution for Python2
    # which is a backported implementation of python3 subprocess
    # https://pypi.python.org/pypi/subprocess32/
    file_class = file
else:
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

        if isinstance(cmd, string_types) or isinstance(cmd, list):
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
                    'datalad.log.cmd', opt, default=default)
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
                     level={True: 9,
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
        stdout, stderr = binary_type(), binary_type()

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
            if not (stdout_ or stderr_):
                # no output was generated, so sleep a tiny bit
                time.sleep(0.001)

        # Handle possible remaining output
        stdout_, stderr_ = proc.communicate()
        # ??? should we condition it on log_stdout in {'offline'} ???
        stdout += self._process_remaining_output(outputstream, stdout_, *stdout_args)
        stderr += self._process_remaining_output(errstream, stderr_, *stderr_args)

        return stdout, stderr

    def _process_remaining_output(self, stream, out_, *pargs):
        """Helper to process output which might have been obtained from popen or
        should be loaded from file"""
        out = binary_type()
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
                if isinstance(out_, text_type):
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
                self._log_err(line.decode('utf-8') if PY3 else line,
                              expected)
            else:  # pragma: no cover
                raise RuntimeError("must not get here")
            return (line + suf) if suf else line
        # it was output already directly but for code to work, return ""
        return binary_type()

    def run(self, cmd, log_stdout=True, log_stderr=True, log_online=False,
            expect_stderr=False, expect_fail=False,
            cwd=None, env=None, shell=None, stdin=None):
        """Runs the command `cmd` using shell.

        In case of dry-mode `cmd` is just added to `commands` and it is
        actually executed otherwise.
        Allows for separately logging stdout and stderr  or streaming it to
        system's stdout or stderr respectively.

        Note: Using a string as `cmd` and shell=True allows for piping,
              multiple commands, etc., but that implies shlex.split() is not
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
            set it to True and output will be logged at level 9 unless
            exit status is non-0 (in non-online mode only, in online -- would
            log at 9)

        expect_fail: bool, optional
            Normally, if command exits with non-0 status, it is considered an
            error and logged at level 11 (above DEBUG). But if the call intended
            for checking routine, such messages are usually not needed, thus
            it will be logged at level 9.

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
                shell = isinstance(cmd, string_types)

            if self.protocol.records_ext_commands:
                prot_exc = None
                prot_id = self.protocol.start_section(
                    shlex.split(cmd, posix=not on_windows)
                    if isinstance(cmd, string_types)
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

                if PY3:
                    # Decoding was delayed to this point
                    def decode_if_not_None(x):
                        return "" if x is None else binary_type.decode(x)
                    # TODO: check if we can avoid PY3 specific here
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
                    msg = "Failed to run %r%s. Exit code=%d.%s%s" \
                        % (cmd, " under %r" % (popen_cwd), status,
                           "" if log_online else " out=%s" % out[0],
                           "" if log_online else " err=%s" % out[1])
                    lgr.log(9 if expect_fail else 11, msg)
                    raise CommandError(text_type(cmd), msg, status, out[0], out[1])
                else:
                    self.log("Finished running %r with status %s" % (cmd, status),
                             level=8)
            finally:
                # Those streams are for us to close if we asked for a PIPE
                # TODO -- assure closing the files import pdb; pdb.set_trace()
                _cleanup_output(outputstream, proc.stdout)
                _cleanup_output(errstream, proc.stderr)

        else:
            if self.protocol.records_ext_commands:
                self.protocol.add_section(shlex.split(cmd,
                                                      posix=not on_windows)
                                          if isinstance(cmd, string_types)
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

        Logs at level 9 by default and adds "Protocol:"-prefix in order to
        log the used protocol.
        """
        level = kwargs.pop('level', 9)
        if isinstance(self.protocol, NullProtocol):
            lgr.log(level, msg, *args, **kwargs)
        else:
            if args:
                msg = msg % args
            lgr.log(level, "{%s} %s" % (
                self.protocol.__class__.__name__, msg)
            )


class GitRunner(Runner):
    """
    Runner to be used to run git and git annex commands

    Overloads the runner class to check & update GIT_DIR and
    GIT_WORK_TREE environment variables set to the absolute path
    if is defined and is relative path
    """
    _GIT_PATH = None

    @borrowdoc(Runner)
    def __init__(self, *args, **kwargs):
        super(GitRunner, self).__init__(*args, **kwargs)
        self._check_git_path()

    @staticmethod
    def _check_git_path():
        """If using bundled git-annex, we would like to use bundled with it git

        Thus we will store _GIT_PATH a path to git in the same directory as annex
        if found.  If it is empty (but not None), we do nothing
        """
        if GitRunner._GIT_PATH is None:
            from distutils.spawn import find_executable
            # with all the nesting of config and this runner, cannot use our
            # cfg here, so will resort to dark magic of environment options
            if (os.environ.get('DATALAD_USE_DEFAULT_GIT', '0').lower()
                    in ('1', 'on', 'true', 'yes')):
                git_fpath = find_executable("git")
                if git_fpath:
                    GitRunner._GIT_PATH = ''
                    lgr.log(9, "Will use default git %s", git_fpath)
                    return  # we are done - there is a default git avail.
                # if not -- we will look for a bundled one

            annex_fpath = find_executable("git-annex")
            if not annex_fpath:
                # not sure how to live further anyways! ;)
                alongside = False
            else:
                annex_path = op.dirname(op.realpath(annex_fpath))
                alongside = op.lexists(op.join(annex_path, 'git'))
            GitRunner._GIT_PATH = annex_path if alongside else ''
            lgr.log(9, "Will use git under %r (no adjustments to PATH if empty "
                       "string)", GitRunner._GIT_PATH)
            assert(GitRunner._GIT_PATH is not None)  # we made the decision!

    @staticmethod
    def get_git_environ_adjusted(env=None):
        """
        Replaces GIT_DIR and GIT_WORK_TREE with absolute paths if relative path and defined
        """
        # if env set copy else get os environment
        git_env = env.copy() if env else os.environ.copy()
        if GitRunner._GIT_PATH:
            git_env['PATH'] = op.pathsep.join([GitRunner._GIT_PATH, git_env['PATH']]) \
                if 'PATH' in git_env \
                else GitRunner._GIT_PATH

        for varstring in ['GIT_DIR', 'GIT_WORK_TREE']:
            var = git_env.get(varstring)
            if var:                                    # if env variable set
                if not op.isabs(var):                   # and it's a relative path
                    git_env[varstring] = op.abspath(var)  # to absolute path
                    lgr.log(9, "Updated %s to %s", varstring, git_env[varstring])

        if 'GIT_SSH_COMMAND' not in git_env:
            git_env['GIT_SSH_COMMAND'] = GIT_SSH_COMMAND
            git_env['GIT_SSH_VARIANT'] = 'ssh'

        return git_env

    def run(self, cmd, env=None, *args, **kwargs):
        out, err = super(GitRunner, self).run(
            cmd, env=self.get_git_environ_adjusted(env), *args, **kwargs)
        # All communication here will be returned as unicode
        # TODO: do that instead within the super's run!
        return assure_unicode(out), assure_unicode(err)
