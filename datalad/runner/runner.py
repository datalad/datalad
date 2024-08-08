# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base DataLad command execution runner
"""
from __future__ import annotations

import logging
from os import PathLike
from queue import Queue
from typing import (
    IO,
    cast,
)

from .coreprotocols import NoCapture
from .exception import CommandError
from .nonasyncrunner import (
    ThreadedRunner,
    _ResultGenerator,
)
from .protocol import (
    GeneratorMixIn,
    WitlessProtocol,
)

lgr = logging.getLogger('datalad.runner.runner')


class WitlessRunner(object):
    """Minimal Runner with support for online command output processing

    It aims to be as simple as possible, providing only essential
    functionality.
    """
    __slots__ = ['cwd', 'env']

    def __init__(self,
                 cwd: str | PathLike | None = None,
                 env: dict | None = None
                 ):
        """
        Parameters
        ----------
        cwd : str or path-like, optional
          If given, commands are executed with this path as PWD,
          the PWD of the parent process is used otherwise.
        env : dict, optional
          Environment to be used for command execution. If `None` is provided,
          the current process environment is inherited by the sub-process. If
          a mapping is provided, it will constitute the complete environment of
          the sub-process, i.e.  no values from the environment of the current
          process will be inherited. If `env` and `cwd` are given, 'PWD' in the
          environment is set to the string-value of `cwd`.
        """
        self.env = env
        self.cwd = cwd

    def _get_adjusted_env(self,
                          env: dict | None = None,
                          cwd: str | PathLike | None = None,
                          copy: bool = True
                          ) -> dict | None:
        """Return an adjusted execution environment

        This method adjusts the environment provided in `env` to
        reflect the configuration of the runner. It returns
        an altered copy or an altered original, if `copy` is
        `False`.

        Parameters
        ----------
        env
          The environment that should be adjusted

        cwd: str | PathLike | None (default: None)
          If not None, the content of this variable will be
          put into the environment variable 'PWD'.

        copy: bool (default: True)
          if True, the returned environment will be a
          copy of `env`. Else the passed in environment
          is modified. Note: if `env` is not `None` and
          `cwd` is `None` and `copy` is `True`, the
          returned dictionary is still a copy
        """
        env = env.copy() if env is not None and copy is True else env
        if cwd is not None and env is not None:
            # If an environment and 'cwd' is provided, ensure the 'PWD' in the
            # environment is set to the value of 'cwd'.
            env['PWD'] = str(cwd)
        return env

    def run(self,
            cmd: list | str,
            protocol: type[WitlessProtocol] | None = None,
            stdin: bytes | IO | Queue | None = None,
            cwd: PathLike | str | None = None,
            env: dict | None = None,
            timeout: float | None = None,
            exception_on_error: bool = True,
            **kwargs) -> dict | _ResultGenerator:
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
          If the protocol has the GeneratorMixIn-mixin, the run-method
          will return an iterator and can therefore be used in a for-clause.
        stdin : file-like, bytes, Queue, or None
          If stdin is a file-like, it will be directly used as stdin for the
          subprocess. The caller is responsible for writing to it and closing it.
          If stdin is a bytes, it will be fed to stdin of the subprocess.
          If all data is written, stdin will be closed.
          If stdin is a Queue, all elements (bytes) put into the Queue will
          be passed to stdin until None is read from the queue. If None is read,
          stdin of the subprocess is closed.
        cwd : str or path-like, optional
          If given, commands are executed with this path as PWD,
          the PWD of the parent process is used otherwise. Overrides
          any `cwd` given to the constructor.
        env : dict, optional
          Environment to be used for command execution. If given, it will
          completely replace any environment provided to theconstructor. If
          `cwd` is given, 'PWD' in the environment is set to its value.
          This must be a complete environment definition, no values
          from the current environment will be inherited. Overrides
          any `env` given to the constructor.
        timeout: float, optional
          None or the seconds after which a timeout callback is
          invoked, if no progress was made in communicating with
          the sub-process, or if waiting for the subprocess exit
          took more than the specified time. See the protocol and
          `ThreadedRunner` descriptions for a more detailed discussion
          on timeouts.
        exception_on_error : bool, optional
          This argument is first interpreted if the protocol is a subclass
          of `GeneratorMixIn`. If it is `True` (default), a
          `CommandErrorException` is raised by the generator if the
          sub process exited with a return code not equal to zero. If the
          parameter is `False`, no exception is raised. In both cases the
          return code can be read from the attribute `return_code` of
          the generator. Then this argument interpreted within this function
          to not raise `CommandError` if value is False in case of non-0 exit.
        kwargs :
          Passed to the Protocol class constructor.

        Returns
        -------
          dict | _ResultGenerator

            If the protocol is not a subclass of `GeneratorMixIn`, the
            result of protocol._prepare_result will be returned.

            If the protocol is a subclass of `GeneratorMixIn`, a Generator, i.e.
            a `_ResultGenerator`, will be returned. This allows to use this
            method in constructs like:

                for protocol_output in runner.run():
                    ...

            Where the iterator yields whatever protocol.pipe_data_received
            sends into the generator.
            If all output was yielded and the process has terminated, the
            generator will raise StopIteration(return_code), where
            return_code is the return code of the process. The return code
            of the process will also be stored in the "return_code"-attribute
            of the runner. So you could write:

               gen = runner.run()
               for file_descriptor, data in gen:
                   ...

               # get the return code of the process
               result = gen.return_code

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

        applied_cwd = cwd or self.cwd
        applied_env = self._get_adjusted_env(
            env=env or self.env,
            cwd=applied_cwd,
        )

        lgr.debug(
            'Run %r (protocol_class=%s) (cwd=%s)',
            cmd,
            protocol.__name__,
            applied_cwd
        )

        threaded_runner = ThreadedRunner(
            cmd=cmd,
            protocol_class=protocol,
            stdin=stdin,
            protocol_kwargs=kwargs,
            timeout=timeout,
            exception_on_error=exception_on_error,
            cwd=applied_cwd,
            env=applied_env
        )

        results_or_iterator = threaded_runner.run()
        if issubclass(protocol, GeneratorMixIn):
            return results_or_iterator

        results = cast(dict, results_or_iterator)
        # log before any exception is raised
        lgr.debug("Finished %r with status %s", cmd, results['code'])

        # make it such that we always blow if a protocol did not report
        # a return code at all or it was non-0 and we were not asked ignore
        # errors
        return_code = results.get('code', None)
        if return_code is None or (return_code and exception_on_error):
            # the runner has a better idea, doc string warns Protocol
            # implementations not to return these
            results.pop('cmd', None)
            results.pop('cwd', None)
            raise CommandError(
                # whatever the results were, we carry them forward
                cmd=cmd,
                cwd=applied_cwd,
                **results,
            )
        # Denoise result, the return code must be zero at this point.
        results.pop('code', None)
        return results
