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

from os import linesep
from os.path import join as opj, exists, normpath, isabs, commonprefix, relpath, realpath, isdir, abspath
from os.path import dirname, basename
from os.path import curdir, pardir, sep
# shortcuts
_curdirsep = curdir + sep
_pardirsep = pardir + sep

import logging
import shlex
from six import string_types

from functools import wraps

import git
from git.exc import GitCommandError, NoSuchPathError, InvalidGitRepositoryError
from git.objects.blob import Blob

from ..support.exceptions import CommandError
from ..support.exceptions import FileNotInRepositoryError
from ..cmd import Runner
from ..utils import optional_args, on_windows, getpwd
from ..utils import swallow_logs
from ..utils import swallow_outputs

lgr = logging.getLogger('datalad.gitrepo')

# Override default GitPython's DB backend to talk directly to git so it doesn't interfer with
# possible operations performed by gc/repack
default_git_odbt = git.GitCmdObjectDB

# TODO: Figure out how GIT_PYTHON_TRACE ('full') is supposed to be used.
# Didn't work as expected on a first try. Probably there is a neatier way to
# log Exceptions from git commands.

# TODO: Check whether it makes sense to unify passing of options in a way
# similar to paths. See options_decorator in annexrepo.py
# Note: GitPython is doing something similar already with **kwargs.
# TODO: Figure this out in detail.


def _normalize_path(base_dir, path):
    """Helper to check paths passed to methods of this class.

    Checks whether `path` is beneath `base_dir` and normalizes it.
    Additionally paths are converted into relative paths with respect to
    `base_dir`, considering PWD in case of relative paths. This
    is intended to be used in repository classes, which means that
    `base_dir` usually will be the repository's base directory.

    Parameters
    ----------
    path: str
        path to be normalized
    base_dir: str
        directory to serve as base to normalized, relative paths

    Returns
    -------
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
        # path might already be a symlink pointing to annex etc,
        # so realpath only its directory, to get "inline" with realpath(base_dir)
        # above
        path = opj(realpath(dirname(path)), basename(path))
        if commonprefix([path, base_dir]) != base_dir:
            raise FileNotInRepositoryError(msg="Path outside repository: %s"
                                               % path, filename=path)
        else:
            pass
    # Executive decision was made to not do this kind of magic!
    #
    # elif commonprefix([realpath(getpwd()), base_dir]) == base_dir:
    #     # If we are inside repository, rebuilt relative paths.
    #     path = opj(realpath(getpwd()), path)
    #
    # BUT with relative curdir/pardir start it would assume relative to curdir
    #
    elif path.startswith(_curdirsep) or path.startswith(_pardirsep):
         path = opj(realpath(getpwd()), path)
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
def normalize_paths(func, match_return_type=True, map_filenames_back=False):
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
    match_return_type and possibly input argument.

    If a call to the wrapped function includes normalize_path and it is False
    no normalization happens for that function call (used for calls to wrapped
    functions within wrapped functions, while possible CWD is within a repository)

    Parameters
    ----------
    match_return_type : bool, optional
      If True, and a single string was passed in, it would return the first
      element of the output (after verifying that it is a list of length 1).
      It makes easier to work with single files input.
    map_filenames_back : bool, optional
      If True and returned value is a dictionary, it assumes to carry entries
      one per file, and then filenames are mapped back to as provided from the
      normalized (from the root of the repo) paths
    """

    @wraps(func)
    def newfunc(self, files, *args, **kwargs):

        normalize = _normalize_path if kwargs.pop('normalize_paths', True) \
            else lambda rpath, filepath: filepath

        if files:
            if isinstance(files, string_types) or not files:
                files_new = [normalize(self.path, files)]
                single_file = True
            elif isinstance(files, list):
                files_new = [normalize(self.path, path) for path in files]
                single_file = False
            else:
                raise ValueError("_files_decorator: Don't know how to handle instance of %s." %
                                 type(files))
        else:
            single_file = None
            files_new = []

        if map_filenames_back:
            def remap_filenames(out):
                """Helper to map files back to non-normalized paths"""
                if isinstance(out, dict):
                    assert(len(out) == len(files_new))
                    files_ = [files] if single_file else files
                    mapped = out.__class__()
                    for fin, fout in zip(files_, files_new):
                        mapped[fin] = out[fout]
                    return mapped
                else:
                    return out
        else:
            remap_filenames = lambda x: x

        result = func(self, files_new, *args, **kwargs)

        if single_file is None:
            # no files were provided, nothing we can do really
            return result
        elif (result is None) or not match_return_type or not single_file:
            # If function doesn't return anything or no denormalization
            # was requested or it was not a single file
            return remap_filenames(result)
        elif single_file:
            if len(result) != 1:
                # Magic doesn't apply
                return remap_filenames(result)
            elif isinstance(result, (list, tuple)):
                return result[0]
            elif isinstance(result, dict) and tuple(result)[0] == files_new[0]:
                # assume that returned dictionary has files as keys.
                return tuple(result.values())[0]
            else:
                # no magic can apply
                return remap_filenames(result)
        else:
            return RuntimeError("should have not got here... check logic")

    return newfunc


def _remove_empty_items(list_):
    """Remove empty entries from list

    This is needed, since some functions of GitPython may convert
    an empty entry to '.', when used with a list of paths.

    Parameter:
    ----------
    list_: list of str

    Returns
    -------
    list of str
    """
    if not isinstance(list_, list):
        lgr.warning(
            "_remove_empty_items() called with non-list type: %s" % type(list_))
        return list_
    return [file_ for file_ in list_ if file_]

def Repo(*args, **kwargs):
    """Factory method around git.Repo to consistently initiate with different backend
    """
    if 'odbt' not in kwargs:
        kwargs['odbt'] = default_git_odbt
    return git.Repo(*args, **kwargs)

class GitRepo(object):
    """Representation of a git repository

    Not sure if needed yet, since there is GitPython. By now, wrap it to have
    control. Convention: method's names starting with 'git_' to not be
    overridden accidentally by AnnexRepo.

    """
    __slots__ = ['path', 'repo', 'cmd_call_wrapper']

    # Disable automatic garbage and autopacking
    _GIT_COMMON_OPTIONS = ['-c', 'receive.autogc=0', '-c', 'gc.auto=0']
    # actually no need with default GitPython db backend not in memory default_git_odbt
    # but still allows for faster testing etc.  May be eventually we would make it switchable
    #_GIT_COMMON_OPTIONS = []

    def __init__(self, path, url=None, runner=None, create=True):
        """Creates representation of git repository at `path`.

        If `url` is given, a clone is created at `path`.
        Can also be used to create a git repository at `path`.

        Parameters
        ----------
        path: str
          path to the git repository; In case it's not an absolute path,
          it's relative to PWD
        url: str
          url to the to-be-cloned repository. Requires a valid git url
          according to:
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .
        create: bool
          if true, creates a git repository at `path` if there is none. Also
          creates `path`, if it doesn't exist.
          If set to false, an exception is raised in case `path` doesn't exist
          or doesn't contain a git repository.
        """

        self.path = abspath(normpath(path))
        self.cmd_call_wrapper = runner or Runner(cwd=self.path)
        # TODO: Concept of when to set to "dry".
        #       Includes: What to do in gitrepo class?
        #       Now: setting "dry" means to give a dry-runner to constructor.
        #       => Do it similar in gitrepo/dataset.
        #       Still we need a concept of when to set it and whether this
        #       should be a single instance collecting everything or more
        #       fine grained.

        # TODO: somehow do more extensive checks that url and path don't point to the
        # same location
        if url is not None and not (url == path):
            # TODO: What to do, in case url is given, but path exists already?
            # Just rely on whatever clone_from() does, independently on value
            # of create argument?
            try:
                lgr.debug("Git clone from {0} to {1}".format(url, path))
                self.cmd_call_wrapper(git.Repo.clone_from, url, path)
                lgr.debug("Git clone completed")
                # TODO: more arguments possible: ObjectDB etc.
            except GitCommandError as e:
                # log here but let caller decide what to do
                lgr.error(str(e))
                raise
            except ValueError as e:
                if git.__version__ == '1.0.2' and e.message == "I/O operation on closed file":
                    # bug https://github.com/gitpython-developers/GitPython/issues/383
                    raise GitCommandError("clone has failed, telling ya",
                                          999,  # good number
                                          stdout="%s already exists" if exists(path) else ""
                                          )
                raise  # reraise original

        if create and not exists(opj(path, '.git')):
            try:
                lgr.debug("Initialize empty Git repository at {0}".format(path))
                self.repo = self.cmd_call_wrapper(git.Repo.init, path, True, odbt=default_git_odbt)
            except GitCommandError as e:
                lgr.error(str(e))
                raise
        else:
            try:
                self.repo = self.cmd_call_wrapper(Repo, path)
                lgr.debug("Using existing Git repository at {0}".format(path))
            except (GitCommandError,
                    NoSuchPathError,
                    InvalidGitRepositoryError) as e:
                lgr.error("%s: %s" % (type(e), str(e)))
                raise

    def __repr__(self):
        return "<GitRepo path=%s (%s)>" % (self.path, type(self))

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        """
        return self.path == obj.path


    @classmethod
    def get_toppath(cls, path):
        """Return top-level of a repository given the path.

        If path has symlinks -- they get resolved.

        Return None if no parent directory contains a git repository.
        """
        try:
            with swallow_logs():
                toppath, err = Runner().run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=path,
                    log_stdout=True, log_stderr=True,
                    expect_fail=True, expect_stderr=True)
                return toppath.rstrip('\n\r')
        except CommandError:
            return None
        except OSError:
            return GitRepo.get_toppath(dirname(path))

    @normalize_paths
    def git_add(self, files):
        """Adds file(s) to the repository.

        Parameters
        ----------
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
            except OSError as e:
                lgr.error("git_add: %s" % e)
                raise

        else:
            lgr.warning("git_add was called with empty file list.")

    @normalize_paths(match_return_type=False)
    def git_remove(self, files, **kwargs):
        """Remove files.

        Parameters
        ----------
        files: str
          list of paths to remove

        Returns
        -------
        [str]
          list of successfully removed files.
        """

        files = _remove_empty_items(files)

        return self.repo.index.remove(files, working_tree=True, **kwargs)

    def precommit(self):
        """Perform pre-commit maintenance tasks
        """
        self.repo.index.write()  # flush possibly cached in GitPython changes to index

    def git_commit(self, msg=None, options=None):
        """Commit changes to git.

        Parameters
        ----------
        msg: str
            commit-message
        options:
            to be implemented. See options_decorator in annexrepo.
        """

        # TODO: for some commits we explicitly do not want a message since
        # it would be coming from e.g. staged merge. But it is not clear
        # what gitpython would do about it. doc says that it would
        # convert to string anyways.... bleh
        if not msg:
            msg = "Commit"  # there is no good default
        if options:
            raise NotImplementedError
        lgr.debug("Committing with msg=%r" % msg)
        self.cmd_call_wrapper(self.repo.index.commit, msg)
        #
        #  Was blaming of too much state causes side-effects while interlaving with
        #  git annex cmds so this snippet if to use outside git call
        #self._git_custom_command([], ['git', 'commit'] + \
        #                         (["-m", msg] if msg else []) + \
        #                         (options if options else []))

    def get_indexed_files(self):
        """Get a list of files in git's index

        Returns
        -------
        list
            list of paths rooting in git's base dir
        """

        return [x[0] for x in self.cmd_call_wrapper(
            self.repo.index.entries.keys)]

    def git_get_hexsha(self, branch=None):
        """Return a hexsha for a given branch name. If None - of current branch

        Parameters
        ----------
        branch: str, optional
        """
        # TODO: support not only a branch but any treeish
        if branch is None:
            return self.repo.active_branch.object.hexsha
        for b in self.repo.branches:
            if b.name == branch:
                return b.object.hexsha
        raise ValueError("Unknown branch %s" % branch)

    def git_get_merge_base(self, treeishes):
        """Get a merge base hexsha

        Parameters
        ----------
        treeishes: str or list of str
          List of treeishes (branches, hexshas, etc) to determine the merge base of.
          If a single value provided, returns merge_base with the current branch.

        Returns
        -------
        str or None
          If no merge-base for given commits, or specified treeish doesn't exist,
          None returned
        """
        if isinstance(treeishes, string_types):
            treeishes = [treeishes]
        if not treeishes:
            raise ValueError("Provide at least a single value")
        elif len(treeishes) == 1:
            treeishes = treeishes + [self.git_get_active_branch()]

        try:
            bases = self.repo.merge_base(*treeishes)
        except GitCommandError as exc:
            if "fatal: Not a valid object name" in str(exc):
                return None
            raise

        if not bases:
            return None
        assert(len(bases) == 1)  # we do not do 'all' yet
        return bases[0].hexsha

    def git_get_active_branch(self):

        return self.repo.active_branch.name

    def git_get_branches(self):
        """Get all branches of the repo.

        Returns
        -------
        [str]
            Names of all branches of this repository.
        """

        return [branch.name for branch in self.repo.branches]

    def git_get_remote_branches(self):
        """Get all branches of all remotes of the repo.

        Returns
        -----------
        [str]
            Names of all remote branches.
        """
        # TODO: treat entries like this: origin/HEAD -> origin/master'
        # currently this is done in collection

        # For some reason, this is three times faster than the version below:
        remote_branches = list()
        for remote in self.repo.remotes:
            try:
                for ref in remote.refs:
                    remote_branches.append(ref.name)
            except AssertionError as e:
                if e.message.endswith("did not have any references"):
                    # this will happen with git annex special remotes
                    pass
                else:
                    raise e
        return remote_branches
        # return [branch.strip() for branch in
        #         self.repo.git.branch(r=True).splitlines()]

    def git_get_remotes(self):
        return [remote.name for remote in self.repo.remotes]

    def git_get_files(self, branch=None):
        """Get a list of files in git.

        Lists the files in the (remote) branch.

        Parameters
        ----------
        branch: str
          Name of the branch to query. Default: active branch.

        Returns
        -------
        [str]
          list of files.
        """

        if branch is None:
            # active branch can be queried way faster:
            return self.get_indexed_files()
        else:
            return [item.path for item in self.repo.tree(branch).traverse()
                    if isinstance(item, Blob)]

    def git_get_file_content(self, file_, branch='HEAD'):
        """

        Returns
        -------
        [str]
          content of file_ as a list of lines.
        """

        content_str = self.repo.commit(branch).tree[file_].data_stream.read()

        # in python3 a byte string is returned. Need to convert it:
        from six import PY3
        if PY3:
            conv_str = u''
            for b in bytes(content_str):
                conv_str += chr(b)
            return conv_str.splitlines()
        else:
            return content_str.splitlines()
        # TODO: keep splitlines?

    @normalize_paths(match_return_type=False)
    def _git_custom_command(self, files, cmd_str,
                           log_stdout=True, log_stderr=True, log_online=False,
                           expect_stderr=True, cwd=None, env=None,
                           shell=None, expect_fail=False):
        """Allows for calling arbitrary commands.

        Helper for developing purposes, i.e. to quickly implement git commands
        for proof of concept without the need to figure out, how this is done
        via GitPython.

        Parameters
        ----------
        files: list of files
        cmd_str: str or list
            arbitrary command str. `files` is appended to that string.

        Returns
        -------
        stdout, stderr
        """
        cmd = shlex.split(cmd_str + " " + " ".join(files), posix=not on_windows) \
            if isinstance(cmd_str, string_types) \
            else cmd_str + files
        assert(cmd[0] == 'git')
        cmd = cmd[:1] + self._GIT_COMMON_OPTIONS + cmd[1:]
        return self.cmd_call_wrapper.run(cmd, log_stderr=log_stderr,
                                  log_stdout=log_stdout, log_online=log_online,
                                  expect_stderr=expect_stderr, cwd=cwd,
                                  env=env, shell=shell, expect_fail=expect_fail)

# TODO: --------------------------------------------------------------------

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
        return out.rstrip(linesep).splitlines()

    def git_remote_update(self, name='', verbose=False):
        """
        """

        v = "-v" if verbose else ''
        self._git_custom_command('', 'git remote %s update %s' % (name, v),
                                 expect_stderr=True)

    def git_fetch(self, name, options=''):
        """
        """

        self._git_custom_command('', 'git fetch %s %s' % (options, name),
                                 expect_stderr=True)

    def git_get_remote_url(self, name, push=False):
        """We need to know, where to clone from, if a remote is
        requested
        """

        remote = self.repo.remote(name)
        return remote.config_reader.get(
            'pushurl' if push and remote.config_reader.has_option('pushurl') else 'url')

    def git_get_branch_commits(self, branch, limit=None, stop=None, value=None):
        """Return GitPython's commits for the branch

        Pretty much similar to what 'git log <branch>' does.
        It is a generator which returns top commits first

        Parameters
        ----------
        branch: str
        limit: None | 'left-only', optional
          Limit which commits to report.  If None -- all commits (merged or not),
          if 'left-only' -- only the commits from the left side of the tree upon merges
        stop: str, optional
          hexsha of the commit at which stop reporting (matched one is not reported either)
        value: None | 'hexsha', optional
          What to yield.  If None - entire commit object is yielded, if 'hexsha' only its hexsha
        """

        fvalue = {None: lambda x: x, 'hexsha': lambda x: x.hexsha}[value]

        if not limit:
            def gen():
                # traverse doesn't yield original commit
                co = self.repo.branches[branch].commit
                yield co
                for co_ in co.traverse():
                    yield co_
        elif limit == 'left-only':
            # we need a custom implementation since couldn't figure out how to do with .traversal
            def gen():
                co = self.repo.branches[branch].commit
                while co:
                    yield co
                    co = co.parents[0] if co.parents else None
        else:
            raise ValueError(limit)

        for c in gen():
            if stop and c.hexsha == stop:
                return
            yield fvalue(c)

    def git_pull(self, name='', options=''):
        """
        """

        return self._git_custom_command('', 'git pull %s %s' % (options, name),
                                 expect_stderr=True)

    def git_push(self, name='', options=''):
        """
        """
        self._git_custom_command('', 'git push %s %s' % (options, name),
                                 expect_stderr=True)

    def git_checkout(self, name, options=''):
        """
        """
        # TODO: May be check for the need of -b options herein?

        self._git_custom_command('', 'git checkout %s %s' % (options, name),
                                 expect_stderr=True)

    def git_merge(self, name, options=[], msg=None, **kwargs):
        if msg:
            options = options + ["-m", msg]
        self._git_custom_command('', ['git', 'merge'] + options + [name], **kwargs)

    def git_remove_branch(self, branch):
        self._git_custom_command('', 'git branch -D %s' % branch)

    def git_ls_remote(self, remote, options=None):
        self._git_custom_command('', 'git ls-remote %s %s' %
                                 (options if options is not None else '',
                                  remote))
        # TODO: Return values?
    
    @property
    def dirty(self):
        """Returns true if there is uncommitted changes or files not known to index"""
        return self.repo.is_dirty(untracked_files=True)

    def gc(self, allow_background=False, auto=False):
        """Perform house keeping (garbage collection, repacking)"""
        cmd_options = ['git']
        if not allow_background:
            cmd_options += ['-c', 'gc.autodetach=0']
        cmd_options += ['gc', '--aggressive']
        if auto:
            cmd_options += ['--auto']
        self._git_custom_command('', cmd_options)

    def get_submodules(self):
        """Return a list of git.Submodule instances for all submodules"""
        # check whether we have anything in the repo. if not go home early
        if not self.repo.head.is_valid():
            return []
        return self.repo.submodules

# TODO add_submodule
# remove submodule
# status?
