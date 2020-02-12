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
from datalad.utils import Path


class OperationsBase(object):
    """Abstract class with the desired API for operations.

    Any path-like argument must be a pathlib object.

    Method parameters must be verbose or generic enough to be translatable
    to non-POSIX systems, such as Windows.
    """
    def __init__(self, cwd=None):
        """
        Parameters
        ----------
        cwd : Path or None
          Current working directory to resolve any relative paths against.
          If None, the process working directory (PWD) is used.
        """
        self._cwd = Path.cwd() if cwd is None else cwd

    def _ensure_absolute(self, path):
        """Internal helper to make a path absolute

        If relative path is given, interpret it as relative to initialized CWD
        if any, to PWD otherwise.

        Parameters
        ----------
        path : Path

        Returns
        -------
        Path
        """

        # Note, that this doesn't actually resolve the path. For now, this is
        # intentional to not get completely confusing return values. This is
        # only about interpreting as relative to the correct base.
        # TODO: possibly turn this into a decorator, that allows to assign
        #       arguments of the actual methods, that need to go through this.
        if not path.is_absolute():
            if self._cwd:
                path = self._cwd / path
            else:
                path = Path.cwd() / path
        return path

    def make_directory(self, path, force=False):
        """Create a new directory

        Parameters
        ----------
        path : Path
          Location at which to create a directory.
        force : bool
          Enforce creation of directory, even when it already exists,
          or if parent directories are missing.
        """
        raise NotImplementedError

    def exists(self, path):
        """Test if something exists at the given path

        Parameters
        ----------
        path : Path
          Path to test.

        Returns
        -------
        bool
          True, if the path exists (even in case of a broken symlink), False
          otherwise.
        """
        raise NotImplementedError

    # TODO: force? How about permissions?
    def remove(self, path, recursive=False):
        """Remove the given path

        Note, that this is supposed to not raise in case `path` doesn't exist
        and `recursive` isn't required for an empty directory (as opposed to
        plain shell "rm").

        Parameters
        ----------
        path : Path
          Path to remove.
        recursive : bool
          If True, everything underneath `path` is also removed, If False,
          `path` removal might fail with present content.
        """
        raise NotImplementedError

    def rename(self, src, dst):
        """Rename path `src` to `dst`

        Parameters
        ----------
        src : Path
        dst : Path
        """

        # TODO; specify what happens if `dst` exists. Note, that pathlib would
        # silently replace an existing file on Unix, if permissions allow it.
        # Need a unified behavior across subclasses
        raise NotImplementedError

    # TODO: What do we want to do with symlinks? Follow? Make an option?
    def change_permissions(self, path, mode, recursive=False):
        """Change the permissions for a path

        Parameters
        ----------
        path : Path
          Path to change permissions of.
        mode : str
          Recognized label for a permission mode, such as 'user_readonly'.
        recursive : bool
          Apply change recursively to all content underneath the path, too.
        """
        raise NotImplementedError

    # TODO: What do we want to do with symlinks? Follow? Make an option?
    def change_group(self, path, label, recursive=False):
        """Change the group ownership for a path

        Parameters
        ----------
        path : Path
          Path to change ownership of.
        label : str
          Name of the group.
        recursive : bool
          Apply change recursively to all content underneath the path, too.
        """
        raise NotImplementedError


class RemoteOperationsBase(OperationsBase):
    """Abstract class with the desired API for remote operations.
    """
    def __init__(self, cwd=None, remote_cwd=None):
        """
        Parameters
        ----------
        cwd : Path or None
          Local working directory to resolve any relative paths against.
          If None, the process working directory (PWD) is used.
        remote_cwd : Path or None
          Remote working directory to resolve any remote relative paths
          against. If None, the process working directory (PWD) of the
          remote connection is used.
        """
        super(RemoteOperationsBase, self).__init__(cwd=cwd)

        self._remote_cwd = remote_cwd

    def _ensure_absolute_remote(self, path):
        """Internal helper to make a path absolute

        If relative path is given, interpret it as relative to initialized
        REMOTE_CWD if any, pass into remote operation unchanged otherwise.

        Parameters
        ----------
        path : Path

        Returns
        -------
        Path
        """

        # Note, that this doesn't actually resolve the path. For now, this is
        # intentional to not get completely confusing return values. This is
        # only about interpreting as relative to the correct base.
        # TODO: possibly turn this into a decorator, that allows to assign
        #       arguments of the actual methods, that need to go through this.
        if not path.is_absolute() and self._remote_cwd:
            path = self._remote_cwd / path
        return path

    def get(self, source, destination, recursive=False, preserve_attrs=False):
        # TODO: Doc. Not quite sure yet. For now signature is copied from
        #       SSHConnection. Trying to use it delegating to SSHConnection from
        #       within RemoteSSHShellOperations and differently from within
        #       RemotePersistentSSHShellOperations. Let's see how that works.
        #
        #       Eventually we might even want get/put to be "copy" instead,
        #       that can be performed locally as well. Would most consistent
        #       with base idea about those command abstractions.
        raise NotImplementedError

    def put(self, source, destination, recursive=False, preserve_attrs=False):
        # TODO: Doc. Not quite sure yet. For now signature is copied from
        #       SSHConnection. Trying to use it delegating to SSHConnection from
        #       within RemoteSSHShellOperations and differently from within
        #       RemotePersistentSSHShellOperations. Let's see how that works.
        #
        #       Eventually we might even want get/put to be "copy" instead,
        #       that can be performed locally as well. Would most consistent
        #       with base idea about those command abstractions.
        raise NotImplementedError
