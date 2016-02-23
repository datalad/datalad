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

from .dochelpers import exc_str
from .support.exceptions import CommandError
from .support.protocol import NullProtocol, DryRunProtocol, \
    ExecutionTimeProtocol, ExecutionTimeExternalsProtocol
from .utils import on_windows
from . import cfg

lgr = logging.getLogger('datalad.cmd')

_TEMP_std = sys.stdout, sys.stderr

if PY2:
    # TODO apparently there is a recommended substitution for Python2
    # which is a backported implementation of python3 subprocess
    # https://pypi.python.org/pypi/subprocess32/
    pass

class Runner(object):
    """Provides a wrapper for calling functions and commands.

    An object of this class provides a methods calls shell commands or python
    functions, allowing for protocolling the calls and output handling.

    Outputs (stdout and stderr) can be either logged or streamed to system's
    stdout/stderr during execution.
    This can be enabled or disabled for both of them independently.
    Additionally, a protocol object can be a used with the Runner. Such a
    protocol has to implement datalad.support.protocol.ProtocolInterface, is
    able to record calls and allows for dry runs.
    """

    __slots__ = ['commands', 'dry', 'cwd', 'env', 'protocol']

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
            cfg = os.environ.get('DATALAD_CMD_PROTOCOL', 'null')
            protocol = {
                'externals-time': ExecutionTimeExternalsProtocol,
                'time': ExecutionTimeProtocol,
                'null': NullProtocol
            }[cfg]()
            if cfg != 'null':
                # we need to dump it into a file at the end
                # TODO: config cmd.protocol_prefix = protocol
                filename = '%s-%s.log' % (
                    os.environ.get('DATALAD_CMD_PROTOCOL_PREFIX', 'protocol'),
                    id(self)
                )
                atexit.register(functools.partial(protocol.write_to_file, filename))

        self.protocol = protocol

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

    # Two helpers to encapsulate formatting/output
    def _log_out(self, line):
        if line:
            self.log("stdout| " + line.rstrip('\n'))

    def _log_err(self, line, expected=False):
        if line:
            self.log("stderr| " + line.rstrip('\n'),
                     level={True: logging.DEBUG,
                            False: logging.ERROR}[expected])

    def _get_output_online(self, proc, log_stdout, log_stderr,
                           expect_stderr=False, expect_fail=False):
        stdout, stderr = binary_type(), binary_type()
        while proc.poll() is None:
            if log_stdout:
                line = proc.stdout.readline()
                if line:
                    stdout += line
                    self._log_out(line.decode())
                    # TODO: what level to log at? was: level=5
                    # Changes on that should be properly adapted in
                    # test.cmd.test_runner_log_stdout()
            else:
                pass

            if log_stderr:
                line = proc.stderr.readline()
                if line:
                    stderr += line
                    self._log_err(line.decode() if PY3 else line,
                                  expect_stderr or expect_fail)
                    # TODO: what's the proper log level here?
                    # Changes on that should be properly adapted in
                    # test.cmd.test_runner_log_stderr()
            else:
                pass

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
                prot_id = self.protocol.start_section([str(f),
                                                 "args=%s" % str(args),
                                                 "kwargs=%s" % str(kwargs)])

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
                self.protocol.add_section([str(f),
                                             "args=%s" % str(args),
                                             "kwargs=%s" % str(kwargs)],
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
    # TODO:  this is all crawl specific -- should be moved away
    if cfg.getboolean('crawl', 'dryrun', default=False):
        kwargs = kwargs.copy()
        kwargs['protocol'] = DryRunProtocol()
    return Runner(*args, **kwargs)