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

import logging
import re
import shlex
from os import linesep
from os.path import join as opj
from os.path import exists
from os.path import normpath
from os.path import isabs
from os.path import commonprefix
from os.path import relpath
from os.path import realpath
from os.path import abspath
from os.path import dirname
from os.path import basename
from os.path import curdir
from os.path import pardir
from os.path import sep

from six import string_types
from functools import wraps
import git as gitpy
from git.exc import GitCommandError
from git.exc import NoSuchPathError
from git.exc import InvalidGitRepositoryError
from git.objects.blob import Blob

from datalad import ssh_manager
from datalad.cmd import Runner, GitRunner
from datalad.dochelpers import exc_str
from datalad.utils import optional_args
from datalad.utils import on_windows
from datalad.utils import getpwd
from datalad.utils import swallow_logs
from datalad.utils import updated

# imports from same module:
from .external_versions import external_versions
from .exceptions import CommandError
from .exceptions import FileNotInRepositoryError
from .network import RI
from .network import is_ssh

# shortcuts
_curdirsep = curdir + sep
_pardirsep = pardir + sep


lgr = logging.getLogger('datalad.gitrepo')

# Override default GitPython's DB backend to talk directly to git so it doesn't
# interfere with possible operations performed by gc/repack
default_git_odbt = gitpy.GitCmdObjectDB

# TODO: Figure out how GIT_PYTHON_TRACE ('full') is supposed to be used.
# Didn't work as expected on a first try. Probably there is a neatier way to
# log Exceptions from git commands.


# TODO: ignore leading and/or trailing underscore to allow for python-reserved words
@optional_args
def kwargs_to_options(func, split_single_char_options=True,
                      target_kw='options'):
    """Decorator to provide convenient way to pass options to command calls.

    Parameters
    ----------
    func: Callable
        function to decorate
    split_single_char_options: bool
        whether or not to split key and value of single char keyword arguments
        into two subsequent entries of the list
    target_kw: str
        keyword argument to pass the generated list of cmdline arguments to

    Returns
    -------
    Callable
    """

    # TODO: don't overwrite options, but join

    @wraps(func)
    def newfunc(self, *args, **kwargs):
        t_kwargs = dict()
        t_kwargs[target_kw] = \
            gitpy.Git().transform_kwargs(
                split_single_char_options=split_single_char_options,
                **kwargs)
        return func(self, *args, **t_kwargs)
    return newfunc


def to_options(**kwargs):
    """Transform keyword arguments into a list of cmdline options

    Parameters
    ----------
    split_single_char_options: bool

    kwargs:

    Returns
    -------
    list
    """
    # TODO: borrow_docs!

    return gitpy.Git().transform_kwargs(**kwargs)


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

    base_dir = realpath(base_dir)  # realpath OK
    # path = normpath(path)
    # Note: disabled normpath, because it may break paths containing symlinks;
    # But we don't want to realpath relative paths, in case cwd isn't the
    # correct base.

    if isabs(path):
        # path might already be a symlink pointing to annex etc,
        # so realpath only its directory, to get "inline" with
        # realpath(base_dir) above
        path = opj(realpath(dirname(path)), basename(path))  # realpath OK
    # Executive decision was made to not do this kind of magic!
    #
    # elif commonprefix([realpath(getpwd()), base_dir]) == base_dir:
    #     # If we are inside repository, rebuilt relative paths.
    #     path = opj(realpath(getpwd()), path)
    #
    # BUT with relative curdir/pardir start it would assume relative to curdir
    #
    elif path.startswith(_curdirsep) or path.startswith(_pardirsep):
        path = normpath(opj(realpath(getpwd()), path))  # realpath OK
    else:
        # We were called from outside the repo. Therefore relative paths
        # are interpreted as being relative to self.path already.
        return path

    if commonprefix([path, base_dir]) != base_dir:
        raise FileNotInRepositoryError(msg="Path outside repository: %s"
                                           % path, filename=path)

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
def normalize_paths(func, match_return_type=True, map_filenames_back=False,
                    serialize=False):
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
    functions within wrapped functions, while possible CWD is within a
    repository)

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
    serialize : bool, optional
      Loop through files giving only a single one to the function one at a time.
      This allows to simplify implementation and interface to annex commands
      which do not take multiple args in the same call (e.g. checkpresentkey)
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
                raise ValueError("_files_decorator: Don't know how to handle "
                                 "instance of %s." % type(files))
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

        if serialize:  # and not single_file:
            result = [
                func(self, f, *args, **kwargs)
                for f in files_new
            ]
        else:
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
    """Factory method around gitpy.Repo to consistently initiate with different
    backend
    """
    # TODO: This probably doesn't work as intended (or at least not as
    #       consistently as intended). gitpy.Repo could be instantiated by
    #       classmethods Repo.init or Repo.clone_from. In these cases 'odbt'
    #       would be needed as a paramter to these methods instead of the
    #       constructor.
    if 'odbt' not in kwargs:
        kwargs['odbt'] = default_git_odbt
    return gitpy.Repo(*args, **kwargs)


def split_remote_branch(branch):
    """Splits a remote branch's name into the name of the remote and the name
    of the branch.

    Parameters
    ----------
    branch: str
      the remote branch's name to split

    Returns
    -------
    list of str
    """
    assert '/' in branch, \
        "remote branch %s must have had a /" % branch
    assert not branch.endswith('/'), \
        "branch name with trailing / is invalid. (%s)" % branch
    return branch.split('/', 1)


class GitRepo(object):
    """Representation of a git repository

    Not sure if needed yet, since there is GitPython. By now, wrap it to have
    control. Convention: method's names starting with 'git_' to not be
    overridden accidentally by AnnexRepo.

    """
    __slots__ = ['path', 'repo', 'cmd_call_wrapper']

    # Disable automatic garbage and autopacking
    _GIT_COMMON_OPTIONS = ['-c', 'receive.autogc=0', '-c', 'gc.auto=0']
    # actually no need with default GitPython db backend not in memory
    # default_git_odbt but still allows for faster testing etc.
    # May be eventually we would make it switchable _GIT_COMMON_OPTIONS = []

    def __init__(self, path, url=None, runner=None, create=True,
                 git_opts=None, **kwargs):
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
        kwargs:
          keyword arguments serving as additional options to the git-init
          command. Therefore, it makes sense only if called with `create`.

          Generally, this way of passing options to the git executable is
          (or will be) used a lot in this class. It's a transformation of
          python-style keyword arguments (or a `dict`) to command line arguments,
          provided by GitPython.

          A single character keyword will be prefixed by '-', multiple characters
          by '--'. An underscore in the keyword becomes a dash. The value of the
          keyword argument is used as the value for the corresponding command
          line argument. Assigning a boolean creates a flag.

          Examples:
          no_commit=True => --no-commit
          C='/my/path'   => -C /my/path

        """

        if git_opts:
            lgr.warning("TODO: options passed to git are currently ignored.\n"
                        "options received: %s" % git_opts)

        # Sanity check for argument `path`:
        # raise if we cannot deal with `path` at all or
        # if it is not a local thing:
        path = RI(path).localpath

        # try to get a local path from `url`:
        if url is not None:
            try:
                if not isinstance(url, RI):
                    url = RI(url).localpath
                else:
                    url = url.localpath
            except ValueError:
                pass

        self.path = abspath(normpath(path))
        self.cmd_call_wrapper = runner or GitRunner(cwd=self.path)
        # TODO: Concept of when to set to "dry".
        #       Includes: What to do in gitrepo class?
        #       Now: setting "dry" means to give a dry-runner to constructor.
        #       => Do it similar in gitrepo/dataset.
        #       Still we need a concept of when to set it and whether this
        #       should be a single instance collecting everything or more
        #       fine grained.

        # TODO: somehow do more extensive checks that url and path don't point
        #       to the same location

        self.repo = None
        if url is not None and not (url == path):
            # TODO: What to do, in case url is given, but path exists already?
            # Just rely on whatever clone_from() does, independently on value
            # of create argument?
            self.clone(url, path)

        if create and not GitRepo.is_valid_repo(path):
            try:
                lgr.debug("Initialize empty Git repository at {0}".format(path))
                self.repo = self.cmd_call_wrapper(gitpy.Repo.init, path,
                                                  mkdir=True,
                                                  odbt=default_git_odbt,
                                                  **kwargs)
            except GitCommandError as e:
                lgr.error(exc_str(e))
                raise
        else:
            if self.repo is None:
                try:
                    self.repo = self.cmd_call_wrapper(Repo, path)
                    lgr.debug("Using existing Git repository at {0}".format(path))
                except (GitCommandError,
                        NoSuchPathError,
                        InvalidGitRepositoryError) as e:
                    lgr.error("%s: %s" % (type(e), str(e)))
                    raise

    def clone(self, url, path):
        """Clone url into path

        Provides workarounds for known issues (e.g.
        https://github.com/datalad/datalad/issues/785)

        Parameters
        ----------
        url : str
        path : str
        """

        if is_ssh(url):
            cnct = ssh_manager.get_connection(url)
            cnct.open()
            # TODO: with git <= 2.3 keep old mechanism:
            #       with rm.repo.git.custom_environment(GIT_SSH="wrapper_script"):
            env = {'GIT_SSH_COMMAND': "ssh -S %s" % cnct.ctrl_path}
        else:
            env = None
        ntries = 5  # 3 is not enough for robust workaround
        for trial in range(ntries):
            try:
                lgr.debug("Git clone from {0} to {1}".format(url, path))
                self.repo = self.cmd_call_wrapper(gitpy.Repo.clone_from,
                                                  url,
                                                  path,
                                                  env=env,
                                                  odbt=default_git_odbt)
                lgr.debug("Git clone completed")
                break
                # TODO: more arguments possible: ObjectDB etc.
            except GitCommandError as e:
                # log here but let caller decide what to do
                e_str = exc_str(e)
                # see https://github.com/datalad/datalad/issues/785
                if re.search("Request for .*aborted.*Unable to find", str(e),
                             re.DOTALL) \
                        and trial < ntries - 1:
                    lgr.info(
                        "Hit a known issue with Git (see GH#785). Trial #%d, "
                        "retrying",
                        trial)
                    continue
                lgr.error(e_str)
                raise
            except ValueError as e:
                if gitpy.__version__ == '1.0.2' \
                        and "I/O operation on closed file" in str(e):
                    # bug https://github.com/gitpython-developers/GitPython
                    # /issues/383
                    raise GitCommandError(
                        "clone has failed, telling ya",
                        999,  # good number
                        stdout="%s already exists" if exists(path) else "")
                raise  # reraise original

    def __repr__(self):
        return "<GitRepo path=%s (%s)>" % (self.path, type(self))

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        """
        return self.path == obj.path

    @classmethod
    def is_valid_repo(cls, path):
        """Returns if a given path points to a git repository"""
        return exists(opj(path, '.git', 'objects'))

    def is_with_annex(self, only_remote=False):
        """Return True if GitRepo (assumed) at the path has remotes with git-annex branch

        Parameters
        ----------
        only_remote: bool, optional
            Check only remote (no local branches) for having git-annex branch
        """
        return any((b.endswith('/git-annex') for b in self.get_remote_branches())) or \
            ((not only_remote) and any((b == 'git-annex' for b in self.get_branches())))

    @classmethod
    def get_toppath(cls, path, follow_up=True):
        """Return top-level of a repository given the path.

        Parameters
        -----------
        follow_up : bool
          If path has symlinks -- they get resolved by git.  If follow_up is
          True, we will follow original path up until we hit the same resolved
          path.  If no such path found, resolved one would be returned.

        Return None if no parent directory contains a git repository.
        """
        try:
            with swallow_logs():
                toppath, err = Runner().run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=path,
                    log_stdout=True, log_stderr=True,
                    expect_fail=True, expect_stderr=True)
                toppath = toppath.rstrip('\n\r')
        except CommandError:
            return None
        except OSError:
            toppath = GitRepo.get_toppath(dirname(path))

        if follow_up:
            path_ = path
            path_prev = ""
            while path_ and path_ != path_prev:  # on top /.. = /
                if realpath(path_) == toppath:
                    toppath = path_
                    break
                path_prev = path_
                path_ = dirname(path_)

        return toppath

    # classmethod so behavior could be tuned in derived classes
    @classmethod
    def _get_added_files_commit_msg(cls, files):
        if not files:
            return "No files were added"
        msg = "Added %d file" % len(files)
        if len(files) > 1:
            msg += "s"
        return msg + '\n\nFiles:\n' + '\n'.join(files)

    @normalize_paths
    def add(self, files, commit=False, msg=None, git=True, git_options=None, _datalad_msg=False):
        """Adds file(s) to the repository.

        Parameters
        ----------
        files: list
            list of paths to add
        commit: bool
          whether or not to directly commit
        msg: str
          commit message in case `commit=True`. A default message, containing
          the list of files that were added, is created by default.
        git: bool
          somewhat ugly construction to be compatible with AnnexRepo.add();
          has to be always true.
        """

        if git_options:
            lgr.warning("git_options not yet implemented. Ignored.")

        # needs to be True - see docstring:
        assert(git)

        files = _remove_empty_items(files)
        if files:
            try:

                self._git_custom_command(files, ['git', 'add'])

                # Note: as opposed to git cmdline, force is True by default in
                #       gitpython, which would lead to add things, that are
                #       ignored or excluded otherwise
                # 2. Note: There is an issue with globbing (like adding '.'),
                #       which apparently doesn't care for 'force' and therefore
                #       adds '.git/...'. May be it's expanded at the wrong
                #       point in time or sth. like that.
                # For now, use direct call to git add.
                #self.cmd_call_wrapper(self.repo.index.add, files, write=True,
                #                      force=False)
                # TODO: May be make use of 'fprogress'-option to indicate
                # progress
                # But then, we don't have it for git-annex add, anyway.
                #
                # TODO: Is write=True a reasonable way to do it?
                # May be should not write until success of operation is
                # confirmed?
                # What's best in case of a list of files?
            except OSError as e:
                lgr.error("add: %s" % e)
                raise

        else:
            lgr.warning("add was called with empty file list.")

        if commit:
            if msg is None:
                msg = self._get_added_files_commit_msg(files)
            self.commit(msg=msg, _datalad_msg=_datalad_msg)

        # Make sure return value from GitRepo is consistent with AnnexRepo
        # currently simulating similar return value, assuming success
        # for all files:
        # TODO: Make return values consistent across both *Repo classes!
        return [{u'file': f, u'success': True} for f in files]

    @normalize_paths(match_return_type=False)
    def remove(self, files, **kwargs):
        """Remove files.

        Parameters
        ----------
        files: str
          list of paths to remove
        kwargs:
          see `__init__`

        Returns
        -------
        [str]
          list of successfully removed files.
        """

        files = _remove_empty_items(files)

        # todo: we are able to remove objects, not necessarily specified by a
        #       path (see below). We may want to make this available at some
        #       point.
        # Multiple types of items are supported which may be be freely mixed.
        #
        #     - path string
        #         Remove the given path at all stages. If it is a directory, you must
        #         specify the r=True keyword argument to remove all file entries
        #         below it. If absolute paths are given, they will be converted
        #         to a path relative to the git repository directory containing
        #         the working tree
        #
        #         The path string may include globs, such as *.c.
        #
        #     - Blob Object
        #         Only the path portion is used in this case.
        #
        #     - BaseIndexEntry or compatible type
        #         The only relevant information here Yis the path. The stage is ignored.

        return self.repo.index.remove(files, working_tree=True, **kwargs)

    def precommit(self):
        """Perform pre-commit maintenance tasks
        """
        # flush possibly cached in GitPython changes to index:
        self.repo.index.write()

    @staticmethod
    def _get_prefixed_commit_msg(msg):
        DATALAD_PREFIX = "[DATALAD]"
        return DATALAD_PREFIX if not msg else "%s %s" % (DATALAD_PREFIX, msg)

    def commit(self, msg=None, options=None, _datalad_msg=False):
        """Commit changes to git.

        Parameters
        ----------
        msg: str
          commit-message
        options: list of str
          cmdline options for git-commit
        _datalad_msg: bool, optional
          To signal that commit is automated commit by datalad, so
          it would carry the [DATALAD] prefix
        """

        if _datalad_msg:
            msg = self._get_prefixed_commit_msg(msg)

        if not msg:
            if options:
                if "--allow-empty-message" not in options:
                        options.append("--allow-empty-message")
                else:
                    options = ["--allow-empty-message"]

        self.precommit()
        if options:
            # we can't pass all possible options to gitpython's implementation
            # of commit. Therefore we need a direct call to git:
            cmd = ['git', 'commit'] + (["-m", msg if msg else ""]) + options
            lgr.debug("Committing via direct call of git: %s" % cmd)
            self._git_custom_command([], cmd)
        else:
            lgr.debug("Committing with msg=%r" % msg)
            self.cmd_call_wrapper(self.repo.index.commit, msg)

    def get_indexed_files(self):
        """Get a list of files in git's index

        Returns
        -------
        list
            list of paths rooting in git's base dir
        """

        return [x[0] for x in self.cmd_call_wrapper(
            self.repo.index.entries.keys)]

    def get_hexsha(self, branch=None):
        """Return a hexsha for a given branch name. If None - of current branch

        Parameters
        ----------
        branch: str, optional
        """
        # TODO: support not only a branch but any treeish
        #       Note: repo.tree(treeish).hexsha
        if branch is None:
            return self.repo.active_branch.object.hexsha
        for b in self.repo.branches:
            if b.name == branch:
                return b.object.hexsha
        raise ValueError("Unknown branch %s" % branch)

    def get_merge_base(self, treeishes):
        """Get a merge base hexsha

        Parameters
        ----------
        treeishes: str or list of str
          List of treeishes (branches, hexshas, etc) to determine the merge
          base of. If a single value provided, returns merge_base with the
          current branch.

        Returns
        -------
        str or None
          If no merge-base for given commits, or specified treeish doesn't
          exist, None returned
        """
        if isinstance(treeishes, string_types):
            treeishes = [treeishes]
        if not treeishes:
            raise ValueError("Provide at least a single value")
        elif len(treeishes) == 1:
            treeishes = treeishes + [self.get_active_branch()]

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

    def get_committed_date(self, branch=None):
        """Get the date stamp of the last commit (in a branch). None if no commit"""
        try:
            commit = next(
                self.get_branch_commits(branch
                                        or self.get_active_branch())
            )
        except Exception as exc:
            lgr.debug("Got exception while trying to get last commit: %s",
                      exc_str(exc))
            return None
        return commit.committed_date

    def get_active_branch(self):
        return self.repo.active_branch.name

    def get_branches(self):
        """Get all branches of the repo.

        Returns
        -------
        [str]
            Names of all branches of this repository.
        """

        return [branch.name for branch in self.repo.branches]

    def get_remote_branches(self):
        """Get all branches of all remotes of the repo.

        Returns
        -----------
        [str]
            Names of all remote branches.
        """
        # TODO: Reconsider melting with get_branches()

        # TODO: treat entries like this: origin/HEAD -> origin/master'
        # currently this is done in collection

        # For some reason, this is three times faster than the version below:
        remote_branches = list()
        for remote in self.repo.remotes:
            try:
                for ref in remote.refs:
                    remote_branches.append(ref.name)
            except AssertionError as e:
                if str(e).endswith("did not have any references"):
                    # this will happen with git annex special remotes
                    pass
                else:
                    raise e
        return remote_branches
        # return [branch.strip() for branch in
        #         self.repo.git.branch(r=True).splitlines()]

    def get_remotes(self, with_refs_only=False):
        """

        Parameters
        ----------
        with_refs_only : bool, optional
          return only remotes with any refs.  E.g. annex special remotes
          would not have any refs

        Returns
        -------
        remotes : list of str
          List of names of the remotes
        """
        if with_refs_only:
            # older versions of GitPython might not tolerate remotes without
            # any references at all, so we need to catch
            remotes = []
            for remote in self.repo.remotes:
                try:
                    if len(remote.refs):
                        remotes.append(remote.name)
                except AssertionError as exc:
                    if "not have any references" not in str(exc):
                        # was some other reason
                        raise
            return remotes
        else:
            return [remote.name for remote in self.repo.remotes]

    def get_files(self, branch=None):
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
        # TODO: RF codes base and melt get_indexed_files() in

        if branch is None:
            # active branch can be queried way faster:
            return self.get_indexed_files()
        else:
            return [item.path for item in self.repo.tree(branch).traverse()
                    if isinstance(item, Blob)]

    def get_file_content(self, file_, branch='HEAD'):
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

    def _gitpy_custom_call(self, cmd, cmd_args=None, cmd_options=None,
                           git_options=None, env=None,

                           # 'old' options for Runner; not sure yet, which of
                           # them are actually still needed:
                           log_stdout=True, log_stderr=True, log_online=False,
                           expect_stderr=True, cwd=None,
                           shell=None, expect_fail=False):

        """Helper to call GitPython's wrapper for git calls.

        The used instance of `gitpy.Git` is bound to the repository,
        which determines its working directory.
        This is used for adhoc implementation of a git command and to
        demonstrate how to use it in more specific implementations.

        Note
        ----
        Aims to replace the use of datalad's `Runner` class for direct git
        calls. (Currently the `_git_custom_command()` method).
        Therefore mimicking its behaviour during RF'ing.

        Parameters
        ----------
        cmd: str
          the native git command to call
        cmd_args: list of str
          arguments to the git command
        cmd_options: dict
          options for the command as key, value pair
          (this transformation, needs some central place to document)
        git_options: dict
          options for the git executable as key, value pair
          (see above)
        env: dict
          environment vaiables to temporarily set for this call

        TODO
        ----
        Example

        Returns
        -------
        (stdout, stderr)
        """

        # TODO: Reconsider when to log/stream what (stdout, stderr) and/or
        # fully implement the behaviour of `Runner`

        if log_online:
            raise NotImplementedError("option 'log_online' not implemented yet")
        with_exceptions = not expect_fail
        if cwd:
            # the gitpy.cmd.Git instance, bound to this repository doesn't allow
            # to explicitly set the working dir, except for using os.getcwd
            raise NotImplementedError("working dir is a read-only property")

        _tmp_shell = gitpy.cmd.Git.USE_SHELL
        gitpy.cmd.Git.USE_SHELL = shell

        if env is None:
            env = {}
        if git_options is None:
            git_options = {}
        if cmd_options is None:
            cmd_options = {}
        cmd_options.update({'with_exceptions': with_exceptions,
                            'with_extended_output': True})

        # TODO: _GIT_COMMON_OPTIONS!

        with self.repo.git.custom_environment(**env):
            try:
                status, std_out, std_err = \
                    self.repo.git(**git_options).__getattr__(cmd)(
                        cmd_args, **cmd_options)
            except GitCommandError as e:
                # For now just reraise. May be raise CommandError instead
                raise
            finally:
                gitpy.cmd.Git.USE_SHELL = _tmp_shell

        if not expect_stderr and std_err:
            lgr.error("Unexpected output on stderr: %s" % std_err)
            raise CommandError
        if log_stdout:
            for line in std_out.splitlines():
                lgr.debug("stdout| " + line)
        if log_stderr:
            for line in std_err.splitlines():
                lgr.log(level=logging.DEBUG if expect_stderr else logging.ERROR,
                        msg="stderr| " + line)

        return std_out, std_err

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
        return self.cmd_call_wrapper.run(
            cmd,
            log_stderr=log_stderr,
            log_stdout=log_stdout,
            log_online=log_online,
            expect_stderr=expect_stderr,
            cwd=cwd,
            env=env,
            shell=shell,
            expect_fail=expect_fail)

# TODO: --------------------------------------------------------------------

    def add_remote(self, name, url, options=None):
        """Register remote pointing to a url
        """
        cmd = ['git', 'remote', 'add']
        if options:
            cmd += options
        cmd += [name, url]

        return self._git_custom_command('', cmd)

    def remove_remote(self, name):
        """Remove existing remote
        """

        return self._git_custom_command(
            '', ['git', 'remote', 'remove', name]
        )

    def show_remotes(self, name='', verbose=False):
        """
        """

        options = ["-v"] if verbose else []
        name = [name] if name else []
        out, err = self._git_custom_command(
            '', ['git', 'remote'] + options + ['show'] + name
        )
        return out.rstrip(linesep).splitlines()

    def update_remote(self, name=None, verbose=False):
        """
        """
        options = ["-v"] if verbose else []
        name = [name] if name else []
        self._git_custom_command(
            '', ['git', 'remote'] + name + ['update'] + options,
            expect_stderr=True
        )

    # TODO: centralize all the c&p code in fetch, pull, push
    # TODO: document **kwargs passed to gitpython
    def fetch(self, remote=None, refspec=None, progress=None, all_=False,
              **kwargs):
        """Fetches changes from a remote (or all_ remotes).

        Parameters
        ----------
        remote: str
          (optional) name of the remote to fetch from. If no remote is given and
          `all_` is not set, the tracking branch is fetched.
        refspec: str
          (optional) refspec to fetch.
        progress:
          passed to gitpython. TODO: Figure it out, make consistent use of it
          and document it.
        all_: bool
          fetch all_ remotes (and all_ of their branches).
          Fails if `remote` was given.
        kwargs:
          passed to gitpython. TODO: Figure it out, make consistent use of it
          and document it.

        Returns
        -------
        list
            FetchInfo objects of the items fetched from remote
        """
        # TODO: options=> **kwargs):
        # Note: Apparently there is no explicit (fetch --all) in gitpython,
        #       but fetch is always bound to a certain remote instead.
        #       Therefore implement it on our own:
        if remote is None:
            if refspec is not None:
                # conflicts with using tracking branch or fetch all remotes
                # For now: Just fail.
                # TODO: May be check whether it fits to tracking branch
                raise ValueError("refspec specified without a remote. (%s)" %
                                 refspec)
            if all_:
                remotes_to_fetch = self.repo.remotes
            else:
                # No explicit remote to fetch.
                # => get tracking branch:
                tb = self.repo.active_branch.tracking_branch().name
                if tb:
                    tb_remote, refspec = split_remote_branch(tb)
                    remotes_to_fetch = [self.repo.remote(tb_remote)]
                else:
                    # No remote, no tracking branch
                    # => fail
                    raise ValueError("Neither a remote is specified to fetch "
                                     "from nor a tracking branch is set up.")
        else:
            remotes_to_fetch = [self.repo.remote(remote)]

        fi_list = []
        for rm in remotes_to_fetch:
            fetch_url = \
                rm.config_reader.get('fetchurl'
                                     if rm.config_reader.has_option('fetchurl')
                                     else 'url')
            if is_ssh(fetch_url):
                cnct = ssh_manager.get_connection(fetch_url)
                cnct.open()
                # TODO: with git <= 2.3 keep old mechanism:
                #       with rm.repo.git.custom_environment(GIT_SSH="wrapper_script"):
                with rm.repo.git.custom_environment(
                        GIT_SSH_COMMAND="ssh -S %s" % cnct.ctrl_path):
                    fi_list += rm.fetch(refspec=refspec, progress=progress, **kwargs)
                    # TODO: progress +kwargs
            else:
                fi_list += rm.fetch(refspec=refspec, progress=progress, **kwargs)
                # TODO: progress +kwargs

        # TODO: fetch returns a list of FetchInfo instances. Make use of it.
        return fi_list

    def pull(self, remote=None, refspec=None, progress=None, **kwargs):
        """See fetch
        """
        if remote is None:
            if refspec is not None:
                # conflicts with using tracking branch or fetch all remotes
                # For now: Just fail.
                # TODO: May be check whether it fits to tracking branch
                raise ValueError("refspec specified without a remote. (%s)" %
                                 refspec)
            # No explicit remote to pull from.
            # => get tracking branch:
            tb = self.repo.active_branch.tracking_branch().name
            if tb:
                tb_remote, refspec = split_remote_branch(tb)
                remote = self.repo.remote(tb_remote)
            else:
                # No remote, no tracking branch
                # => fail
                raise ValueError("No remote specified to fetch from nor a "
                                 "tracking branch is set up.")
        else:
            remote = self.repo.remote(remote)

        fetch_url = \
            remote.config_reader.get(
                'fetchurl' if remote.config_reader.has_option('fetchurl')
                else 'url')
        if is_ssh(fetch_url):
            cnct = ssh_manager.get_connection(fetch_url)
            cnct.open()
            # TODO: with git <= 2.3 keep old mechanism:
            #       with remote.repo.git.custom_environment(GIT_SSH="wrapper_script"):
            with remote.repo.git.custom_environment(
                    GIT_SSH_COMMAND="ssh -S %s" % cnct.ctrl_path):
                return remote.pull(refspec=refspec, progress=progress, **kwargs)
                # TODO: progress +kwargs
        else:
            return remote.pull(refspec=refspec, progress=progress, **kwargs)
            # TODO: progress +kwargs

    def push(self, remote=None, refspec=None, progress=None, all_=False,
             **kwargs):
        """See fetch
        Returns
        -------
        list
            PushInfo objects of the items pushed to remote
        """

        if remote is None:
            if refspec is not None:
                # conflicts with using tracking branch or fetch all remotes
                # For now: Just fail.
                # TODO: May be check whether it fits to tracking branch
                raise ValueError("refspec specified without a remote. (%s)" %
                                 refspec)
            if all_:
                remotes_to_push = self.repo.remotes
            else:
                # No explicit remote to fetch.
                # => get tracking branch:
                tb = self.repo.active_branch.tracking_branch().name
                if tb:
                    tb_remote, refspec = split_remote_branch(tb)
                    remotes_to_push = [self.repo.remote(tb_remote)]
                else:
                    # No remote, no tracking branch
                    # => fail
                    raise ValueError("No remote specified to fetch from nor a "
                                     "tracking branch is set up.")
        else:
            remotes_to_push = [self.repo.remote(remote)]

        pi_list = []
        for rm in remotes_to_push:
            push_url = \
                rm.config_reader.get('pushurl'
                                     if rm.config_reader.has_option('pushurl')
                                     else 'url')
            if is_ssh(push_url):
                cnct = ssh_manager.get_connection(push_url)
                cnct.open()
                # TODO: with git <= 2.3 keep old mechanism:
                #       with rm.repo.git.custom_environment(GIT_SSH="wrapper_script"):
                with rm.repo.git.custom_environment(
                        GIT_SSH_COMMAND="ssh -S %s" % cnct.ctrl_path):
                    pi_list += rm.push(refspec=refspec, progress=progress, **kwargs)
                    # TODO: progress +kwargs
            else:
                pi_list += rm.push(refspec=refspec, progress=progress, **kwargs)
                # TODO: progress +kwargs
        return pi_list

    def get_remote_url(self, name, push=False):
        """Get the url of a remote.

        Reads the configuration of remote `name` and returns its url or None,
        if there is no url configured.

        Parameters
        ----------
        name: str
          name of the remote
        push: bool
          if True, get the pushurl instead of the fetch url.
        """
        cfg_reader = self.repo.remote(name).config_reader
        if push:
            if cfg_reader.has_option('pushurl'):
                return cfg_reader.get('pushurl')
            else:
                return None
        else:
            if cfg_reader.has_option('url'):
                return cfg_reader.get('url')
            else:
                return None

    def set_remote_url(self, name, url, push=False):
        """Set the URL a remote is pointing to

        Sets the URL of the remote `name`. Requires the remote to already exist.

        Parameters
        ----------
        name: str
          name of the remote
        url: str
        push: bool
          if True, set the push URL, otherwise the fetch URL
        """

        cmd = ["git", "remote", "set-url"]
        if push:
            cmd.append("--push")
        cmd += [name, url]
        return self._git_custom_command('', cmd)

    def get_branch_commits(self, branch, limit=None, stop=None, value=None):
        """Return GitPython's commits for the branch

        Pretty much similar to what 'git log <branch>' does.
        It is a generator which returns top commits first

        Parameters
        ----------
        branch: str
        limit: None | 'left-only', optional
          Limit which commits to report.  If None -- all commits (merged or not),
          if 'left-only' -- only the commits from the left side of the tree upon
          merges
        stop: str, optional
          hexsha of the commit at which stop reporting (matched one is not
          reported either)
        value: None | 'hexsha', optional
          What to yield.  If None - entire commit object is yielded, if 'hexsha'
          only its hexsha
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
            # we need a custom implementation since couldn't figure out how to
            # do with .traversal
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

    def checkout(self, name, options=None):
        """
        """
        # TODO: May be check for the need of -b options herein?
        cmd = ['git', 'checkout']
        if options:
            cmd += options
        cmd += [str(name)]

        self._git_custom_command('', cmd, expect_stderr=True)

    # TODO: Before implementing annex merge, find usages and check for a needed
    # change to call super().merge
    def merge(self, name, options=None, msg=None, allow_unrelated=False, **kwargs):
        if options is None:
            options = []
        if msg:
            options = options + ["-m", msg]
        if allow_unrelated and external_versions['cmd:git'] >= '2.9':
            options += ['--allow-unrelated-histories']
        self._git_custom_command(
            '', ['git', 'merge'] + options + [name],
            **kwargs
        )

    def remove_branch(self, branch):
        self._git_custom_command(
            '', ['git', 'branch', '-D', branch]
        )

    def ls_remote(self, remote, options=None):
        if options is None:
            options = []
        self._git_custom_command(
            '', ['git', 'ls-remote'] + options + [remote]
        )
        # TODO: Return values?

    @property
    def dirty(self):
        """Returns true if there are uncommitted changes or files not known to
        index"""
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

    def get_submodules(self, sorted_=True):
        """Return a list of git.Submodule instances for all submodules"""
        # check whether we have anything in the repo. if not go home early
        if not self.repo.head.is_valid():
            return []
        submodules = self.repo.submodules
        if sorted_:
            submodules = sorted(submodules, key=lambda x: x.path)
        return submodules

    def add_submodule(self, path, name=None, url=None, branch=None):
        """Add a new submodule to the repository.

        This will alter the index as well as the .gitmodules file, but will not
        create a new commit.  If the submodule already exists, no matter if the
        configuration differs from the one provided, the existing submodule
        is considered as already added and no further action is performed.

        Parameters
        ----------
        path : str
          repository-relative path at which the submodule should be located, and
          which will be created as required during the repository initialization.
        name : str or None
          name/identifier for the submodule. If `None`, the `path` will be used
          as name.
        url : str or None
          git-clone compatible URL. If `None`, the repository is assumed to
          exist, and the url of the first remote is taken instead. This is
          useful if you want to make an existing repository a submodule of
          another one.
        branch : str or None
          name of branch to be checked out in the submodule. The given branch
          must exist in the remote repository, and will be checked out locally
          as a tracking branch. If `None`, remote HEAD will be checked out.
        """
        if name is None:
            name = path
        # XXX the following should do it, but GitPython will refuse to add a submodule
        # unless you specify a URL that is configured as one of its remotes, or you
        # specify no URL, but the repo has at least one remote.
        # this is stupid, as for us it is valid to not have any remote, because we can
        # still obtain the submodule from a future publication location, based on the
        # parent
        # gitpy.Submodule.add(self.repo, name, path, url=url, branch=branch)
        # going git native instead
        cmd = ['git', 'submodule', 'add', '--name', name]
        if branch is not None:
            cmd += ['-b', branch]
        if url is None:
            if not isabs(path):
                path = opj(curdir, path)
            url = path
        cmd += [url, path]
        self._git_custom_command('', cmd)
        # TODO: return value

    def deinit_submodule(self, path, **kwargs):
        """Deinit a submodule


        Parameters
        ----------
        path: str
            path to the submodule; relative to `self.path`
        kwargs:
            see `__init__`
        """

        kwargs = updated(kwargs, {'insert_kwargs_after': 'deinit'})
        self._gitpy_custom_call('submodule', ['deinit', path],
                                cmd_options=kwargs)
        # TODO: return value

    def update_submodule(self, path, mode='checkout', init=False):
        """Update a registered submodule.

        This will make the submodule match what the superproject expects by
        cloning missing submodules and updating the working tree of the
        submodules. The "updating" can be done in several ways depending
        on the value of submodule.<name>.update configuration variable, or
        the `mode` argument.

        Parameters
        ----------
        path : str
          Identifies which submodule to operate on by it's repository-relative
          path.
        mode : {checkout, rebase, merge}
          Update procedure to perform. 'checkout': the commit recorded in the
          superproject will be checked out in the submodule on a detached HEAD;
          'rebase': the current branch of the submodule will be rebased onto
          the commit recorded in the superproject; 'merge': the commit recorded
          in the superproject will be merged into the current branch in the
          submodule.
        init : bool
          If True, initialize all submodules for which "git submodule init" has
          not been called so far before updating.
        """
        cmd = ['git', 'submodule', 'update', '--%s' % mode]
        if init:
            cmd.append('--init')
        cmd += ['--', path]
        self._git_custom_command('', cmd)
        # TODO: return value

    def tag(self, tag):
        """Assign a tag to current commit

        Parameters
        ----------
        tag : str
          Custom tag label.
        """
        # TODO later to be extended with tagging particular commits and signing
        self._git_custom_command(
            '', ['git', 'tag', str(tag)]
        )

    def get_tracking_branch(self, branch=None):
        """Get the tracking branch for `branch` if there is any.

        Parameters
        ----------
        branch: str
            local branch to look up. If none is given, active branch is used.

        Returns
        -------
        tuple
            (remote or None, refspec or None) of the tracking branch
        """
        if branch is None:
            branch = self.get_active_branch()

        cfg_reader = self.repo.config_reader()
        sct = "branch \"{0}\"".format(branch)
        track_remote = cfg_reader.get_value(section=sct,
                                            option="remote",
                                            default="DATALAD_DEFAULT")
        if track_remote == "DATALAD_DEFAULT":
            # we have no "tracking remote"
            track_remote = None
        track_branch = cfg_reader.get_value(section=sct,
                                            option="merge",
                                            default="DATALAD_DEFAULT")
        if track_branch == "DATALAD_DEFAULT":
            # we have no tracking branch
            track_branch = None

        return track_remote, track_branch

    @property
    def count_objects(self):
        """return dictionary with count, size(in KiB) information of git objects
        """

        count_cmd = ['git', 'count-objects', '-v']
        count_str, err = self._git_custom_command('', count_cmd)
        count = {key: int(value)
                 for key, value in [item.split(': ')
                                    for item in count_str.split('\n')
                                    if len(item.split(': ')) == 2]}
        return count

    def get_deleted_files(self):
        """return a list of paths with deleted files (deletion not yet commited)"""
        return [f.split('\t')[1]
                for f in self.repo.git.diff('--raw', '--name-status').split('\n')
                if f.split('\t')[0] == 'D']

# TODO
# remove submodule
# status?
