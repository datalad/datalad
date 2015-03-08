# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
Wrapper for command calls, allowing for dry runs and output handling

"""


import subprocess
import sys
import logging

lgr = logging.getLogger('datalad.cmd')


class Runner(object):
    """Provides a wrapper for system calls.

    An object of this class provides a method to make system calls.
    Outputs (stdout and stderr) are streamed to stdout during execution as if you were calling it from command line.
    Additionally allows for dry runs. This is achieved by initializing the `Runner` with `dry=True`.
    The Runner will then collect all calls as strings in `commands`.
    """

    __slots__ = ['commands', 'dry']

    def __init__(self, dry=False):
        self.dry = dry
        self.commands = []

    def run(self, cmd):
        """Runs the command `cmd` using shell.

        `cmd` is called and uses stdout whereas stderr is captured and logged.
        In case of dry-mode `cmd` is just added to `commands`.

        Parameters
        ----------
        cmd : str
          String defining the command call.

        Returns
        -------
        Status code as returned by the called command or `None` in case of dry-mode.
        """

        self.log("Running: %s" % cmd)

        if not self.dry:

            proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=subprocess.PIPE, shell=True)
            # shell=True allows for piping, multiple commands, etc., but that implies to not use shlex.split()
            # and is considered to be a security hazard. So be careful with input.
            # Alternatively we would have to parse `cmd` and create multiple subprocesses.

            while proc.poll() is None:
                err_line = proc.stderr.readline()
                if err_line != '':
                    self.log("stderr: %s" % err_line)
                    #TODO: log per line or as a whole?

            status = proc.poll()

            if not status in [0, None]:
                msg = "Failed to run %r. Exit code=%d" % (cmd, status)
                lgr.error(msg)
                raise RuntimeError(msg)

            else:
                self.log("Finished running %r with status %s" % (cmd, status), level=8)
                return status

        else:
            self.commands.append(cmd)
        return None

    def drycall(self, f, *args, **kwargs):
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
    os.link(os.path.realpath(src), dst)
