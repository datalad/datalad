# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""
from datalad.operations import OperationsBase
from datalad.cmd import Runner
from datalad.utils import (
    quote_cmdlinearg,
    on_windows,
)


class PurePythonOperations(OperationsBase):
    def make_directory(self, path, force=False):
        path.mkdir(
            parents=force,
            exist_ok=force,
        )

    def exists(self, path):
        return path.exists() or path.is_symlink()


class PosixShellOperations(PurePythonOperations):
    def __init__(self, cwd=None, env=None):
        super(PosixShellOperations, self).__init__(cwd=cwd)

        self._runner = Runner(
            # pull from superclass, who knows what might have been
            # done to it
            cwd=self._cwd,
            env=env,
        )

    def _run(self,
             cmd,
             log_stdout=True,
             log_stderr=True,
             log_online=False,
             expect_stderr=False,
             expect_fail=False,
             stdin=None):
        """Internal helper to execute command.

        MUST NOT BE CALLED by non-(sub)class code.
        """
        return self._runner.run(
            cmd,
            log_stdout=log_stdout,
            log_stderr=log_stderr,
            log_online=log_online,
            expect_stderr=expect_stderr,
            expect_fail=expect_fail,
            stdin=stdin,
        )

    def remove(self, path, recursive=False):
        self._run('rm {} -f {}'.format(
            '-r' if recursive else '',
            quote_cmdlinearg))


class WindowsShellOperations(PurePythonOperations):
    pass


LocalOperation = WindowsShellOperations if on_windows else PosixShellOperations
