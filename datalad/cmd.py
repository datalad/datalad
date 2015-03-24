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

lgr = logging.getLogger('datalad.cmd')


class Runner(object):
    """Provides a wrapper for calling functions and commands.

    An object of this class provides a methods calls shell commands or python functions,
    allowing for dry runs and output handling.

    Outputs (stdout and stderr) can be either logged or streamed to system's stdout/stderr during execution.
    This can be enabled or disabled for both of them independently.
    Additionally allows for dry runs. This is achieved by initializing the `Runner` with `dry=True`.
    The Runner will then collect all calls as strings in `commands`.
    """

    __slots__ = ['commands', 'dry']

    def __init__(self, dry=False):
        self.dry = dry
        self.commands = []

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

        *args and **kwargs:
           see Runner.run() and Runner.call() for available arguments.

        Raises
        ------
        ValueError if cmd is neither a string nor a callable.
        """

        if isinstance(cmd, basestring):
            self.run(cmd, *args, **kwargs)
        elif callable(cmd):
            self.call(cmd, *args, **kwargs)
        else:
            raise ValueError("Argument 'command' is neither a string nor a callable.")
        # TODO: shouldn't it return the functions instead of just calling them?

    # Two helpers to encapsulate formatting/output
    def _log_out(self, line):
        if line:
            self.log("stdout| " + line.rstrip('\n'))

    def _log_err(self, line):
        if line:
            self.log("stderr| " + line.rstrip('\n'),
                     level=logging.ERROR)

    def _get_output_online(self, proc, log_stderr, log_stdout, return_output=False):
        stdout, stderr = [], []
        while proc.poll() is None:
            if log_stdout:
                line = proc.stdout.readline()
                if line != '':
                    if return_output:
                        stdout += line
                    self._log_out(line)
                    # TODO: what level to log at? was: level=5
                    # Changes on that should be properly adapted in
                    # test.cmd.test_runner_log_stdout()
            else:
                pass

            if log_stderr:
                line = proc.stderr.readline()
                if line != '':
                    if return_output:
                        stderr += line
                    self._log_err(line)
                    # TODO: what's the proper log level here?
                    # Changes on that should be properly adapted in
                    # test.cmd.test_runner_log_stderr()
            else:
                pass

        return stdout, stderr

    def _get_output_communicate(self, proc, log_stderr, log_stdout, return_output=False):
        """Delegate collection of output to proc.communicate.  It always collects
        output, thus
        """
        out, err = proc.communicate()

        self._log_out(out)
        self._log_err(err)

        return (out, err)

    def run(self, cmd, log_stdout=True, log_stderr=True,
            log_online=False, return_output=False):
        """Runs the command `cmd` using shell.

        In case of dry-mode `cmd` is just added to `commands` and it is executed otherwise.
        Allows for seperatly logging stdout and stderr  or streaming it to system's stdout
        or stderr respectively.

        Parameters
        ----------
        cmd : str
          String defining the command call.

        log_stdout: bool, optional
            If True, stdout is logged. Goes to sys.stdout otherwise.

        log_stderr: bool, optional
            If True, stderr is logged. Goes to sys.stderr otherwise.

        log_online: bool, optional
            Either to log as output comes in.  Setting to True is preferable for
            running user-invoked actions to provide timely output

        return_output: bool, optional
            If True, return a tuple of two strings (stdout, stderr) in addition
            to the exit code

        Returns
        -------
        Status code as returned by the called command or `None` in case of dry-mode.

        Raises
        ------
        RunTimeError
           if command's exitcode wasn't 0 or None
        (stdout, stderr)
           if return_output=True
        """

        outputstream = subprocess.PIPE if log_stdout else sys.stdout
        errstream = subprocess.PIPE if log_stderr else sys.stderr

        self.log("Running: %s" % (cmd,))

        if not self.dry:

            proc = subprocess.Popen(cmd, stdout=outputstream, stderr=errstream, shell=True)
            # shell=True allows for piping, multiple commands, etc., but that implies to not use shlex.split()
            # and is considered to be a security hazard. So be careful with input.
            # Alternatively we would have to parse `cmd` and create multiple
            # subprocesses.

            meth = self._get_output_online if log_online \
                   else self._get_output_communicate
            out = meth(proc, log_stderr, log_stdout)

            status = proc.poll()

            if status not in [0, None]:
                msg = "Failed to run %r. Exit code=%d" % (cmd, status)
                lgr.error(msg)
                raise RuntimeError(msg)

            else:
                self.log("Finished running %r with status %s" % (cmd, status), level=8)
                if return_output:
                    return 0, out  # return 0 as status, even if it was None to avoid TypeErrors.
                else:
                    return 0
                # TODO: Rethink, when to return status and/or output, since things changed
                # by introducing log_online and return_output parameters.
                # Plus: If we raise exception, returning status may be pointless at all.

        else:
            self.commands.append(cmd)
            out = ("DRY", "DRY")

        if return_output:
            return None, out
        else:
            return None

    def call(self, f, *args, **kwargs):
        """Helper to unify collection of logging all "dry" actions.

        Calls `f` if `Runner`-object is not in dry-mode. Adds `f` along with its arguments to `commands` otherwise.

        f : callable
        *args, **kwargs:
          Callable arguments
        """
        if self.dry:
            self.commands.append("%s args=%s kwargs=%s" % (f, args, kwargs))
        else:
            return f(*args, **kwargs)

    def log(self, msg, level=logging.DEBUG):
        """log helper

        Logs at DEBUG-level by default and adds "DRY:"-prefix for dry runs.
        """
        if self.dry:
            lgr.log(level, "DRY: %s" % msg)
        else:
            lgr.log(level, msg)


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
    except  AttributeError, e:
        lgr.warn("Linking of %s failed (%s), copying file" % (src, e))
        shutil.copyfile(src_realpath, dst)
        shutil.copystat(src_realpath, dst)
