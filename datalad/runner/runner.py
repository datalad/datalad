# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base DataLad command execution runner
"""

import logging
import os
import subprocess
import tempfile
import warnings

from .coreprotocols import NoCapture
from .exception import CommandError
from .nonasyncrunner import run_command
from .utils import (
    auto_repr,
    ensure_unicode,
    try_multiple,
    unlink,
)

lgr = logging.getLogger('datalad.runner.runner')


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
        cmd : list or str
          Sequence of program arguments. Passing a single string causes
          execution via the platform shell.
        protocol : WitlessProtocol, optional
          Protocol class handling interaction with the running process
          (e.g. output capture). A number of pre-crafted classes are
          provided (e.g `KillOutput`, `NoCapture`, `GitProgress`).
        stdin : byte stream, optional
          File descriptor like, or bytes objects used as stdin for the process.
          Passed verbatim to run_command().
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

        lgr.debug('Run %r (cwd=%s)', cmd, cwd)
        results = run_command(
            cmd,
            protocol,
            stdin,
            protocol_kwargs=kwargs,
            cwd=cwd,
            env=env,
        )

        # log before any exception is raised
        lgr.debug("Finished %r with status %s", cmd, results['code'])

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
