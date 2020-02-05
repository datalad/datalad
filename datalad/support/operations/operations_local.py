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

    # TODO: force? How about permissions?
    def remove(self, path, recursive=False):
        path = self._ensure_absolute(path)

        def _remove_dir_content(path):

            for p in path.iterdir():
                if p.is_dir():
                    _remove_dir_content(p)
                    p.rmdir()
                else:
                    p.unlink()

        if path.is_dir():
            if recursive:
                _remove_dir_content(path)
            else:
                path.rmdir()
        else:
            path.unlink()

    def change_permissions(self, path, mode, recursive=False):
        # TODO: mode should prob. mapped from labels to whatever is needed
        #      (platform independent -> dependent)
        if on_windows:
            # TODO: There's no obv. approach to realize this on windows yet.
            #       Need to figure current concept of permissions and groups
            #       on windows and how to use them.
            #
            # Note, that pathlib's chmod is explicitly "like os.chmod". From
            # docs:
            #
            # Note
            #
            # Although Windows supports chmod(), you can only set the file’s
            # read-only flag with it (via the stat.S_IWRITE and stat.S_IREAD
            # constants or a corresponding integer value). All other bits are
            # ignored.

            raise NotImplementedError("Not implemented on windows")

        path = self._ensure_absolute(path)
        path.chmod(mode)

        if recursive and path.is_dir():
            [self.change_permissions(pp, mode, recursive=True)
             for pp in path.iterdir()]

    def change_group(self, path, label, recursive=False):
        if on_windows:
            # TODO: same as change_permissions: Not clear ATM, what we can
            #       and should do on windows.
            raise NotImplementedError("Not implemented on windows")
        path = self._ensure_absolute(path)
        from shutil import chown
        chown(path, group=label)
        if recursive and path.is_dir():
            [self.change_group(pp, label, recursive=True)
             for pp in path.iterdir()]


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


# Note: Currently outcommented, since WindowsShellOperations hasn't implemented
# anything yet. However, eventually the idea is to automatically determine which
# operations class to use:
# LocalOperation = WindowsShellOperations if on_windows else
# PosixShellOperations
LocalOperation = PurePythonOperations
