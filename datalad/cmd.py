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
import shutil
import shlex
import atexit
import functools

from six import PY3, PY2
from six import string_types, binary_type
from os.path import abspath, isabs

from .dochelpers import exc_str
from .support.exceptions import CommandError
from .support.protocol import NullProtocol, DryRunProtocol, \
    ExecutionTimeProtocol, ExecutionTimeExternalsProtocol
from .utils import on_windows

lgr = logging.getLogger('datalad.cmd')

_TEMP_std = sys.stdout, sys.stderr

if PY2:
    # TODO apparently there is a recommended substitution for Python2
    # which is a backported implementation of python3 subprocess
    # https://pypi.python.org/pypi/subprocess32/
    pass


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

    __slots__ = ['commands', 'dry', 'cwd', 'env', 'protocol', '__log_outputs']

    def __init__(self, cwd=None, env=None, protocol=None):
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
        self.__log_outputs = None  # we don't know yet either we need ot log every output or not

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

    @property
    def _log_outputs(self):
        if self.__log_outputs is None:
            try:
                from . import cfg
                self.__log_outputs = \
                    cfg.getbool('datalad.log', 'outputs', default=False)
            except ImportError:
                # could be too early, then log!
                return True
        return self.__log_outputs

    # Two helpers to encapsulate formatting/output
    def _log_out(self, line):
        if line and self._log_outputs:
            self.log("stdout| " + line.rstrip('\n'))

    def _log_err(self, line, expected=False):
        if line and self._log_outputs:
            self.log("stderr| " + line.rstrip('\n'),
                     level={True: logging.DEBUG,
                            False: logging.ERROR}[expected])

    def _get_output_online(self, proc, log_stdout, log_stderr,
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

        def decide_to_log(v):
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

        log_stdout_ = decide_to_log(log_stdout)
        log_stderr_ = decide_to_log(log_stderr)

        while proc.poll() is None:
            if log_stdout_:
                lgr.log(3, "Reading line from stdout")
                line = proc.stdout.readline()
                if line and callable(log_stdout_):
                    # Let it be processed
                    line = log_stdout_(line)
                if line:
                    stdout += line
                    self._log_out(line.decode())
                    # TODO: what level to log at? was: level=5
                    # Changes on that should be properly adapted in
                    # test.cmd.test_runner_log_stdout()
            else:
                pass

            if log_stderr_:
                # see for a possibly useful approach to processing output
                # in another thread http://codereview.stackexchange.com/a/17959
                # current problem is that if there is no output on stderr
                # it stalls
                lgr.log(3, "Reading line from stderr")
                line = proc.stderr.readline()
                if line and callable(log_stderr_):
                    # Let it be processed
                    line = log_stderr_(line)
                if line:
                    stderr += line
                    self._log_err(line.decode() if PY3 else line,
                                  expect_stderr or expect_fail)
                    # TODO: what's the proper log level here?
                    # Changes on that should be properly adapted in
                    # test.cmd.test_runner_log_stderr()
            else:
                pass

        if log_stdout in {'offline'} or log_stderr in {'offline'}:
            lgr.log(4, "Issuing proc.communicate() since one of the targets "
                       "is 'offline'")
            stdout_, stderr_ = proc.communicate()
            stdout += stdout_
            stderr += stderr_

        return stdout, stderr

    def run(self, cmd, log_stdout=True, log_stderr=True, log_online=False,
            expect_stderr=False, expect_fail=False,
            cwd=None, env=None, shell=None):
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
            Either to log as output comes in.  Setting to True is preferable
            for running user-invoked actions to provide timely output

        expect_stderr: bool, optional
            Normally, having stderr output is a signal of a problem and thus it
            gets logged at ERROR level.  But some utilities, e.g. wget, use
            stderr for their progress output.  Whenever such output is expected,
            set it to True and output will be logged at DEBUG level unless
            exit status is non-0 (in non-online mode only, in online -- would
            log at DEBUG)

        expect_fail: bool, optional
            Normally, if command exits with non-0 status, it is considered an
            ERROR and logged accordingly.  But if the call intended for checking
            routine, such alarming message should not be logged as ERROR, thus
            it will be logged at DEBUG level.

        cwd : string, optional
            Directory under which run the command (passed to Popen)

        env : string, optional
            Custom environment to pass

        shell: bool, optional
            Run command in a shell.  If not specified, then it runs in a shell
            only if command is specified as a string (not a list)

        Returns
        -------
        (stdout, stderr)

        Raises
        ------
        CommandError
           if command's exitcode wasn't 0 or None. exitcode is passed to
           CommandError's `code`-field. Command's stdout and stderr are stored
           in CommandError's `stdout` and `stderr` fields respectively.
        """

        # TODO:  having two PIPEs is dangerous, and leads to lock downs so we
        # would need either threaded solution as in .communicate or just allow
        # only one to be monitored and another one just being dumped into a file
        outputstream = subprocess.PIPE if log_stdout else sys.stdout
        errstream = subprocess.PIPE if log_stderr else sys.stderr

        self.log("Running: %s" % (cmd,))

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
                proc = subprocess.Popen(cmd, stdout=outputstream,
                                        stderr=errstream,
                                        shell=shell,
                                        cwd=cwd or self.cwd,
                                        env=env or self.env)

            except Exception as e:
                prot_exc = e
                lgr.error("Failed to start %r%r: %s" %
                          (cmd, " under %r" % cwd if cwd else '', exc_str(e)))
                raise

            finally:
                if self.protocol.records_ext_commands:
                    self.protocol.end_section(prot_id, prot_exc)

            if log_online:
                out = self._get_output_online(proc, log_stdout, log_stderr,
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
                msg = "Failed to run %r%s. Exit code=%d. out=%s err=%s" \
                    % (cmd, " under %r" % (cwd or self.cwd), status, out[0], out[1])
                (lgr.debug if expect_fail else lgr.error)(msg)
                raise CommandError(str(cmd), msg, status, out[0], out[1])
            else:
                self.log("Finished running %r with status %s" % (cmd, status),
                         level=8)

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

        f : callable

        `*args`, `**kwargs`:
          Callable arguments
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

    def log(self, msg, level=logging.DEBUG):
        """log helper

        Logs at DEBUG-level by default and adds "Protocol:"-prefix in order to
        log the used protocol.
        """
        if isinstance(self.protocol, NullProtocol):
            lgr.log(level, msg)
        else:
            lgr.log(level, "{%s} %s" % (self.protocol.__class__.__name__, msg))


class GitRunner(Runner):
    """
    Runner to be used to run git and git annex commands

    Overloads the runner class to check & update GIT_DIR and
    GIT_WORK_TREE environment variables set to the absolute path
    if is defined and is relative path
    """

    @staticmethod
    def get_git_environ_adjusted(env=None):
        """
        Replaces GIT_DIR and GIT_WORK_TREE with absolute paths if relative path and defined
        """
        git_env = env.copy() if env else os.environ.copy()         # if env set copy else get os environment

        for varstring in ['GIT_DIR', 'GIT_WORK_TREE']:
            var = git_env.get(varstring)
            if var:                                                # if env variable set
                if not isabs(var):                                 # and it's a relative path
                    git_env[varstring] = abspath(var)              # convert it to absolute path
                    lgr.debug("Updated %s to %s" % (varstring, git_env[varstring]))

        return git_env

    def run(self, cmd, env=None, *args, **kwargs):
        return super(GitRunner, self).run(
            cmd, env=self.get_git_environ_adjusted(), *args, **kwargs)


# ####
# Preserve from previous version
# TODO: document intention
# ####
# this one might get under Runner for better output/control
def link_file_load(src, dst, dry_run=False):
    """Just a little helper to hardlink files's load
    """
    dst_dir = os.path.dirname(dst)
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    if os.path.lexists(dst):
        lgr.debug("Destination file %(dst)s exists. Removing it first"
                  % locals())
        # TODO: how would it interact with git/git-annex
        os.unlink(dst)
    lgr.debug("Hardlinking %(src)s under %(dst)s" % locals())
    src_realpath = os.path.realpath(src)

    try:
        os.link(src_realpath, dst)
    except AttributeError as e:
        lgr.warn("Linking of %s failed (%s), copying file" % (src, e))
        shutil.copyfile(src_realpath, dst)
        shutil.copystat(src_realpath, dst)
    else:
        lgr.log(2, "Hardlinking finished")


def get_runner(*args, **kwargs):
    # needs local import, because the ConfigManager itself needs the runner
    from . import cfg
    # TODO:  this is all crawl specific -- should be moved away
    if cfg.obtain('datalad.crawl.dryrun', default=False):
        kwargs = kwargs.copy()
        kwargs['protocol'] = DryRunProtocol()
    return Runner(*args, **kwargs)
