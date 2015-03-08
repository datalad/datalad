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
import shlex
import sys
import logging

lgr = logging.getLogger('datalad.cmd')


class Runner(object):
    """Provides a wrapper for system calls.

    An object of this class provides a method to make system calls.
    Outputs (stdout and stderr) are streamed to stdout during execution as if you were calling it from command line.
    Additionally allows for dry runs. This is achieved by initializing the `Runner` with `dry=True`.
    The Runner will then collect all calls as strings in `cmdBuffer`.
    """

    __slots__ = ['cmdBuffer', 'dry']

    def __init__(self, dry=False):
        self.dry = dry
        self.cmdBuffer = []

    def run(self, cmd):
        """

        Parameters
        ----------
        cmd : str
          String defining the command call.

        Returns
        -------
        Status code as returned by the called command.
        """

        self.log("Running: %s" % cmd)

        if not self.dry:
            # pipeArgs = shlex.split(cmd)

            proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT, shell=True)
            # shell=True allows for piping, multiple commands, etc., but that implies to not use shlex.split()
            # and is considered to be a security hazard. So be careful with input.
            # Alternatively we would have to parse `cmd` and create multiple subprocesses.

            status = proc.wait()

            if not status in [0, None]:
                msg = "Failed to run %r. Exit code=%d" \
                      % (cmd, status)
                lgr.error(msg)
                raise RuntimeError(msg)

            else:
                self.log("Finished running %r with status %s" % (cmd, status),
                         level=8)
                return status

        else:
            self.cmdBuffer.append(cmd)
        return None

    def log(self, msg, level=None):
        if level is None:
            logf = lgr.debug
        else:
            logf = lambda msg: lgr.log(level, msg)
        if self.dry:
            lgr.debug("DRY: %s" % msg)
        else:
            lgr.debug(msg)