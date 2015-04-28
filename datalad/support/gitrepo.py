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

from os import getcwd, linesep
from os.path import join as opj, exists, normpath, isabs, commonprefix, relpath, realpath
import logging
import shlex

from functools import wraps

from git import Repo
from git.exc import GitCommandError

from ..support.exceptions import FileNotInRepositoryError
from ..cmd import Runner
from ..utils import optional_args

lgr = logging.getLogger('datalad.gitrepo')

# TODO: Figure out how GIT_PYTHON_TRACE ('full') is supposed to be used.
# Didn't work as expected on a first try. Probably there is a neatier way to
# log Exceptions from git commands.

# TODO: Check whether it makes sense to unify passing of options in a way
# similar to paths. See options_decorator in annexrepo.py
# Note: GitPython is doing something similar already with **kwargs.
# TODO: Figure this out in detail.


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
    if not path:
        return path

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


@optional_args
def normalize_path(func):
    """Decorator to provide unified path conversion for a single file

    Unlike normalize_paths, intended to be used for functions dealing with a
    single filename at a time

    Note
    ----
    This is intended to be used within the repository classes and therefore
    returns a class method!

    The decorated function is expected to take a path at
    first positional argument (after 'self'). Additionally the class `func`
    is a member of, is expected to have an attribute 'path'.
    """

    @wraps(func)
    def newfunc(self, file_, *args, **kwargs):
        file_new = _normalize_path(self.path, file_)
        return func(self, file_new, *args, **kwargs)

    return newfunc


@optional_args
def normalize_paths(func, match_return_type=True):
    """Decorator to provide unified path conversions.

    Note
    ----
    This is intended to be used within the repository classes and therefore
    returns a class method!

    The decorated function is expected to take a path or a list of paths at
    first positional argument (after 'self'). Additionally the class `func`
    is a member of, is expected to have an attribute 'path'.

    Accepts either a list of paths or a single path in a str. Passes a list
    to decorated function either way, but would return based on the value of
    match_return_type and possibly input argument

    Parameters
    ----------
    match_return_type : bool, optional
      If True, and a single string was passed in, it would return the first
      element of the output (after verifying that it is a list of length 1).
      It makes easier to work with single files input.
    """

    @wraps(func)
    def newfunc(self, files, *args, **kwargs):
        if isinstance(files, basestring) or not files:
            files_new = [_normalize_path(self.path, files)]
            single_file = True
        elif isinstance(files, list):
            files_new = [_normalize_path(self.path, path) for path in files]
            single_file = False
        else:
            raise ValueError("_files_decorator: Don't know how to handle instance of %s." %
                             type(files))

        result = func(self, files_new, *args, **kwargs)

        if (result is None) or not match_return_type or not single_file:
            # If function doesn't return anything or no denormalization
            # was requested or it was not a single file
            return result
        elif single_file:
            assert(len(result) == 1)
            return result[0]
        else:
            return RuntimeError("should have not got here... check logic")

    return newfunc


def _remove_empty_items(list_):
    """Remove empty entries from list

    This is needed, since some functions of GitPython may convert
    an empty entry to '.', when used with a list of paths.

    Parameter:
    ----------
    files: list of str

    Returns:
    list of str
    """
    if not isinstance(list_, list):
        lgr.warning(
            "_remove_empty_items() called with non-list type: %s" % type(files))
        return files
    return [file_ for file_ in list_ if file_]


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

        files = _remove_empty_items(files)
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

    @normalize_paths
    def git_remove(self, files, **kwargs):
        """Remove files.

        Parameters:
        -----------
        files: str
          list of paths to remove
        Returns:
        --------
        [str]
          list of successfully removed files.
        """

        files = _remove_empty_items(files)

        return self.repo.index.remove(files, working_tree=True, **kwargs)


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

        self.cmd_call_wrapper(self.repo.index.commit, msg)

    def get_indexed_files(self):
        """Get a list of files in git's index

        Returns:
        --------
        list
            list of paths rooting in git's base dir
        """

        return [x[0] for x in self.cmd_call_wrapper(
            self.repo.index.entries.keys)]

    def git_get_branches(self):
        """Get all branches of the repo.

        Returns:
        -----------
        [str]
            Names of all branches of this repository.
        """
        return [branch.name for branch in self.repo.branches]

    def git_get_active_branch(self):

        return self.repo.active_branch.name

    @normalize_paths(match_return_type=False)
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


    def git_remote_add(self, name, url, options=''):
        """
        """

        return self._git_custom_command('', 'git remote add %s %s %s' %
                                 (options, name, url))

    def git_remote_remove(self, name):
        """
        """

        return self._git_custom_command('', 'git remote remove %s' % name)

    def git_remote_show(self, name='', verbose=False):
        """
        """

        v = "-v" if verbose else ""
        out, err = self._git_custom_command('', 'git remote %s show %s' %
                                            (v, name))
        return out.rstrip(linesep).split(linesep)

    def git_remote_update(self, name='', verbose=False):
        """
        """

        v = "-v" if verbose else ''
        self._git_custom_command('', 'git remote %s update %s' %
                                        (name, v))

    def git_fetch(self, name, options=''):
        """
        """

        self._git_custom_command('', 'git fetch %s %s' %
                                        (options, name))

    def git_get_remote_url(self, name):
        """We need to know, where to clone from, if a remote is
        requested
        """

        out, err =self._git_custom_command(
            '', 'git config --get remote.%s.url' %name)
        return out.rstrip(linesep)

    def git_pull(self, name='', options=''):
        """
        """

        return self._git_custom_command('', 'git pull %s %s' % (options, name))

    def git_push(self, name='', options=''):
        """
        """

        self._git_custom_command('', 'git push %s %s' % (options, name))

    def git_checkout(self, name, options=''):
        """
        """

        self._git_custom_command('', 'git checkout %s %s' % (options, name))

    def git_get_files(self, branch=None):
        """Get a list of files in git.

        Lists the files in the (remote) branch.

        Parameters:
        -----------
        branch: str
          Name of the branch to query.
        Returns:
        --------
        [str]
          list of files.
        """

        # TODO: This does not work as expected. Figure out!
        # For now keep it as is, since it nevertheless provides
        # the info needed for collections.
        cmd_str = 'git ls-files' + \
                  (' --with-tree %s' % branch if branch else '')
        out, err = self._git_custom_command(
            '', cmd_str)
        return out.rstrip(linesep).split(linesep)

    def git_get_file_content(self, file_, branch='HEAD'):
        """

        Returns:
        --------
        [str]
          content of file_ as a list of lines.
        """

        out, err = self._git_custom_command(
            '', 'git cat-file blob %s:%s' % (branch, file_))
        return out.rstrip(linesep).split(linesep)
