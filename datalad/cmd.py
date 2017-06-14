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

from collections import OrderedDict
from six import PY3, PY2
from six import string_types, binary_type
from os.path import abspath, isabs, pathsep

from .consts import GIT_SSH_COMMAND
from .dochelpers import exc_str
from .support.exceptions import CommandError
from .support.protocol import NullProtocol, DryRunProtocol, \
    ExecutionTimeProtocol, ExecutionTimeExternalsProtocol
from .utils import on_windows
from .dochelpers import borrowdoc

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
             Switch to instruct either outputs should be logged or not.  If not
             set (default), config 'datalad.log outputs' would be consulted
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
        # we don't know yet either we need ot log every output or not
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
                    line = log_stdout_(line.decode())
                    if line is not None:
                        # we are working with binary type here
                        line = line.encode()
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
                    line = log_stderr_(line.decode())
                    if line is not None:
                        # we are working with binary type here
                        line = line.encode()
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

        stdin: file descriptor
            input stream to connect to stdin of the process.

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

        popen_env = env or self.env

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
            log_args += [cwd or self.cwd]
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
                proc = subprocess.Popen(cmd, stdout=outputstream,
                                        stderr=errstream,
                                        shell=shell,
                                        cwd=cwd or self.cwd,
                                        env=popen_env,
                                        stdin=stdin)

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

    def log(self, msg, *args, **kwargs):
        """log helper

        Logs at DEBUG-level by default and adds "Protocol:"-prefix in order to
        log the used protocol.
        """
        level = kwargs.pop('level', logging.DEBUG)
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
            annex_fpath = find_executable("git-annex")
            if not annex_fpath:
                # not sure how to live further anyways! ;)
                alongside = False
            else:
                annex_path = os.path.dirname(os.path.realpath(annex_fpath))
                if on_windows:
                    # just bundled installations so git should be taken from annex
                    alongside = True
                else:
                    alongside = os.path.lexists(os.path.join(annex_path, 'git'))
            GitRunner._GIT_PATH = annex_path if alongside else ''
            lgr.debug(
                "Will use git under %r (no adjustments to PATH if empty string)",
                GitRunner._GIT_PATH
            )
            assert(GitRunner._GIT_PATH is not None)  # we made the decision!

    @staticmethod
    def get_git_environ_adjusted(env=None):
        """
        Replaces GIT_DIR and GIT_WORK_TREE with absolute paths if relative path and defined
        """
        # if env set copy else get os environment
        git_env = env.copy() if env else os.environ.copy()
        if GitRunner._GIT_PATH:
            git_env['PATH'] = pathsep.join([GitRunner._GIT_PATH, git_env['PATH']]) \
                if 'PATH' in git_env \
                else GitRunner._GIT_PATH

        for varstring in ['GIT_DIR', 'GIT_WORK_TREE']:
            var = git_env.get(varstring)
            if var:                                    # if env variable set
                if not isabs(var):                     # and it's a relative path
                    git_env[varstring] = abspath(var)  # to absolute path
                    lgr.debug("Updated %s to %s" % (varstring, git_env[varstring]))

        if 'GIT_SSH_COMMAND' not in git_env:
            git_env['GIT_SSH_COMMAND'] = GIT_SSH_COMMAND

        return git_env

    def run(self, cmd, env=None, *args, **kwargs):
        return super(GitRunner, self).run(
            cmd, env=self.get_git_environ_adjusted(env), *args, **kwargs)


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
