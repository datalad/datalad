# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to Git via GitPython

For further information on GitPython see http://gitpython.readthedocs.org/

"""

from os import getcwd
from os.path import join as opj, exists, normpath, isabs, commonprefix, relpath, realpath
import logging
import shlex

from functools import wraps

from git import Repo
from git.exc import GitCommandError

from datalad.support.exceptions import FileNotInRepositoryError
from datalad.cmd import Runner

lgr = logging.getLogger('datalad.gitrepo')

# TODO: Figure out how GIT_PYTHON_TRACE ('full') is supposed to be used.
# Didn't work as expected on a first try. Probably there is a neatier way to
# log Exceptions from git commands.

# TODO: Check whether it makes sense to unify passing of options in a way
# similar to paths. See options_decorator in annexrepo.py


def _normalize_path(base_dir, path):
    """Helper to check paths passed to methods of this class.

    Checks whether `path` is beneath `base_dir` and normalize it.
    Additionally paths are converted into relative paths with respect to
    `base_dir`, considering os.getcwd() in case of relative paths. This
    is intended to be used in repository classes, which means that
    `base_dir` usually will be the repository's base directory.

    Parameters:
    -----------
    path: str
        path to be normalized
    base_dir: str
        directory to serve as base to normalized, relative paths

    Returns:
    --------
    str:
        path, that is a relative path with respect to `base_dir`
    """
    base_dir = realpath(base_dir)
    # path = normpath(path)
    # Note: disabled normpath, because it may break paths containing symlinks;
    # But we don't want to realpath relative paths, in case cwd isn't the correct base.

    if isabs(path):
        path = realpath(path)
        if commonprefix([path, base_dir]) != base_dir:
            raise FileNotInRepositoryError(msg="Path outside repository: %s"
                                               % path, filename=path)
        else:
            pass

    elif commonprefix([getcwd(), base_dir]) == base_dir:
        # If we are inside repository, rebuilt relative paths.
        path = opj(getcwd(), path)
    else:
        # We were called from outside the repo. Therefore relative paths
        # are interpreted as being relative to self.path already.
        return path

    return relpath(path, start=base_dir)


def normalize_paths(func):
    """Decorator to provide unified path conversions.

    Note
    ----
    This is intended to be used within the repository classes and therefore
    returns a class method!

    The decorated function is expected to take a path or a list of paths at
    first positional argument (after 'self'). Additionally the class `func`
    is a member of, is expected to have an attribute 'path'.

    Accepts either a list of paths or a single path in a str. Passes a list
    to decorated function either way!
    """

    @wraps(func)
    def newfunc(self, files, *args, **kwargs):
        if isinstance(files, basestring):
            files_new = [_normalize_path(self.path, files)]
        elif isinstance(files, list):
            files_new = [_normalize_path(self.path, path) for path in files]
        else:
            raise ValueError("_files_decorator: Don't know how to handle instance of %s." %
                             type(files))
        return func(self, files_new, *args, **kwargs)
    return newfunc


class GitRepo(object):
    """Representation of a git repository

    Not sure if needed yet, since there is GitPython. By now, wrap it to have
    control. Convention: method's names starting with 'git_' to not be
    overridden accidentally by AnnexRepo.

    """
    __slots__ = ['path', 'repo', 'cmd_call_wrapper']

    def __init__(self, path, url=None, runner=None):
        """Creates representation of git repository at `path`.

        If there is no git repository at this location, it will create an empty one.
        Additionally the directory is created if it doesn't exist.
        If url is given, a clone is created at `path`.

        Parameters
        ----------
        path: str
          path to the git repository; In case it's not an absolute path,
          it's relative to os.getcwd()
        url: str
          url to the to-be-cloned repository. Requires a valid git url according to
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .

        """

        self.path = normpath(path)
        self.cmd_call_wrapper = runner or Runner(cwd=self.path)
        # TODO: Concept of when to set to "dry".
        #       Includes: What to do in gitrepo class?
        #       Now: setting "dry" means to give a dry-runner to constructor.
        #       => Do it similar in gitrepo/dataset.
        #       Still we need a concept of when to set it and whether this
        #       should be a single instance collecting everything or more
        #       fine grained.

        if url is not None:
            try:
                self.cmd_call_wrapper(Repo.clone_from, url, path)
                # TODO: more arguments possible: ObjectDB etc.
            except GitCommandError as e:
                # log here but let caller decide what to do
                lgr.error(str(e))
                raise

        if not exists(opj(path, '.git')):
            try:
                self.repo = self.cmd_call_wrapper(Repo.init, path, True)
            except GitCommandError as e:
                lgr.error(str(e))
                raise
        else:
            try:
                self.repo = self.cmd_call_wrapper(Repo, path)
            except GitCommandError as e:
                # TODO: Creating Repo-object from existing git repository might raise other Exceptions
                lgr.error(str(e))
                raise

    @normalize_paths
    def git_add(self, files):
        """Adds file(s) to the repository.

        Parameters:
        -----------
        files: list
            list of paths to add
        """

        if files:
            try:
                self.cmd_call_wrapper(self.repo.index.add, files, write=True)
                # TODO: May be make use of 'fprogress'-option to indicate progress
                # But then, we don't have it for git-annex add, anyway.
                #
                # TODO: Is write=True a reasonable way to do it?
                # May be should not write until success of operation is confirmed?
                # What's best in case of a list of files?
            except OSError, e:
                lgr.error("git_add: %s" % e)
                raise

        else:
            lgr.warning("git_add was called with empty file list.")

    def git_commit(self, msg=None, options=None):
        """Commit changes to git.

        Parameters:
        -----------
        msg: str
            commit-message
        options:
            to be implemented. See options_decorator in annexrepo.
        """

        if not msg:
            msg = "What would be a good default message?"

        self.cmd_call_wrapper(self.repo.index.commit ,msg)

    def get_indexed_files(self):
        """Get a list of files in git's index

        Returns:
        --------
        list
            list of paths rooting in git's base dir
        """

        return [x[0] for x in self.cmd_call_wrapper(
            self.repo.index.entries.keys)]

    @normalize_paths
    def _git_custom_command(self, files, cmd_str,
                           log_stdout=True, log_stderr=True, log_online=False,
                           expect_stderr=False, cwd=None, env=None,
                           shell=None):
        """Allows for calling arbitrary commands.

        Helper for developing purposes, i.e. to quickly implement git commands
        for proof of concept without the need to figure out, how this is done
        via GitPython.

        Parameters:
        -----------
        files: list of files
        cmd_str: str
            arbitrary command str. `files` is appended to that string.

        Returns:
        --------
        stdout, stderr
        """
        cmd = shlex.split(cmd_str + " " + " ".join(files))
        return self.cmd_call_wrapper.run(cmd, log_stderr=log_stderr,
                                  log_stdout=log_stdout, log_online=log_online,
                                  expect_stderr=expect_stderr, cwd=cwd,
                                  env=env, shell=shell)

# TODO: --------------------------------------------------------------------

# THE local collection:
# operations on remotes like looking for certain files, list files, git cat?
# May be better: fetch the remotes -> query branch remote/master

    @normalize_paths
    def git_remove(self, files):
        """git rm
        """
        raise NotImplementedError

    def git_remote_add(self, name, url):
        """
        """
        raise NotImplementedError

    def git_remote_remove(self, name):
        """
        """
        raise NotImplementedError

    def git_fetch(self, whatever):
        """
        """
        raise NotImplementedError

    def git_checkout(self, whatever):
        """
        """
        raise NotImplementedError

    def git_get_remote_url(self, name):
        """We need to know, where to clone from, if a remote is
        requested
        """
        raise NotImplementedError

