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
from datalad.support.operations.operations_abstract import (
    OperationsBase
)

from datalad.cmd import Runner
from datalad.utils import (
    quote_cmdlinearg,
    on_windows,
)


class PurePythonOperations(OperationsBase):
    def make_directory(self, path, force=False):
        path = self._ensure_absolute(path)
        path.mkdir(
            parents=force,
            exist_ok=force,
        )

    def exists(self, path):
        path = self._ensure_absolute(path)
        return path.exists() or path.is_symlink()

    def rename(self, src, dst):
        src = self._ensure_absolute(src)
        dst = self._ensure_absolute(dst)
        return src.rename(dst)


class PosixShellOperations(PurePythonOperations):
    def __init__(self, cwd=None, env=None):
        super(PosixShellOperations, self).__init__(cwd=cwd)

        self._runner = Runner(
            # pull from superclass, who knows what might have been
            # done to it
            cwd=quote_cmdlinearg(str(self._cwd)),
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
        # Note, that this would currently raise non-specific CommandError
        self._run('rm {} -f {}'.format(
            '-r' if recursive else '',
            quote_cmdlinearg(str(path))))


class WindowsShellOperations(PurePythonOperations):

    # Note that, while this currently a plain copy of PosixShellOperations,
    # it seems unlikely that it would be good idea to make this a subclass of
    # PosixShellOperations in the long run. Or may be it is. We need to see a
    # few more usecases, I think.

    def __init__(self, cwd=None, env=None):
        super(WindowsShellOperations, self).__init__(cwd=cwd)

        self._runner = Runner(
            # pull from superclass, who knows what might have been
            # done to it
            cwd=quote_cmdlinearg(str(self._cwd)),
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
        # Note, that this would currently raise non-specific CommandError
        self._run('rm {} -f {}'.format(
            '-r' if recursive else '',
            quote_cmdlinearg(str(path))))


LocalOperation = WindowsShellOperations if on_windows else PosixShellOperations
