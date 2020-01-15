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

import re
import shlex
import time
import os
import os.path as op
import warnings


from itertools import chain
import logging
from collections import (
    OrderedDict,
    namedtuple
)
from os import linesep
from os.path import (
    join as opj,
    exists,
    normpath,
    isabs,
    commonprefix,
    relpath,
    realpath,
    dirname,
    basename,
    curdir,
    pardir,
    sep
)

import posixpath
from functools import wraps
from weakref import WeakValueDictionary

import git as gitpy
from git import RemoteProgress
from gitdb.exc import BadName
from git.exc import (
    GitCommandError,
    NoSuchPathError,
    InvalidGitRepositoryError
)
from datalad.support.due import due, Doi

from datalad import ssh_manager
from datalad.cmd import (
    GitRunner,
    BatchedCommand
)
from datalad.config import (
    ConfigManager,
    _parse_gitconfig_dump
)

from datalad.consts import (
    GIT_SSH_COMMAND,
    ADJUSTED_BRANCH_EXPR,
)
from datalad.dochelpers import exc_str
import datalad.utils as ut
from datalad.utils import (
    Path,
    PurePosixPath,
    assure_list,
    optional_args,
    on_windows,
    getpwd,
    posix_relpath,
    assure_dir,
    generate_file_chunks,
    assure_unicode
)

# imports from same module:
from .external_versions import external_versions
from .exceptions import (
    CommandError,
    DeprecatedError,
    FileNotInRepositoryError,
    GitIgnoreError,
    InvalidGitReferenceError,
    MissingBranchError,
    OutdatedExternalDependencyWarning,
    PathKnownToRepositoryError,
)
from .network import (
    RI,
    PathRI,
    is_ssh
)
from .path import get_parent_paths
from .repo import (
    PathBasedFlyweight,
    RepoInterface
)

#from git.objects.blob import Blob

# shortcuts
_curdirsep = curdir + sep
_pardirsep = pardir + sep


lgr = logging.getLogger('datalad.gitrepo')
_lgr_level = lgr.getEffectiveLevel()
if _lgr_level <= 2:
    from ..log import LoggerHelper
    # Let's also enable gitpy etc debugging
    gitpy_lgr = LoggerHelper(logtarget="git").get_initialized_logger()
    gitpy_lgr.setLevel(_lgr_level)
    gitpy_lgr.propagate = True

# Override default GitPython's DB backend to talk directly to git so it doesn't
# interfere with possible operations performed by gc/repack
default_git_odbt = gitpy.GitCmdObjectDB

# TODO: Figure out how GIT_PYTHON_TRACE ('full') is supposed to be used.
# Didn't work as expected on a first try. Probably there is a neatier way to
# log Exceptions from git commands.


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
    base_dir: str
        directory to serve as base to normalized, relative paths
    path: str
        path to be normalized

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
            if isinstance(files, str) or not files:
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


if external_versions["cmd:git"] >= "2.24.0":
    # An unintentional change in Git 2.24.0 led to `ls-files -o` traversing
    # into untracked submodules when multiple pathspecs are given, returning
    # repositories that are deeper than the first level. This helper filters
    # these deeper levels out so that save_() doesn't fail trying to add them.
    #
    # TODO: Once an upstream release includes a fix, either set a ceiling on
    # the Git version above or remove _prune_deeper_repos() entirely.
    def _prune_deeper_repos(repos):
        firstlevel_repos = []
        prev = None
        for repo in sorted(repos):
            if not (prev and str(repo).startswith(prev)):
                prev = str(repo)
                firstlevel_repos.append(repo)
        return firstlevel_repos
else:
    def _prune_deeper_repos(repos):
        return repos


def Repo(*args, **kwargs):
    """Factory method around gitpy.Repo to consistently initiate with different
    backend
    """
    # TODO: This probably doesn't work as intended (or at least not as
    #       consistently as intended). gitpy.Repo could be instantiated by
    #       classmethods Repo.init or Repo.clone_from. In these cases 'odbt'
    #       would be needed as a parameter to these methods instead of the
    #       constructor.
    if 'odbt' not in kwargs:
        kwargs['odbt'] = default_git_odbt
    return gitpy.Repo(*args, **kwargs)


def guard_BadName(func):
    """A helper to guard against BadName exception

    Workaround for
    https://github.com/gitpython-developers/GitPython/issues/768
    also see https://github.com/datalad/datalad/issues/2550
    Let's try to precommit (to flush anything flushable) and do
    it again
    """

    @wraps(func)
    def wrapped(repo, *args, **kwargs):
        try:
            return func(repo, *args, **kwargs)
        except BadName:
            repo.precommit()
            return func(repo, *args, **kwargs)

    return wrapped


class GitPythonProgressBar(RemoteProgress):
    """A handler for Git commands interfaced by GitPython which report progress
    """

    # GitPython operates with op_codes which are a mask for actions.
    _known_ops = {
        RemoteProgress.COUNTING: "counting objects",
        RemoteProgress.COMPRESSING: "compressing objects",
        RemoteProgress.WRITING: "writing objects",
        RemoteProgress.RECEIVING: "receiving objects",
        RemoteProgress.RESOLVING: "resolving stuff",
        RemoteProgress.FINDING_SOURCES: "finding sources",
        RemoteProgress.CHECKING_OUT: "checking things out"
    }

    # To overcome the bug when GitPython (<=2.1.11), with tentative fix
    # in https://github.com/gitpython-developers/GitPython/pull/798
    # we will collect error_lines from the last progress bar used by GitPython
    # To do that reliably this class should be used as a ContextManager,
    # or .close() should be called explicitly before analysis of this
    # attribute is done.
    # TODO: remove the workaround whenever new GitPython version provides
    # it natively and we boost versioned dependency on it
    _last_error_lines = None

    def __init__(self, action):
        super(GitPythonProgressBar, self).__init__()
        self._action = action
        from datalad.ui import ui
        self._ui = ui
        self._pbar = None
        self._op_code = None
        GitPythonProgressBar._last_error_lines = None

    def __del__(self):
        self.close()

    def close(self):
        GitPythonProgressBar._last_error_lines = self.error_lines
        self._close_pbar()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _close_pbar(self):
        if self._pbar:
            self._pbar.finish()
        self._pbar = None

    def _get_human_msg(self, op_code):
        """Return human readable action message
        """
        op_id = op_code & self.OP_MASK
        op = self._known_ops.get(op_id, "doing other evil")
        return "%s (%s)" % (self._action, op)

    def update(self, op_code, cur_count, max_count=None, message=''):
        # ATM we ignore message which typically includes bandwidth info etc
        try:
            if not max_count:
                # spotted used by GitPython tests, so may be at times it is not
                # known and assumed to be a 100%...? TODO
                max_count = 100.0
            if op_code:
                # Apparently those are composite and we care only about the ones
                # we know, so to avoid switching the progress bar for no good
                # reason - first & with the mask
                op_code = op_code & self.OP_MASK
            if self._op_code is None or self._op_code != op_code:
                # new type of operation
                self._close_pbar()

                self._pbar = self._ui.get_progressbar(
                    self._get_human_msg(op_code),
                    total=max_count,
                    unit=' objects'
                )
                self._op_code = op_code
            if not self._pbar:
                lgr.error("Ended up without progress bar... how?")
                return
            self._pbar.update(cur_count, increment=False)
        except Exception as exc:
            lgr.debug("GitPythonProgressBar errored with %s", exc_str(exc))
            return
        #import time; time.sleep(0.001)  # to see that things are actually "moving"
        # without it we would get only a blink on initial 0 value, istead of
        # a blink at some higher value.  Anyways git provides those
        # without flooding so should be safe to force here.
        self._pbar.refresh()


# Compatibility kludge.  See GitRepo.get_submodules().
Submodule = namedtuple("Submodule", ["name", "path", "url"])


class GitRepo(RepoInterface, metaclass=PathBasedFlyweight):
    """Representation of a git repository

    """

    # We use our sshrun helper
    GIT_SSH_ENV = {'GIT_SSH_COMMAND': GIT_SSH_COMMAND,
                   'GIT_SSH_VARIANT': 'ssh'}

    # We must check git config to have name and email set, but
    # should do it once
    _config_checked = False

    # Begin Flyweight:

    _unique_instances = WeakValueDictionary()

    def _flyweight_invalid(self):
        return not self.is_valid_git()

    @classmethod
    def _flyweight_reject(cls, id_, *args, **kwargs):
        # TODO:
        # This is a temporary approach. See PR # ...
        # create = kwargs.pop('create', None)
        # kwargs.pop('path', None)
        # if create and kwargs:
        #     # we have `create` plus options other than `path`
        #     return "Call to {0}() with args {1} and kwargs {2} conflicts " \
        #            "with existing instance {3}." \
        #            "This is likely to be caused by inconsistent logic in " \
        #            "your code." \
        #            "".format(cls, args, kwargs, cls._unique_instances[id_])
        pass

    # End Flyweight

    def __hash__(self):
        # the flyweight key is already determining unique instances
        # add the class name to distinguish from strings of a path
        return hash((self.__class__.__name__, self.__weakref__.key))

    # This is the least common denominator to claim that a user
    # used DataLad.
    # For now citing Zenodo's all (i.e., latest) version
    @due.dcite(Doi("10.5281/zenodo.808846"),
               # override path since there is no need ATM for such details
               path="datalad",
               description="DataLad - Data management and distribution platform")
    def __init__(self, path, url=None, runner=None, create=True,
                 git_opts=None, repo=None, fake_dates=False,
                 create_sanity_checks=True,
                 **kwargs):
        """Creates representation of git repository at `path`.

        Can also be used to create a git repository at `path`.

        Parameters
        ----------
        path: str
          path to the git repository; In case it's not an absolute path,
          it's relative to PWD
        url: str, optional
          DEPRECATED -- use .clone() class method
          url to the to-be-cloned repository. Requires a valid git url
          according to:
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .
        create: bool, optional
          if true, creates a git repository at `path` if there is none. Also
          creates `path`, if it doesn't exist.
          If set to false, an exception is raised in case `path` doesn't exist
          or doesn't contain a git repository.
        repo: git.Repo, optional
          GitPython's Repo instance to (re)use if provided
        create_sanity_checks: bool, optional
          Whether to perform sanity checks during initialization (when
          `create=True` and target path is not a valid repo already), such as
          that new repository is not created in the directory where git already
          tracks some files.
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

        # BEGIN Repo validity test
        # We want to fail early for tests, that would be performed a lot. In particular this is about
        # GitRepo.is_valid_repo. We would use the latter to decide whether or not to call GitRepo() only for
        # __init__ to then test the same things again. If we fail early we can save the additional test from outer
        # scope.
        self.path = path

        # Note, that the following three path objects are used often and therefore
        # are stored for performance. Path object creation comes with a cost. Most noteably,
        # this is used for validity checking of the repository.
        self.pathobj = ut.Path(self.path)
        self.dot_git = self.pathobj / '.git'
        # Read a potential .git file in order to not do that over and over again, when testing is_valid_git() etc.
        # TODO: There's still some code duplication with static method GitRepo.get_git_dir()
        #       However, it's returning relative path. So, the logic in usage needs to be unified in order to melt both
        #       pieces.
        if self.dot_git.is_file():
            with self.dot_git.open() as f:
                line = f.readline()
                if line.startswith("gitdir: "):
                    self.dot_git = self.pathobj / line[7:].strip()
                else:
                    raise InvalidGitRepositoryError("Invalid .git file")

        elif self.dot_git.is_symlink():
            self.dot_git = self.dot_git.resolve()

        self._valid_git_test_path = self.dot_git / 'HEAD'
        _valid_repo = self.is_valid_git()

        do_create = False
        if create and not _valid_repo:
            if repo is not None:
                # `repo` passed with `create`, which doesn't make sense
                raise TypeError("argument 'repo' must not be used with 'create'")
            do_create = True
        else:
            # Note: We used to call gitpy.Repo(path) here, which potentially
            # raised NoSuchPathError or InvalidGitRepositoryError. This is
            # used by callers of GitRepo.__init__() to detect whether we have a
            # valid repo at `path`. Now, with switching to lazy loading property
            # `repo`, we detect those cases without instantiating a
            # gitpy.Repo().

            if not exists(path):
                raise NoSuchPathError(path)
            if not _valid_repo:
                raise InvalidGitRepositoryError(path)
        # END Repo validity test

        if url is not None:
            raise DeprecatedError(
                new=".clone() class method",
                version="0.5.0",
                msg="RF: url passed to init()"
            )

        # So that we "share" control paths with git/git-annex
        if ssh_manager:
            ssh_manager.assure_initialized()

        # note: we may also want to distinguish between a path to the worktree
        # and the actual repository

        # Could be used to e.g. disable automatic garbage and autopacking
        # ['-c', 'receive.autogc=0', '-c', 'gc.auto=0']
        self._GIT_COMMON_OPTIONS = []
        # actually no need with default GitPython db backend not in memory
        # default_git_odbt but still allows for faster testing etc.
        # May be eventually we would make it switchable _GIT_COMMON_OPTIONS = []

        if git_opts is None:
            git_opts = {}
        if kwargs:
            git_opts.update(kwargs)

        self.cmd_call_wrapper = runner or GitRunner(cwd=self.path)
        self._repo = repo
        self._cfg = None

        if do_create:  # we figured it out ealier
            self._repo = self._create_empty_repo(path,
                                                 create_sanity_checks, **git_opts)

        # inject git options into GitPython's git call wrapper:
        # Note: `None` currently can happen, when Runner's protocol prevents
        # calls above from being actually executed (DryRunProtocol)
        if self._repo is not None:
            self._repo.git._persistent_git_options = self._GIT_COMMON_OPTIONS

        # with DryRunProtocol path might still not exist
        if exists(self.path):
            self.inode = os.stat(self.path).st_ino
        else:
            self.inode = None

        if fake_dates:
            self.configure_fake_dates()
        # Set by fake_dates_enabled to cache config value across this instance.
        self._fake_dates_enabled = None

    def _create_empty_repo(self, path, sanity_checks=True, **kwargs):
        if not op.lexists(path):
            os.makedirs(path)
        elif sanity_checks and external_versions['cmd:git'] < '2.14.0':
            warnings.warn(
                "Your git version (%s) is too old, we will not safe-guard "
                "against creating a new repository under already known to git "
                "subdirectory" % external_versions['cmd:git'],
                OutdatedExternalDependencyWarning
            )
        elif sanity_checks:
            # Verify that we are not trying to initialize a new git repository
            # under a directory some files of which are already tracked by git
            # use case: https://github.com/datalad/datalad/issues/3068
            try:
                stdout, _ = self._git_custom_command(
                    None, ['git', 'ls-files'], cwd=path, expect_fail=True
                )
                if stdout:
                    raise PathKnownToRepositoryError(
                        "Failing to initialize new repository under %s where "
                        "following files are known to a repository above: %s"
                        % (path, stdout)
                    )
            except CommandError:
                # assume that all is good -- we are not under any repo
                pass

        cmd = ['git', 'init']
        cmd.extend(kwargs.pop('_from_cmdline_', []))
        cmd.extend(to_options(**kwargs))
        lgr.debug(
            "Initialize empty Git repository at '%s'%s",
            path,
            ' %s' % cmd[2:] if cmd[2:] else '')

        try:
            stdout, stderr = self._git_custom_command(
                None,
                cmd,
                cwd=path,
                log_stderr=True,
                log_stdout=True,
                log_online=False,
                expect_stderr=False,
                shell=False,
                # we don't want it to scream on stdout
                expect_fail=True)
        except CommandError as exc:
            lgr.error(exc_str(exc))
            raise
        # we want to return None and have lazy eval take care of
        # the rest
        return

    @property
    def repo(self):
        # with DryRunProtocol path not exist
        if exists(self.path):
            inode = os.stat(self.path).st_ino
        else:
            inode = None
        if self.inode != inode:

            # TODO: - what if we never had any inode? possible?
            #       - also: call to self._repo and only afterwards checking whether it's None seems strange

            # reset background processes invoked by GitPython:
            self._repo.git.clear_cache()
            self.inode = inode

        if self._repo is None:
            # Note, that this may raise GitCommandError, NoSuchPathError,
            # InvalidGitRepositoryError:
            self._repo = self.cmd_call_wrapper(
                Repo,
                self.path)
            lgr.log(8, "Using existing Git repository at %s", self.path)

        # inject git options into GitPython's git call wrapper:
        # Note: `None` currently can happen, when Runner's protocol prevents
        # call of Repo(path) above from being actually executed (DryRunProtocol)
        if self._repo is not None:
            self._repo.git._persistent_git_options = self._GIT_COMMON_OPTIONS

        return self._repo

    @classmethod
    def clone(cls, url, path, *args, **kwargs):
        """Clone url into path

        Provides workarounds for known issues (e.g.
        https://github.com/datalad/datalad/issues/785)

        Parameters
        ----------
        url : str
        path : str
        expect_fail : bool
          Whether expect that command might fail, so error should be logged then
          at DEBUG level instead of ERROR
        """

        if 'repo' in kwargs:
            raise TypeError("argument 'repo' conflicts with cloning")
            # TODO: what about 'create'?

        expect_fail = kwargs.pop('expect_fail', False)
        # fail early on non-empty target:
        from os import listdir
        if exists(path) and listdir(path):
            # simulate actual GitCommandError:
            lgr.warning("destination path '%s' already exists and is not an "
                        "empty directory." % path)
            raise GitCommandError(
                ['git', 'clone', '-v', url, path],
                128,
                "fatal: destination path '%s' already exists and is not an "
                "empty directory." % path)
        else:
            # protect against cloning into existing and obviously dangling
            # instance for that location
            try:
                del cls._unique_instances[path]
            except KeyError:
                # didn't exist - all fine
                pass

        # Massage URL
        url_ri = RI(url) if not isinstance(url, RI) else url
        if not on_windows:
            # if we are on windows, the local path of a URL
            # would not end up being a proper local path and cloning
            # would fail. Don't try to be smart and just pass the
            # URL along unmodified

            # try to get a local path from `url`:
            try:
                url = url_ri.localpath
                url_ri = RI(url)
            except ValueError:
                pass

        if is_ssh(url_ri):
            ssh_manager.get_connection(url).open()
            # TODO: with git <= 2.3 keep old mechanism:
            #       with rm.repo.git.custom_environment(GIT_SSH="wrapper_script"):
            env = GitRepo.GIT_SSH_ENV
        else:
            if isinstance(url_ri, PathRI):
                new_url = os.path.expanduser(url)
                if url != new_url:
                    # TODO: remove whenever GitPython is fixed:
                    # https://github.com/gitpython-developers/GitPython/issues/731
                    lgr.info("Expanded source path to %s from %s", new_url, url)
                    url = new_url
            env = None

        fix_annex = None
        ntries = 5  # 3 is not enough for robust workaround
        for trial in range(ntries):
            try:
                lgr.debug("Git clone from {0} to {1}".format(url, path))
                with GitPythonProgressBar("Cloning") as git_progress:
                    repo = gitpy.Repo.clone_from(
                        url, path,
                        env=env,
                        odbt=default_git_odbt,
                        progress=git_progress
                    )
                # Note/TODO: signature for clone from:
                # (url, to_path, progress=None, env=None, **kwargs)

                lgr.debug("Git clone completed")
                break
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
                    (lgr.debug if expect_fail else lgr.error)(e_str)

                if "Clone succeeded, but checkout failed." in str(e):
                    fix_annex = e
                    break

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

        gr = cls(path, *args, repo=repo, **kwargs)
        if fix_annex:
            # cheap check whether we deal with an AnnexRepo - we can't check the class of `gr` itself, since we then
            # would need to import our own subclass
            if hasattr(gr, 'is_valid_annex'):
                lgr.warning("Experienced issues while cloning. "
                            "Trying to fix it, using git-annex-fsck.")
                if not gr.is_initialized():
                    gr._init()
                gr.fsck()
            else:
                lgr.warning("Experienced issues while cloning: %s", exc_str(fix_annex))
        return gr

    def __del__(self):
        # unbind possibly bound ConfigManager, to prevent all kinds of weird
        # stalls etc
        self._cfg = None
        # Make sure to flush pending changes, especially close batch processes
        # (internal `git cat-file --batch` by GitPython)
        try:
            if getattr(self, '_repo', None) is not None and exists(self.path):
                # gc might be late, so the (temporary)
                # repo doesn't exist on FS anymore
                self._repo.git.clear_cache()
                # We used to write out the index to flush GitPython's
                # state... but such unconditional write is really a workaround
                # and does not play nice with read-only operations - permission
                # denied etc. So disabled 
                #if exists(opj(self.path, '.git')):  # don't try to write otherwise
                #    self.repo.index.write()
        except (InvalidGitRepositoryError, AttributeError):
            # might have being removed and no longer valid or attributes unbound
            pass

    def __repr__(self):
        return "<GitRepo path=%s (%s)>" % (self.path, type(self))

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        """
        return self.path == obj.path

    def is_valid_git(self):
        """Returns whether the underlying repository appears to be still valid

        Note, that this almost identical to the classmethod is_valid_repo(). However,
        if we are testing an existing instance, we can save Path object creations. Since this testing
        is done a lot, this is relevant. Creation of the Path objects in is_valid_repo() takes nearly half the time of
        the entire function.

        Also note, that this method is bound to an instance but still class-dependent, meaning that a subclass
        cannot simply overwrite it. This is particularly important for the call from within __init__(),
        which in turn is called by the subclasses' __init__. Using an overwrite would lead to the wrong thing being
        called.
        """

        return self.dot_git.exists() and (
                not self.dot_git.is_dir() or self._valid_git_test_path.exists()
        )

    @classmethod
    def is_valid_repo(cls, path):
        """Returns if a given path points to a git repository"""
        if not isinstance(path, Path):
            path = Path(path)
        dot_git_path = path / '.git'

        # the aim here is to have this test as cheap as possible, because
        # it is performed a lot
        # recognize two things as good-enough indicators of a present
        # repo: 1) a non-empty .git directory (#3473)
        #          NOTE: It's actually faster (and more accurate) to test for existence of a particular subpath.
        #                This should be something that's there right after git-init. Going for .git/HEAD ATM.
        #
        #                In [11]: %timeit path.exists() and (not path.is_dir() or head_path.exists())
        #                4.93 µs ± 34.8 ns per loop (mean ± std. dev. of 7 runs, 100000 loops each)
        #                In [12]: %timeit path.exists() and (not path.is_dir() or any(path.iterdir()))
        #                12.8 µs ± 150 ns per loop (mean ± std. dev. of 7 runs, 100000 loops each)
        #
        #   and 2) a pointer file or symlink

        return dot_git_path.exists() and (
            not dot_git_path.is_dir() or (dot_git_path / 'HEAD').exists()
        )

    @staticmethod
    def get_git_dir(repo):
        """figure out a repo's gitdir

        '.git' might be a  directory, a symlink or a file

        Note
        ----
        Please try using GitRepo.dot_git instead! That one's not static, but it's cheaper and you should avoid
        not having an instance of a repo you're working on anyway. Note, that the property in opposition to this method
        returns an absolute path.


        Parameters
        ----------
        repo: path or Repo instance
          currently expected to be the repos base dir

        Returns
        -------
        str
          relative path to the repo's git dir; So, default would be ".git"
        """
        if hasattr(repo, 'path'):
            # repo instance like given
            repo = repo.path
        dot_git = op.join(repo, ".git")
        if not op.exists(dot_git):
            raise RuntimeError("Missing .git in %s." % repo)
        elif op.islink(dot_git):
            git_dir = os.readlink(dot_git)
        elif op.isdir(dot_git):
            git_dir = ".git"
        elif op.isfile(dot_git):
            with open(dot_git) as f:
                git_dir = f.readline()
                if git_dir.startswith("gitdir:"):
                    git_dir = git_dir[7:]
                git_dir = git_dir.strip()

        return git_dir

    @property
    def config(self):
        """Get an instance of the parser for the persistent repository
        configuration.

        Note: This allows to also read/write .datalad/config,
        not just .git/config

        Returns
        -------
        ConfigManager
        """
        if self._cfg is None:
            # associate with this dataset and read the entire config hierarchy
            self._cfg = ConfigManager(dataset=self, source='any')
        return self._cfg

    def is_with_annex(self):
        """Report if GitRepo (assumed) has (remotes with) a git-annex branch
        """
        return any(
            b['refname:strip=2'] == 'git-annex' or b['refname:strip=2'].endswith('/git-annex')
            for b in self.for_each_ref_(fields='refname:strip=2', pattern=['refs/heads', 'refs/remotes'])
        )

    @classmethod
    def get_toppath(cls, path, follow_up=True, git_options=None):
        """Return top-level of a repository given the path.

        Parameters
        -----------
        follow_up : bool
          If path has symlinks -- they get resolved by git.  If follow_up is
          True, we will follow original path up until we hit the same resolved
          path.  If no such path found, resolved one would be returned.
        git_options: list of str
          options to be passed to the git rev-parse call

        Return None if no parent directory contains a git repository.
        """
        cmd = ['git']
        if git_options:
            cmd.extend(git_options)
        cmd += ["rev-parse", "--show-toplevel"]
        try:
            toppath, err = GitRunner().run(
                cmd,
                cwd=path,
                log_stdout=True, log_stderr=True,
                expect_fail=True, expect_stderr=True)
            toppath = toppath.rstrip('\n\r')
        except CommandError:
            return None
        except OSError:
            toppath = GitRepo.get_toppath(dirname(path), follow_up=follow_up,
                                          git_options=git_options)

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

    @normalize_paths
    def add(self, files, git=True, git_options=None, update=False):
        """Adds file(s) to the repository.

        Parameters
        ----------
        files: list
          list of paths to add
        git: bool
          somewhat ugly construction to be compatible with AnnexRepo.add();
          has to be always true.
        update: bool
          --update option for git-add. From git's manpage:
           Update the index just where it already has an entry matching
           <pathspec>. This removes as well as modifies index entries to match
           the working tree, but adds no new files.

           If no <pathspec> is given when --update option is used, all tracked
           files in the entire working tree are updated (old versions of Git
           used to limit the update to the current directory and its
           subdirectories).

        Returns
        -------
        list
          Of status dicts.
        """
        # under all circumstances call this class' add_ (otherwise
        # AnnexRepo.add would go into a loop
        return list(GitRepo.add_(self, files, git=git, git_options=git_options,
                    update=update))

    def add_(self, files, git=True, git_options=None, update=False):
        """Like `add`, but returns a generator"""
        # TODO: git_options is used as options for the git-add here,
        # instead of options to the git executable => rename for consistency

        if not git:
            lgr.warning(
                'GitRepo.add() called with git=%s, this should not happen',
                git)
            git = True

        # there is no other way then to collect all files into a list
        # at this point, because we need to pass them at once to a single
        # `git add` call
        files = [_normalize_path(self.path, f) for f in assure_list(files) if f]

        if not (files or git_options or update):
            # wondering why just a warning? in cmdline this is also not an error
            lgr.warning("add was called with empty file list and no options.")
            return

        try:
            # without --verbose git 2.9.3  add does not return anything
            add_out = self._git_custom_command(
                files,
                # Set annex.largefiles to prevent storing files in annex when
                # GitRepo() is instantiated with a v6+ annex repo.
                ['git', '-c', 'annex.largefiles=nothing', 'add'] +
                assure_list(git_options) +
                to_options(update=update) + ['--verbose']
            )
            # get all the entries
            for o in self._process_git_get_output(*add_out):
                yield o
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

        # Make sure return value from GitRepo is consistent with AnnexRepo
        # currently simulating similar return value, assuming success
        # for all files:
        # TODO: Make return values consistent across both *Repo classes!
        return

    @staticmethod
    def _process_git_get_output(stdout, stderr=None):
        """Given both outputs (stderr is ignored atm) of git add - process it

        Primarily to centralize handling in both indirect annex and direct
        modes when ran through proxy
        """
        return [{u'file': f, u'success': True}
                for f in re.findall("'(.*)'[\n$]", assure_unicode(stdout))]

    @normalize_paths(match_return_type=False)
    def remove(self, files, recursive=False, **kwargs):
        """Remove files.

        Calls git-rm.

        Parameters
        ----------
        files: str
          list of paths to remove
        recursive: False
          whether to allow recursive removal from subdirectories
        kwargs:
          see `__init__`

        Returns
        -------
        [str]
          list of successfully removed files.
        """

        files = _remove_empty_items(files)

        if recursive:
            kwargs['r'] = True
        stdout, stderr = self._git_custom_command(
            files, ['git', 'rm'] + to_options(**kwargs))

        # output per removed file is expected to be "rm 'PATH'":
        return [line.strip()[4:-1] for line in stdout.splitlines()]

        #return self.repo.git.rm(files, cached=False, **kwargs)

    def precommit(self):
        """Perform pre-commit maintenance tasks
        """
        # All GitPython commands should take care about flushing index
        # whenever they modify it, so we would not care to do anything
        # if self.repo is not None and exists(opj(self.path, '.git')):  # don't try to write otherwise:
        #     # flush possibly cached in GitPython changes to index:
        #     # if self.repo.git:
        #     #     sys.stderr.write("CLEARING\n")
        #     #     self.repo.git.clear_cache()
        #     self.repo.index.write()

        # Close batched by GitPython git processes etc
        # Ref: https://github.com/gitpython-developers/GitPython/issues/718
        self.repo.__del__()
        pass

    @staticmethod
    def _get_prefixed_commit_msg(msg):
        DATALAD_PREFIX = "[DATALAD]"
        return DATALAD_PREFIX if not msg else "%s %s" % (DATALAD_PREFIX, msg)

    def for_each_ref_(self, fields=('objectname', 'objecttype', 'refname'),
                      pattern=None, points_at=None, sort=None, count=None,
                      contains=None):
        """Wrapper for `git for-each-ref`

        Please see manual page git-for-each-ref(1) for a complete overview
        of its functionality. Only a subset of it is supported by this
        wrapper.

        Parameters
        ----------
        fields : iterable or str
          Used to compose a NULL-delimited specification for for-each-ref's
          --format option. The default field list reflects the standard
          behavior of for-each-ref when the --format option is not given.
        pattern : list or str, optional
          If provided, report only refs that match at least one of the given
          patterns.
        points_at : str, optional
          Only list refs which points at the given object.
        sort : list or str, optional
          Field name(s) to sort-by. If multiple fields are given, the last one
          becomes the primary key. Prefix any field name with '-' to sort in
          descending order.
        count : int, optional
          Stop iteration after the given number of matches.
        contains : str, optional
          Only list refs which contain the specified commit.

        Yields
        ------
        dict with items matching the given `fields`

        Raises
        ------
        ValueError
          if no `fields` are given

        RuntimeError
          if `git for-each-ref` returns a record where the number of
          properties does not match the number of `fields`
        """
        if not fields:
            raise ValueError('no `fields` provided, refuse to proceed')
        fields = assure_list(fields)
        cmd = [
            "git",
            "for-each-ref",
            "--format={}".format(
                '%00'.join(
                    '%({})'.format(f) for f in fields)),
        ]
        if points_at:
            cmd.append('--points-at={}'.format(points_at))
        if contains:
            cmd.append('--contains={}'.format(contains))
        if sort:
            for k in assure_list(sort):
                cmd.append('--sort={}'.format(k))
        if pattern:
            cmd += assure_list(pattern)
        if count:
            cmd.append('--count={:d}'.format(count))

        out, _ = self._git_custom_command(None, cmd)
        for line in out.splitlines():
            props = line.split('\0')
            if len(fields) != len(props):
                raise RuntimeError(
                    'expected fields {} from git-for-each-ref, but got: {}'.format(
                        fields, props))
            yield dict(zip(fields, props))

    def configure_fake_dates(self):
        """Configure repository to use fake dates.
        """
        lgr.debug("Enabling fake dates")
        self.config.set("datalad.fake-dates", "true")

    @property
    def fake_dates_enabled(self):
        """Is the repository configured to use fake dates?
        """
        if self._fake_dates_enabled is None:
            self._fake_dates_enabled = \
                self.config.getbool('datalad', 'fake-dates', default=False)
        return self._fake_dates_enabled

    def add_fake_dates(self, env):
        """Add fake dates to `env`.

        Parameters
        ----------
        env : dict or None
            Environment variables.

        Returns
        -------
        A dict (copied from env), with date-related environment
        variables for git and git-annex set.
        """
        env = (env if env is not None else os.environ).copy()
        # Note: Use _git_custom_command here rather than repo.git.for_each_ref
        # so that we use annex-proxy in direct mode.
        last_date = list(self.for_each_ref_(
            fields='committerdate:raw',
            count=1,
            pattern='refs/heads',
            sort="-committerdate",
        ))

        if last_date:
            # Drop the "contextual" timezone, leaving the unix timestamp.  We
            # avoid :unix above because it wasn't introduced until Git v2.9.4.
            last_date = last_date[0]['committerdate:raw'].split()[0]
            seconds = int(last_date)
        else:
            seconds = self.config.obtain("datalad.fake-dates-start")
        seconds_new = seconds + 1
        date = "@{} +0000".format(seconds_new)

        lgr.debug("Setting date to %s",
                  time.strftime("%a %d %b %Y %H:%M:%S +0000",
                                time.gmtime(seconds_new)))

        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
        env["GIT_ANNEX_VECTOR_CLOCK"] = str(seconds_new)

        return env

    def commit(self, msg=None, options=None, _datalad_msg=False, careless=True,
               files=None, date=None, index_file=None):
        """Commit changes to git.

        Parameters
        ----------
        msg: str, optional
          commit-message
        options: list of str, optional
          cmdline options for git-commit
        _datalad_msg: bool, optional
          To signal that commit is automated commit by datalad, so
          it would carry the [DATALAD] prefix
        careless: bool, optional
          if False, raise when there's nothing actually committed;
          if True, don't care
        files: list of str, optional
          path(s) to commit
        date: str, optional
          Date in one of the formats git understands
        index_file: str, optional
          An alternative index to use
        """

        self.precommit()

        if _datalad_msg:
            msg = self._get_prefixed_commit_msg(msg)

        options = options or []

        if not msg:
            if options:
                if "--allow-empty-message" not in options:
                        options.append("--allow-empty-message")
            else:
                options = ["--allow-empty-message"]

        if date:
            options += ["--date", date]
        # Note: We used to use a direct call to git only if there were options,
        # since we can't pass all possible options to gitpython's implementation
        # of commit.
        # But there's an additional issue. GitPython implements commit in a way,
        # that it might create a new commit, when a direct call wouldn't. This
        # was discovered with a modified (but unstaged) submodule, leading to a
        # commit, that apparently did nothing - git status still showed the very
        # same thing afterwards. But a commit was created nevertheless:
        # diff --git a/sub b/sub
        # --- a/sub
        # +++ b/sub
        # @@ -1 +1 @@
        # -Subproject commit d3935338a3b3735792de1078bbfb5e9913ef998f
        # +Subproject commit d3935338a3b3735792de1078bbfb5e9913ef998f-dirty
        #
        # Therefore, for now always use direct call.
        # TODO: Figure out, what exactly is going on with gitpython here

        cmd = ['git', 'commit'] + (["-m", msg if msg else ""])
        if options:
            cmd.extend(options)
        lgr.debug("Committing via direct call of git: %s" % cmd)

        try:
            self._git_custom_command(files, cmd,
                                     expect_stderr=True, expect_fail=True,
                                     check_fake_dates=True,
                                     index_file=index_file)
        except CommandError as e:
            if 'nothing to commit' in e.stdout:
                if careless:
                    lgr.debug(u"nothing to commit in {}. "
                              "Ignored.".format(self))
                else:
                    raise
            elif 'no changes added to commit' in e.stdout or \
                    'nothing added to commit' in e.stdout:
                if careless:
                    lgr.debug(u"no changes added to commit in {}. "
                              "Ignored.".format(self))
                else:
                    raise
            elif "did not match any file(s) known to git" in e.stderr:
                # TODO: Improve FileNotInXXXXError classes to better deal with
                # multiple files; Also consider PathOutsideRepositoryError
                raise FileNotInRepositoryError(cmd=e.cmd,
                                               msg="File(s) unknown to git",
                                               code=e.code,
                                               filename=linesep.join(
                                            [l for l in e.stderr.splitlines()
                                             if l.startswith("pathspec")]))
            else:
                raise

    # TODO usage is primarily in the tests, consider making a test helper and
    # remove from GitRepo API
    def get_indexed_files(self):
        """Get a list of files in git's index

        Returns
        -------
        list
            list of paths rooting in git's base dir
        """

        return [
            str(r.relative_to(self.pathobj))
            for r in self.get_content_info(
                paths=None, ref=None, untracked='no', eval_file_type=False)
        ]

    def format_commit(self, fmt, commitish=None):
        """Return `git show` output for `commitish`.

        Parameters
        ----------
        fmt : str
            A format string accepted by `git show`.
        commitish: str, optional
          Any commit identifier (defaults to "HEAD").

        Returns
        -------
        str or, if there are not commits yet, None.
        """
        cmd = ['git', 'show', '-z', '--no-patch', '--format=' + fmt]
        if commitish is not None:
            cmd.append(commitish + "^{commit}")
        # make sure Git takes our argument as a revision
        cmd.append('--')
        try:
            stdout, stderr = self._git_custom_command(
                '', cmd, expect_stderr=True, expect_fail=True)
        except CommandError as e:
            if 'bad revision' in e.stderr:
                raise ValueError("Unknown commit identifier: %s" % commitish)
            elif 'does not have any commits yet' in e.stderr:
                return None
            else:
                raise e
        # This trailing null is coming from the -z above, which avoids the
        # newline that Git would append to the output. We could drop -z and
        # strip the newline directly, but then we'd have to worry about
        # compatibility across platforms.
        return stdout.rsplit("\0", 1)[0]

    def get_hexsha(self, commitish=None, short=False):
        """Return a hexsha for a given commitish.

        Parameters
        ----------
        commitish : str, optional
          Any identifier that refers to a commit (defaults to "HEAD").
        short : bool, optional
          Return the abbreviated form of the hexsha.

        Returns
        -------
        str or, if there are not commits yet, None.
        """
        stdout = self.format_commit("%{}".format('h' if short else 'H'),
                                    commitish)
        if stdout is not None:
            stdout = stdout.splitlines()
            assert(len(stdout) == 1)
            return stdout[0]

    @normalize_paths(match_return_type=False)
    def get_last_commit_hexsha(self, files):
        """Return the hash of the last commit the modified any of the given
        paths"""
        try:
            commit = self.call_git(
                ['rev-list', '-n1', 'HEAD'],
                files=files,
                expect_fail=True,
            )
            commit = commit.strip()
            return commit if commit else None
        except CommandError:
            if self.get_hexsha() is None:
                # unborn branch, don't freak out
                return None
            raise

    def get_revisions(self, revrange=None, fmt="%H", options=None):
        """Return list of revisions in `revrange`.

        Parameters
        ----------
        revrange : str or list of str or None, optional
            Revisions or revision ranges to walk. If None, revision defaults to
            HEAD unless a revision-modifying option like `--all` or
            `--branches` is included in `options`.
        fmt : string, optional
            Format accepted by `--format` option of `git log`. This should not
            contain new lines because the output is split on new lines.
        options : list of str, optional
            Options to pass to `git log`.  This should not include `--format`.

        Returns
        -------
        List of revisions (str), formatted according to `fmt`.
        """
        if revrange is None:
            revrange = []
        elif isinstance(revrange, str):
            revrange = [revrange]

        cmd = ["git", "log", "--format={}".format(fmt)]
        cmd.extend((options or []) + revrange + ["--"])
        try:
            stdout, _ = self._git_custom_command(None, cmd, expect_fail=True)
        except CommandError as e:
            if "does not have any commits" in e.stderr:
                return []
            raise
        return stdout.splitlines()

    def commit_exists(self, commitish):
        """Does `commitish` exist in the repo?

        Parameters
        ----------
        commitish : str
            A commit or an object that can be dereferenced to one.

        Returns
        -------
        bool
        """
        # Note: The peeling operator "^{commit}" is required so that rev-parse
        # doesn't succeed if passed a full hexsha that is valid but doesn't
        # exist.
        return self.call_git_success(
            ["rev-parse", "--verify", commitish + "^{commit}"])

    def get_merge_base(self, commitishes):
        """Get a merge base hexsha

        Parameters
        ----------
        commitishes: str or list of str
          List of commitishes (branches, hexshas, etc) to determine the merge
          base of. If a single value provided, returns merge_base with the
          current branch.

        Returns
        -------
        str or None
          If no merge-base for given commits, or specified treeish doesn't
          exist, None returned
        """
        if isinstance(commitishes, str):
            commitishes = [commitishes]
        if not commitishes:
            raise ValueError("Provide at least a single value")
        elif len(commitishes) == 1:
            commitishes = commitishes + [self.get_active_branch()]

        try:
            bases = self.repo.merge_base(*commitishes)
        except GitCommandError as exc:
            if "fatal: Not a valid object name" in str(exc):
                return None
            raise

        if not bases:
            return None
        assert(len(bases) == 1)  # we do not do 'all' yet
        return bases[0].hexsha

    def is_ancestor(self, reva, revb):
        """Is `reva` an ancestor of `revb`?

        Parameters
        ----------
        reva, revb : str
            Revisions.

        Returns
        -------
        bool
        """
        return self.call_git_success(
            ["merge-base", "--is-ancestor", reva, revb])

    def get_commit_date(self, branch=None, date='authored'):
        """Get the date stamp of the last commit (in a branch or head otherwise)

        Parameters
        ----------
        date: {'authored', 'committed'}
          Which date to return.  "authored" will be the date shown by "git show"
          and the one possibly specified via --date to `git commit`

        Returns
        -------
        int or None
          None if no commit
        """
        if date == 'committed':
            format = '%ct'
        elif date == 'authored':
            format = '%at'
        else:
            raise ValueError('unknow date type: {}'.format(date))
        d = self.format_commit(format, commitish=branch)
        return int(d) if d else None

    def get_active_branch(self):
        """Get the name of the active branch

        Returns
        -------
        str or None
          Returns None if there is no active branch, i.e. detached HEAD,
          and the branch name otherwise.
        """
        try:
            out, _ = self._git_custom_command(
                "", ["git", "symbolic-ref", "HEAD"],
                expect_fail=True)
        except CommandError as e:
            if 'HEAD is not a symbolic ref' in e.stderr:
                lgr.debug("detached HEAD in {0}".format(self))
                return None
            else:
                raise e
        return out.strip()[11:]  # strip refs/heads/

    def get_branches(self):
        """Get all branches of the repo.

        Returns
        -------
        [str]
            Names of all branches of this repository.
        """

        return [
            b['refname:strip=2']
            for b in self.for_each_ref_(fields='refname:strip=2', pattern='refs/heads')
        ]

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

        return [
            b['refname:strip=2']
            for b in self.for_each_ref_(fields='refname:strip=2', pattern='refs/remotes')
        ]

    def get_remotes(self, with_urls_only=False):
        """Get known remotes of the repository

        Parameters
        ----------
        with_urls_only : bool, optional
          return only remotes which have urls

        Returns
        -------
        remotes : list of str
          List of names of the remotes
        """

        # Note: read directly from config and spare instantiation of gitpy.Repo
        # since we need this in AnnexRepo constructor. Furthermore gitpy does it
        # pretty much the same way and the use of a Repo instance seems to have
        # no reason other than a nice object oriented look.
        from datalad.utils import unique

        self.config.reload()
        remotes = unique([x[7:] for x in self.config.sections()
                          if x.startswith("remote.")])

        if with_urls_only:
            remotes = [
                r for r in remotes
                if self.config.get('remote.%s.url' % r)
            ]
        return remotes

    # TODO this is practically unused outside the tests, consider turning
    # into a test helper and trim from the API
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
        return [
            str(p.relative_to(self.pathobj))
            for p in self.get_content_info(
                paths=None, ref=branch, untracked='no', eval_file_type=False)
            ]

    @normalize_paths(match_return_type=False)
    def _git_custom_command(self, files, cmd_str,
                            log_stdout=True, log_stderr=True, log_online=False,
                            expect_stderr=True, cwd=None, env=None,
                            shell=None, expect_fail=False,
                            check_fake_dates=False,
                            index_file=None,
                            updates_tree=False):
        """Allows for calling arbitrary commands.

        Helper for developing purposes, i.e. to quickly implement git commands
        for proof of concept without the need to figure out, how this is done
        via GitPython.

        Parameters
        ----------
        files: list of files
        cmd_str: str or list
          arbitrary command str. `files` is appended to that string.
        updates_tree: bool
          whether or not command updates the working tree. If True, triggers
          necessary reevaluations like self.config.reload()

        Returns
        -------
        stdout, stderr
        """

        # ensure cmd_str becomes a well-formed list:
        if isinstance(cmd_str, str):
            cmd = shlex.split(cmd_str, posix=not on_windows)
        else:
            cmd = cmd_str[:]  # we will modify in-place

        assert(cmd[0] == 'git')
        cmd = cmd[:1] + self._GIT_COMMON_OPTIONS + cmd[1:]

        if check_fake_dates and self.fake_dates_enabled:
            env = self.add_fake_dates(env)

        if index_file:
            env = (env if env is not None else os.environ).copy()
            env['GIT_INDEX_FILE'] = index_file

        # TODO?: wouldn't splitting interfer with above GIT_INDEX_FILE
        #  handling????
        try:
            out, err = self._run_command_files_split(
                self.cmd_call_wrapper.run,
                cmd,
                files,
                log_stderr=log_stderr,
                log_stdout=log_stdout,
                log_online=log_online,
                expect_stderr=expect_stderr,
                cwd=cwd,
                env=env,
                shell=shell,
                expect_fail=expect_fail)
        except CommandError as e:
            ignored = re.search(GitIgnoreError.pattern, e.stderr)
            if ignored:
                raise GitIgnoreError(cmd=e.cmd, msg=e.stderr,
                                     code=e.code, stdout=e.stdout,
                                     stderr=e.stderr,
                                     paths=ignored.groups()[0].splitlines())
            raise

        if updates_tree:
            lgr.debug("Reloading config due to supposed working tree update")
            self.config.reload()

        return out, err

    # TODO: could be static or class method even
    def _run_command_files_split(
            self,
            func,
            cmd,
            files,
            *args, **kwargs
        ):
        """
        Run `func(cmd + files, ...)` possibly multiple times if `files` is too long
        """
        assert isinstance(cmd, list)
        if not files:
            file_chunks = [[]]
        else:
            file_chunks = generate_file_chunks(files, cmd)

        out, err = "", ""
        for file_chunk in file_chunks:
            out_, err_ = func(
                cmd + (['--'] if file_chunk else []) + file_chunk,
                *args, **kwargs)
            # out_, err_ could be None, and probably no need to append empty strings
            if out_:
                out += out_
            if err_:
                err += err_
        return out, err

    # Convenience wrappers for one-off git calls that don't require further
    # processing or error handling.

    def call_git(self, args, files=None,
                 expect_stderr=False, expect_fail=False):
        """Call git and return standard output.

        Parameters
        ----------
        args : list of str
          Arguments to pass to `git`.
        files : list of str, optional
          File arguments to pass to `git`. The advantage of passing these here
          rather than as part of `args` is that the call will be split into
          multiple calls to avoid exceeding the maximum command line length.
        expect_stderr : bool, optional
          Standard error is expected and should not be elevated above the DEBUG
          level.
        expect_fail : bool, optional
          A non-zero exit is expected and should not be elevated above the
          DEBUG level.

        Returns
        -------
        standard output (str)

        Raises
        ------
        CommandError if the call exits with a non-zero status.
        """
        out, _ = self._git_custom_command(files, ["git"] + args,
                                          expect_stderr=expect_stderr,
                                          expect_fail=expect_fail,
                                          check_fake_dates=True)
        return out

    def call_git_items_(self, args, files=None, expect_stderr=False, sep=None):
        """Call git, splitting output on `sep`.

        Parameters
        ----------
        args : list of str
          Arguments to pass to `git`.
        files : list of str, optional
          File arguments to pass to `git`. The advantage of passing these here
          rather than as part of `args` is that the call will be split into
          multiple calls to avoid exceeding the maximum command line length.
        expect_stderr : bool, optional
          Standard error is expected and should not be elevated above the DEBUG
          level.
        sep : str, optional
          Split the output by `str.split(sep)` rather than `str.splitlines`.

        Returns
        -------
        Generator that yields output items.

        Raises
        ------
        CommandError if the call exits with a non-zero status.
        """
        out, _ = self._git_custom_command(files, ["git"] + args,
                                          expect_stderr=expect_stderr,
                                          check_fake_dates=True)
        yield from (out.split(sep) if sep else out.splitlines())

    def call_git_oneline(self, args, files=None, expect_stderr=False):
        """Call git for a single line of output.

        Parameters
        ----------
        args : list of str
          Arguments to pass to `git`.
        files : list of str, optional
          File arguments to pass to `git`. The advantage of passing these here
          rather than as part of `args` is that the call will be split into
          multiple calls to avoid exceeding the maximum command line length.
        expect_stderr : bool, optional
          Standard error is expected and should not be elevated above the DEBUG
          level.
        sep : str, optional
          Split the output by `str.split(sep)` rather than `str.splitlines`.

        Raises
        ------
        CommandError if the call exits with a non-zero status.
        AssertionError if there is more than one line of output.
        """
        lines = list(self.call_git_items_(args, files=files,
                                          expect_stderr=expect_stderr))
        if len(lines) > 1:
            raise AssertionError(
                "Expected {} to return single line, but it returned {}"
                .format(["git"] + args, lines))
        return lines[0]

    def call_git_success(self, args, files=None, expect_stderr=False):
        """Call git and return true if the call exit code of 0.

        Parameters
        ----------
        args : list of str
          Arguments to pass to `git`.
        files : list of str, optional
          File arguments to pass to `git`. The advantage of passing these here
          rather than as part of `args` is that the call will be split into
          multiple calls to avoid exceeding the maximum command line length.
        expect_stderr : bool, optional
          Standard error is expected and should not be elevated above the DEBUG
          level.

        Returns
        -------
        bool
        """
        try:
            self._git_custom_command(files, ["git"] + args,
                                     expect_fail=True,
                                     expect_stderr=expect_stderr,
                                     check_fake_dates=True)
        except CommandError:
            return False
        return True

    def add_remote(self, name, url, options=None):
        """Register remote pointing to a url
        """
        cmd = ['git', 'remote', 'add']
        if options:
            cmd += options
        cmd += [name, url]

        result = self._git_custom_command('', cmd)
        self.config.reload()
        return result

    def remove_remote(self, name):
        """Remove existing remote
        """

        # TODO: testing and error handling!
        from .exceptions import RemoteNotAvailableError
        try:
            out, err = self._git_custom_command(
                '', ['git', 'remote', 'remove', name])
        except CommandError as e:
            if 'fatal: No such remote' in e.stderr:
                raise RemoteNotAvailableError(name,
                                              cmd="git remote remove",
                                              msg="No such remote",
                                              stdout=e.stdout,
                                              stderr=e.stderr)
            else:
                raise e

        # TODO: config.reload necessary?
        self.config.reload()
        return

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
    @guard_BadName
    def fetch(self, remote=None, refspec=None, all_=False, **kwargs):
        """Fetches changes from a remote (or all remotes).

        Parameters
        ----------
        remote : str, optional
          name of the remote to fetch from. If no remote is given and
          `all_` is not set, the tracking branch is fetched.
        refspec : str, optional
          refspec to fetch.
        all_ : bool, optional
          fetch all remotes (and all of their branches).
          Fails if `remote` was given.
        kwargs :
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
                remotes_to_fetch = [
                    self.repo.remote(r)
                    for r in self.get_remotes(with_urls_only=True)
                ]
            else:
                # No explicit remote to fetch.
                # => get tracking branch:
                tb_remote, refspec = self.get_tracking_branch()
                if tb_remote is not None:
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
                self.config.get('remote.%s.fetchurl' % rm.name,
                                self.config.get('remote.%s.url' % rm.name,
                                                None))
            if fetch_url is None:
                lgr.debug("Remote %s has no URL", rm)
                return []

            fi_list += self._call_gitpy_with_progress(
                "Fetching %s" % rm.name,
                rm.fetch,
                rm.repo,
                refspec,
                fetch_url,
                **kwargs
            )

        # TODO: fetch returns a list of FetchInfo instances. Make use of it.
        return fi_list

    def _call_gitpy_with_progress(self, msg, callable, git_repo,
                                  refspec, url, **kwargs):
        """A helper to reduce code duplication

        Wraps call to a GitPython method with all needed decoration for
        workarounds of having aged git, or not providing full stderr
        when monitoring progress of the operation
        """
        with GitPythonProgressBar(msg) as git_progress:
            git_kwargs = dict(
                refspec=refspec,
                progress=git_progress,
                **kwargs
            )
            if is_ssh(url):
                ssh_manager.get_connection(url).open()
                # TODO: with git <= 2.3 keep old mechanism:
                #       with rm.repo.git.custom_environment(
                # GIT_SSH="wrapper_script"):
                with git_repo.git.custom_environment(**GitRepo.GIT_SSH_ENV):
                    ret = callable(**git_kwargs)
                    # TODO: +kwargs
            else:
                ret = callable(**git_kwargs)
                # TODO: +kwargs
        return ret

    def pull(self, remote=None, refspec=None, **kwargs):
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
            tb_remote, refspec = self.get_tracking_branch()
            if tb_remote is not None:
                remote = self.repo.remote(tb_remote)
            else:
                # No remote, no tracking branch
                # => fail
                raise ValueError("No remote specified to pull from nor a "
                                 "tracking branch is set up.")

        else:
            remote = self.repo.remote(remote)

        fetch_url = \
            remote.config_reader.get(
                'fetchurl' if remote.config_reader.has_option('fetchurl')
                else 'url')

        return self._call_gitpy_with_progress(
                "Pulling",
                remote.pull,
                remote.repo,
                refspec,
                fetch_url,
                **kwargs
            )

    def push(self, remote=None, refspec=None, all_remotes=False,
             **kwargs):
        """Push to remote repository

        Parameters
        ----------
        remote: str
          name of the remote to push to
        refspec: str
          specify what to push
        all_remotes: bool
          if set to True push to all remotes. Conflicts with `remote` not being
          None.
        kwargs: dict
          options to pass to `git push`

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
            if all_remotes:
                remotes_to_push = self.repo.remotes
            else:
                # Nothing explicitly specified. Just call `git push` and let git
                # decide what to do would be an option. But:
                # - without knowing the remote and its URL we cannot provide
                #   shared SSH connection
                # - we lose ability to use GitPython's progress info and return
                #   values
                #   (the latter would be solvable:
                #    Provide a Repo.push() method for GitPython, copying
                #    Remote.push() for similar return value and progress
                #    (also: fetch, pull)

                # Do what git would do:
                # 1. branch.*.remote for current branch or 'origin' as default
                #    if config is missing
                # 2. remote.*.push or push.default

                # TODO: check out "same procedure" for fetch/pull

                tb_remote, refspec = self.get_tracking_branch()
                if tb_remote is None:
                    tb_remote = 'origin'
                remotes_to_push = [self.repo.remote(tb_remote)]
                # use no refspec; let git find remote.*.push or push.default on
                # its own

        else:
            if all_remotes:
                lgr.warning("Option 'all_remotes' conflicts with specified "
                            "remote '%s'. Option ignored.")
            remotes_to_push = [self.repo.remote(remote)]

        pi_list = []
        for rm in remotes_to_push:
            push_url = \
                rm.config_reader.get('pushurl'
                                     if rm.config_reader.has_option('pushurl')
                                     else 'url')
            pi_list += self._call_gitpy_with_progress(
                "Pushing %s" % rm.name,
                rm.push,
                rm.repo,
                refspec,
                push_url,
                **kwargs
            )
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

        var = 'remote.{0}.{1}'.format(name, 'pushurl' if push else 'url')
        return self.config.get(var, None)

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

        var = 'remote.{0}.{1}'.format(name, 'pushurl' if push else 'url')
        self.config.set(var, url, where='local', reload=True)

    def get_branch_commits(self, branch=None, limit=None, stop=None, value=None):
        """Return GitPython's commits for the branch

        Pretty much similar to what 'git log <branch>' does.
        It is a generator which returns top commits first

        Parameters
        ----------
        branch: str, optional
          If not provided, assumes current branch
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

        if not branch:
            branch = self.get_active_branch()

        try:
            _branch = self.repo.branches[branch]
        except IndexError:
            raise MissingBranchError(self, branch,
                                     [b.name for b in self.repo.branches])

        fvalue = {None: lambda x: x, 'hexsha': lambda x: x.hexsha}[value]

        if not limit:
            def gen():
                # traverse doesn't yield original commit
                co = _branch.commit
                yield co
                for co_ in co.traverse():
                    yield co_
        elif limit == 'left-only':
            # we need a custom implementation since couldn't figure out how to
            # do with .traversal
            def gen():
                co = _branch.commit
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

        self._git_custom_command('', cmd, expect_stderr=True, updates_tree=True)

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
            check_fake_dates=True,
            **kwargs
        )

    def remove_branch(self, branch):
        self._git_custom_command(
            '', ['git', 'branch', '-D', branch]
        )

    def cherry_pick(self, commit):
        """Cherry pick `commit` to the current branch.

        Parameters
        ----------
        commit : str
            A single commit.
        """
        self._git_custom_command("", ["git", "cherry-pick", commit],
                                 check_fake_dates=True)

    @property
    def dirty(self):
        """Is the repository dirty?

        Note: This provides a quick answer when you simply want to know if
        there are any untracked changes or modifications in this repository or
        its submodules. For finer-grained control and more detailed reporting,
        use status() instead.
        """
        stdout, _ = self._git_custom_command(
            [],
            ["git", "status", "--porcelain",
             # Ensure the result isn't influenced by status.showUntrackedFiles.
             "--untracked-files=normal",
             # Ensure the result isn't influenced by diff.ignoreSubmodules.
             "--ignore-submodules=none"])
        return bool(stdout.strip())

    @property
    def untracked_files(self):
        """Legacy interface, do not use! Use the status() method instead.

        Despite its name, it also reports on untracked datasets, and
        yields their names with trailing path separators.
        """
        return [
            '{}{}'.format(
                str(p.relative_to(self.pathobj)),
                os.sep if props['type'] != 'file' else ''
            )
            for p, props in self.status(
                    untracked='all', eval_submodule_state='no').items()
            if props.get('state', None) == 'untracked'
        ]

    def gc(self, allow_background=False, auto=False):
        """Perform house keeping (garbage collection, repacking)"""
        cmd_options = ['git']
        if not allow_background:
            cmd_options += ['-c', 'gc.autodetach=0']
        cmd_options += ['gc', '--aggressive']
        if auto:
            cmd_options += ['--auto']
        self._git_custom_command('', cmd_options)

    def _parse_gitmodules(self):
        # TODO read .gitconfig from Git blob?
        gitmodules = self.pathobj / '.gitmodules'
        if not gitmodules.exists():
            return {}
        # pull out file content
        out, err = self._git_custom_command(
            '',
            ['git', 'config', '-z', '-l', '--file', '.gitmodules'])
        # abuse our config parser
        db, _ = _parse_gitconfig_dump(out, {}, None, True)
        mods = {}
        for k, v in db.items():
            if not k.startswith('submodule.'):
                # we don't know what this is
                lgr.warning("Skip unrecognized .gitmodule specification: %s=%s", k, v)
                continue
            k_l = k.split('.')
            # module name is everything after 'submodule.' that is not the variable
            # name
            mod_name = '.'.join(k_l[1:-1])
            mod = mods.get(mod_name, {})
            # variable name is the last 'dot-free' segment in the key
            mod[k_l[-1]] = v
            mods[mod_name] = mod

        out = {}
        # bring into traditional shape
        for name, props in mods.items():
            if 'path' not in props:
                lgr.warning("Failed to get '%s.path', skipping this submodule", name)
                continue
            modprops = {'gitmodule_{}'.format(k): v
                        for k, v in props.items()
                        if not (k.startswith('__') or k == 'path')}
            modpath = self.pathobj / PurePosixPath(props['path'])
            modprops['gitmodule_name'] = name
            out[modpath] = modprops
        return out

    def get_submodules_(self, paths=None):
        """Yield submodules in this repository.

        Parameters
        ----------
        paths : list(pathlib.PurePath), optional
            Restrict submodules to those under `paths`.

        Returns
        -------
        A generator that yields a dictionary with information for each
        submodule.
        """
        if not (self.pathobj / ".gitmodules").exists():
            return

        modinfo = self._parse_gitmodules()
        for path, props in self.get_content_info(
                paths=paths,
                ref=None,
                untracked='no',
                eval_file_type=False).items():
            if props.get('type', None) != 'dataset':
                continue
            props["path"] = path
            props.update(modinfo.get(path, {}))
            yield props

    def get_submodules(self, sorted_=True, paths=None, compat=True):
        """Return list of submodules.

        Parameters
        ----------
        sorted_ : bool, optional
            Sort submodules by path name.
        paths : list(pathlib.PurePath), optional
            Restrict submodules to those under `paths`.
        compat : bool, optional
            If true, return a namedtuple that incompletely mimics the
            attributes of GitPython's Submodule object in hope of backwards
            compatibility with previous callers. Note that this form should be
            considered temporary and callers should be updated; this flag will
            be removed in a future release.

        Returns
        -------
        List of submodule namedtuples if `compat` is true or otherwise a list
        of dictionaries as returned by `get_submodules_`.
        """
        xs = self.get_submodules_(paths=paths)
        if compat:
            warnings.warn("The attribute-based return value of get_submodules() "
                          "exists for compatibility purposes and will be removed "
                          "in an upcoming release",
                          DeprecationWarning)
            xs = (Submodule(name=p["gitmodule_name"],
                            path=str(p["path"].relative_to(self.pathobj)),
                            url=p["gitmodule_url"])
                  for p in xs)

        if sorted_:
            if compat:
                def key(x):
                    return x.path
            else:
                def key(x):
                    return x["path"]
            xs = sorted(xs, key=key)
        return list(xs)

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
            name = Path(path).as_posix()
        # XXX the following should do it, but GitPython will refuse to add a submodule
        # unless you specify a URL that is configured as one of its remotes, or you
        # specify no URL, but the repo has at least one remote.
        # this is stupid, as for us it is valid to not have any remote, because we can
        # still obtain the submodule from a future publication location, based on the
        # parent
        # gitpy.Submodule.add(self.repo, name, path, url=url, branch=branch)
        # going git native instead
        cmd = ['submodule', 'add', '--name', name]
        if branch is not None:
            cmd += ['-b', branch]
        if url is None:
            # repo must already exist locally
            subm = GitRepo(op.join(self.path, path), create=False, init=False)
            # check that it has a commit, and refuse
            # to operate on it otherwise, or we would get a bastard
            # submodule that cripples git operations
            if not subm.get_hexsha():
                raise InvalidGitRepositoryError(
                    'cannot add subdataset {} with no commits'.format(subm))
            # make an attempt to configure a submodule source URL based on the
            # discovered remote configuration
            remote, branch = subm.get_tracking_branch()
            url = subm.get_remote_url(remote) if remote else None

        if url is None:
            # had no luck with a remote URL
            if not isabs(path):
                # need to recode into a relative path "URL" in POSIX
                # style, even on windows
                url = posixpath.join(curdir, posix_relpath(path))
            else:
                url = path
        cmd += [url, Path(path).as_posix()]
        self.call_git(cmd)
        # record dataset ID if possible for comprehesive metadata on
        # dataset components within the dataset itself
        subm_id = GitRepo(op.join(self.path, path)).config.get(
            'datalad.dataset.id', None)
        if subm_id:
            self.call_git(
                ['config', '--file', '.gitmodules', '--replace-all',
                 'submodule.{}.datalad-id'.format(name), subm_id])
        # ensure supported setup
        _fixup_submodule_dotgit_setup(self, path)
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

        self._git_custom_command(path,
                                 ['git', 'submodule', 'deinit'] +
                                 to_options(**kwargs))
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
          Primarily provided for internal purposes and should not be used directly
          since would result in not so annex-friendly .git symlinks/references
          instead of full featured .git/ directories in the submodules
        """
        if GitRepo.is_valid_repo(self.pathobj / path):
            subrepo = GitRepo(self.pathobj / path, create=False)
            subbranch = subrepo.get_active_branch() if subrepo else None
            subbranch_hexsha = subrepo.get_hexsha(subbranch) if subrepo else None
        else:
            subrepo = None
            subbranch = None
            subbranch_hexsha = None

        cmd = ['git', 'submodule', 'update', '--%s' % mode]
        if init:
            cmd.append('--init')
            subgitpath = opj(self.path, path, '.git')
            if not exists(subgitpath):
                # TODO:  wouldn't with --init we get all those symlink'ed .git/?
                # At least let's warn
                lgr.warning(
                    "Do not use update_submodule with init=True to avoid git creating "
                    "symlinked .git/ directories in submodules"
                )
            #  yoh: I thought I saw one recently but thought it was some kind of
            #  an artifact from running submodule update --init manually at
            #  some point, but looking at this code now I worry that it was not
        self._git_custom_command(path, cmd)

        if not init:
            return

        # track branch originally cloned, only if we had a valid repo at the start
        updated_subbranch = subrepo.get_active_branch() if subrepo else None
        if subbranch and not updated_subbranch:
            # got into 'detached' mode
            # trace if current state is a predecessor of the branch_hexsha
            lgr.debug(
                "Detected detached HEAD after updating submodule %s which was "
                "in %s branch before", self.path, subbranch)
            detached_hexsha = subrepo.get_hexsha()
            if subrepo.get_merge_base(
                    [subbranch_hexsha, detached_hexsha]) == detached_hexsha:
                # TODO: config option?
                # in all likely event it is of the same branch since
                # it is an ancestor -- so we could update that original branch
                # to point to the state desired by the submodule, and update
                # HEAD to point to that location
                lgr.info(
                    "Submodule HEAD got detached. Resetting branch %s to point "
                    "to %s. Original location was %s",
                    subbranch, detached_hexsha[:8], subbranch_hexsha[:8]
                )
                branch_ref = 'refs/heads/%s' % subbranch
                subrepo.update_ref(branch_ref, detached_hexsha)
                assert(subrepo.get_hexsha(subbranch) == detached_hexsha)
                subrepo.update_ref('HEAD', branch_ref, symbolic=True)
                assert(subrepo.get_active_branch() == subbranch)
            else:
                lgr.warning(
                    "%s has a detached HEAD since cloned branch %s has another common ancestor with %s",
                    subrepo.path, subbranch, detached_hexsha[:8]
                )
        # TODO: return value

    def update_ref(self, ref, value, symbolic=False):
        """Update the object name stored in a ref "safely".

        Just a shim for `git update-ref` call if not symbolic, and
        `git symbolic-ref` if symbolic

        Parameters
        ----------
        ref : str
          Reference, such as `ref/heads/BRANCHNAME` or HEAD.
        value : str
          Value to update to, e.g. hexsha of a commit when updating for a
          branch ref, or branch ref if updating HEAD
        symbolic : None
          To instruct if ref is symbolic, e.g. should be used in case of
          ref=HEAD
        """
        self._git_custom_command(
            '',
            ['git', 'symbolic-ref' if symbolic else 'update-ref', ref, value]
        )

    def tag(self, tag, message=None, commit=None, options=None):
        """Tag a commit

        Parameters
        ----------
        tag : str
          Custom tag label. Must be a valid tag name.
        message : str, optional
          If provided, adds ['-m', <message>] to the list of `git tag`
          arguments.
        commit : str, optional
          If provided, will be appended as last argument to the `git tag` call,
          and can be used to identify the commit that shall be tagged, if
          not HEAD.
        options : list, optional
          Additional command options, inserted prior a potential `commit`
          argument.
        """
        # TODO: call in save.py complains about extensive logging. When does it
        # happen in what way? Figure out, whether to just silence it or raise or
        # whatever else.
        args = ['tag']
        if message:
            args += ['-m', message]
        if options is not None:
            args.extend(options)
        args.append(tag)
        if commit:
            args.append(commit)
        self.call_git(args)

    def get_tags(self, output=None):
        """Get list of tags

        Parameters
        ----------
        output : str, optional
          If given, limit the return value to a list of values matching that
          particular key of the tag properties.

        Returns
        -------
        list
          Each item is a dictionary with information on a tag. At present
          this includes 'hexsha', and 'name', where the latter is the string
          label of the tag, and the former the hexsha of the object the tag
          is attached to. The list is sorted by the creator date (committer
          date for lightweight tags and tagger date for annotated tags), with
          the most recent commit being the last element.
        """
        tags = [
            dict(
                name=t['refname:strip=2'],
                hexsha=t['object'] if t['object'] else t['objectname'],
            )
            for t in self.for_each_ref_(
                fields=['refname:strip=2', 'objectname', 'object'],
                pattern='refs/tags',
                sort='creatordate')
        ]
        if output:
            return [t[output] for t in tags]
        else:
            return tags

    def describe(self, commitish=None, **kwargs):
        """ Quick and dirty implementation to call git-describe

        Parameters
        ----------
        kwargs:
            transformed to cmdline options for git-describe;
            see __init__ for description of the transformation
        """
        # TODO: be more precise what failure to expect when and raise actual
        # errors
        cmd = ['git', 'describe'] + to_options(**kwargs)
        if commitish is not None:
            cmd.append(commitish)
        try:
            describe, outerr = self._git_custom_command(
                [],
                cmd,
                expect_fail=True)
            return describe.strip()
        # TODO: WTF "catch everything"?
        except:
            return None

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
            if branch is None:
                return None, None

        track_remote = self.config.get('branch.{0}.remote'.format(branch), None)
        track_branch = self.config.get('branch.{0}.merge'.format(branch), None)
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

    def get_changed_files(self, staged=False, diff_filter='', index_file=None,
                          files=None):
        """Return files that have changed between the index and working tree.

        Parameters
        ----------
        staged: bool, optional
          Consider changes between HEAD and the index instead of changes
          between the index and the working tree.
        diff_filter: str, optional
          Any value accepted by the `--diff-filter` option of `git diff`.
          Common ones include "A", "D", "M" for add, deleted, and modified
          files, respectively.
        index_file: str, optional
          Alternative index file for git to use
        """
        opts = ['--name-only', '-z']
        kwargs = {}
        if staged:
            opts.append('--staged')
        if diff_filter:
            opts.append('--diff-filter=%s' % diff_filter)
        if index_file:
            kwargs['env'] = {'GIT_INDEX_FILE': index_file}
        if files is not None:
            opts.append('--')
            # might be too many, need to chunk up
            optss = (
                opts + file_chunk
                for file_chunk in generate_file_chunks(files, ['git', 'diff'] + opts)
            )
        else:
            optss = [opts]
        return [
            normpath(f)  # Call normpath to convert separators on Windows.
            for f in chain(
                *(self.repo.git.diff(*opts, **kwargs).split('\0')
                for opts in optss)
            )
            if f
        ]

    def get_missing_files(self):
        """Return a list of paths with missing files (and no staged deletion)"""
        return self.get_changed_files(diff_filter='D')

    def get_deleted_files(self):
        """Return a list of paths with deleted files (staged deletion)"""
        return self.get_changed_files(staged=True, diff_filter='D')

    def get_git_attributes(self):
        """Query gitattributes which apply to top level directory

        It is a thin compatibility/shortcut wrapper around more versatile
        get_gitattributes which operates on a list of paths and returns
        a dictionary per each path

        Returns
        -------
        dict:
          a dictionary with attribute name and value items relevant for the
          top ('.') directory of the repository, and thus most likely the
          default ones (if not overwritten with more rules) for all files within
          repo.
        """
        return self.get_gitattributes('.')['.']

    def get_gitattributes(self, path, index_only=False):
        """Query gitattributes for one or more paths

        Parameters
        ----------
        path: path or list
          Path(s) to query. Paths may be relative or absolute.
        index_only: bool
          Flag whether to consider only gitattribute setting that are reflected
          in the repository index, not just in the work tree content.

        Returns
        -------
        dict:
          Each key is a queried path (always relative to the repostiory root),
          each value is a dictionary with attribute
          name and value items. Attribute values are either True or False,
          for set and unset attributes, or are the literal attribute value.
        """
        path = assure_list(path)
        cmd = ["git", "check-attr", "-z", "--all"]
        if index_only:
            cmd.append('--cached')
        stdout, stderr = self._git_custom_command(path, cmd)
        # make sure we have one entry for each query path to
        # simplify work with the result
        attributes = {_normalize_path(self.path, p): {} for p in path}
        attr = []
        for item in stdout.split('\0'):
            attr.append(item)
            if len(attr) < 3:
                continue
            # we have a full record
            p, name, value = attr
            attrs = attributes[p]
            attrs[name] = \
                True if value == 'set' else False if value == 'unset' else value
            # done, reset item
            attr = []
        return attributes

    def set_gitattributes(self, attrs, attrfile='.gitattributes', mode='a'):
        """Set gitattributes

        By default appends additional lines to `attrfile`. Note, that later
        lines in `attrfile` overrule earlier ones, which may or may not be
        what you want. Set `mode` to 'w' to replace the entire file by
        what you provided in `attrs`.

        Parameters
        ----------
        attrs : list
          Each item is a 2-tuple, where the first element is a path pattern,
          and the second element is a dictionary with attribute key/value
          pairs. The attribute dictionary must use the same semantics as those
          returned by `get_gitattributes()`. Path patterns can use absolute paths,
          in which case they will be normalized relative to the directory
          that contains the target .gitattributes file (see `attrfile`).
        attrfile: path
          Path relative to the repository root of the .gitattributes file the
          attributes shall be set in.
        mode: str
          'a' to append .gitattributes, 'w' to replace it
        """

        git_attributes_file = op.join(self.path, attrfile)
        attrdir = op.dirname(git_attributes_file)
        if not op.exists(attrdir):
            os.makedirs(attrdir)
        with open(git_attributes_file, mode) as f:
            for pattern, attr in sorted(attrs, key=lambda x: x[0]):
                # normalize the pattern relative to the target .gitattributes file
                npath = _normalize_path(
                    op.join(self.path, op.dirname(attrfile)), pattern)
                # paths in gitattributes always have to be POSIX
                npath = Path(npath).as_posix()
                attrline = u''
                if npath.count(' '):
                    # quote patterns with spaces
                    attrline += u'"{}"'.format(npath.replace('"', '\\"'))
                else:
                    attrline += npath
                for a in sorted(attr):
                    val = attr[a]
                    if val is True:
                        attrline += ' {}'.format(a)
                    elif val is False:
                        attrline += ' -{}'.format(a)
                    else:
                        attrline += ' {}={}'.format(a, val)
                f.write('\n{}'.format(attrline))

    def get_content_info(self, paths=None, ref=None, untracked='all',
                         eval_file_type=True):
        """Get identifier and type information from repository content.

        This is simplified front-end for `git ls-files/tree`.

        Both commands differ in their behavior when queried about subdataset
        paths. ls-files will not report anything, ls-tree will report on the
        subdataset record. This function uniformly follows the behavior of
        ls-tree (report on the respective subdataset mount).

        Parameters
        ----------
        paths : list(pathlib.PurePath)
          Specific paths, relative to the resolved repository root, to query
          info for. Paths must be normed to match the reporting done by Git,
          i.e. no parent dir components (ala "some/../this").
          If none are given, info is reported for all content.
        ref : gitref or None
          If given, content information is retrieved for this Git reference
          (via ls-tree), otherwise content information is produced for the
          present work tree (via ls-files). With a given reference, the
          reported content properties also contain a 'bytesize' record,
          stating the size of a file in bytes.
        untracked : {'no', 'normal', 'all'}
          If and how untracked content is reported when no `ref` was given:
          'no': no untracked files are reported; 'normal': untracked files
          and entire untracked directories are reported as such; 'all': report
          individual files even in fully untracked directories.
        eval_file_type : bool
          If True, inspect file type of untracked files, and report annex
          symlink pointers as type 'file'. This convenience comes with a
          cost; disable to get faster performance if this information
          is not needed.

        Returns
        -------
        dict
          Each content item has an entry under a pathlib `Path` object instance
          pointing to its absolute path inside the repository (this path is
          guaranteed to be underneath `Repo.path`).
          Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'

            Note that the reported type will not always match the type of
            content committed to Git, rather it will reflect the nature
            of the content minus platform/mode-specifics. For example,
            a symlink to a locked annexed file on Unix will have a type
            'file', reported, while a symlink to a file in Git or directory
            will be of type 'symlink'.

          `gitshasum`
            SHASUM of the item as tracked by Git, or None, if not
            tracked. This could be different from the SHASUM of the file
            in the worktree, if it was modified.

        Raises
        ------
        ValueError
          In case of an invalid Git reference (e.g. 'HEAD' in an empty
          repository)
        """
        lgr.debug('%s.get_content_info(...)', self)
        # TODO limit by file type to replace code in subdatasets command
        info = OrderedDict()

        if paths:
            # path matching will happen against what Git reports
            # and Git always reports POSIX paths
            # any incoming path has to be relative already, so we can simply
            # convert unconditionally
            paths = [ut.PurePosixPath(p) for p in paths]

        path_strs = list(map(str, paths)) if paths else None

        # this will not work in direct mode, but everything else should be
        # just fine
        if not ref:
            # make sure no operations are pending before we figure things
            # out in the worktree
            self.precommit()

            # --exclude-standard will make sure to honor and standard way
            # git can be instructed to ignore content, and will prevent
            # crap from contaminating untracked file reports
            cmd = ['git', 'ls-files',
                   '--stage', '-z', '-d', '-m', '--exclude-standard']
            # untracked report mode, using labels from `git diff` option style
            if untracked == 'all':
                cmd.append('-o')
            elif untracked == 'normal':
                cmd += ['-o', '--directory', '--no-empty-directory']
            elif untracked == 'no':
                pass
            else:
                raise ValueError(
                    'unknown value for `untracked`: {}'.format(untracked))
            props_re = re.compile(
                r'(?P<type>[0-9]+) (?P<sha>.*) (.*)\t(?P<fname>.*)$')

            if path_strs:
                # we need to get their within repo elements since ls-tree
                # for paths within submodules returns nothing!
                # see https://public-inbox.org/git/20190703193305.GF21553@hopa.kiewit.dartmouth.edu/T/#u
                submodules = [s.path for s in self.get_submodules()]
                path_strs = get_parent_paths(path_strs, submodules)
        else:
            cmd = ['git', 'ls-tree', ref, '-z', '-r', '--full-tree', '-l']
            props_re = re.compile(
                r'(?P<type>[0-9]+) ([a-z]*) (?P<sha>[^ ]*) [\s]*(?P<size>[0-9-]+)\t(?P<fname>.*)$')

        lgr.debug('Query repo: %s', cmd)
        try:
            stdout, stderr = self._git_custom_command(
                path_strs,
                cmd,
                log_stderr=True,
                log_stdout=True,
                # not sure why exactly, but log_online has to be false!
                log_online=False,
                expect_stderr=False,
                shell=False,
                # we don't want it to scream on stdout
                expect_fail=True)
        except CommandError as exc:
            if "fatal: Not a valid object name" in str(exc):
                raise InvalidGitReferenceError(ref)
            raise
        lgr.debug('Done query repo: %s', cmd)

        if not eval_file_type:
            _get_link_target = None
        elif ref:
            def _read_symlink_target_from_catfile(lines):
                # it is always the second line, all checks done upfront
                header = lines.readline()
                if header.rstrip().endswith('missing'):
                    # something we do not know about, should not happen
                    # in real use, but guard against to avoid stalling
                    return ''
                return lines.readline().rstrip()

            _get_link_target = BatchedCommand(
                ['git', 'cat-file', '--batch'],
                path=self.path,
                output_proc=_read_symlink_target_from_catfile,
            )
        else:
            def try_readlink(path):
                try:
                    return os.readlink(path)
                except OSError:
                    # readlink will fail if the symlink reported by ls-files is
                    # not in the working tree (it could be removed or
                    # unlocked). Fall back to a slower method.
                    return op.realpath(path)

            _get_link_target = try_readlink

        try:
            self._get_content_info_line_helper(
                ref,
                info,
                stdout.split('\0'),
                props_re,
                _get_link_target)
        finally:
            if ref and _get_link_target:
                # cancel batch process
                _get_link_target.close()

        lgr.debug('Done %s.get_content_info(...)', self)
        return info

    def _get_content_info_line_helper(self, ref, info, lines,
                                      props_re, get_link_target):
        """Internal helper of get_content_info() to parse Git output"""
        mode_type_map = {
            '100644': 'file',
            '100755': 'file',
            '120000': 'symlink',
            '160000': 'dataset',
        }
        for line in lines:
            if not line:
                continue
            inf = {}
            props = props_re.match(line)
            if not props:
                # not known to Git, but Git always reports POSIX
                path = ut.PurePosixPath(line)
                inf['gitshasum'] = None
            else:
                # again Git reports always in POSIX
                path = ut.PurePosixPath(props.group('fname'))

            # revisit the file props after this path has not been rejected
            if props:
                inf['gitshasum'] = props.group('sha')
                inf['type'] = mode_type_map.get(
                    props.group('type'), props.group('type'))
                if get_link_target and inf['type'] == 'symlink' and \
                        ((ref is None and '.git/annex/objects' in \
                          ut.Path(
                            get_link_target(str(self.pathobj / path))
                          ).as_posix()) or \
                         (ref and \
                          '.git/annex/objects' in get_link_target(
                              u'{}:{}'.format(
                                  ref, str(path))))
                        ):
                    # report annex symlink pointers as file, their
                    # symlink-nature is a technicality that is dependent
                    # on the particular mode annex is in
                    inf['type'] = 'file'

                if ref and inf['type'] == 'file':
                    inf['bytesize'] = int(props.group('size'))

            # join item path with repo path to get a universally useful
            # path representation with auto-conversion and tons of other
            # stuff
            path = self.pathobj.joinpath(path)
            if 'type' not in inf:
                # be nice and assign types for untracked content
                inf['type'] = 'symlink' if path.is_symlink() \
                    else 'directory' if path.is_dir() else 'file'
            info[path] = inf

    def status(self, paths=None, untracked='all', eval_submodule_state='full'):
        """Simplified `git status` equivalent.

        Parameters
        ----------
        paths : list or None
          If given, limits the query to the specified paths. To query all
          paths specify `None`, not an empty list. If a query path points
          into a subdataset, a report is made on the subdataset record
          within the queried dataset only (no recursion).
        untracked : {'no', 'normal', 'all'}
          If and how untracked content is reported:
          'no': no untracked files are reported; 'normal': untracked files
          and entire untracked directories are reported as such; 'all': report
          individual files even in fully untracked directories.
        eval_submodule_state : {'full', 'commit', 'no'}
          If 'full' (the default), the state of a submodule is evaluated by
          considering all modifications, with the treatment of untracked files
          determined by `untracked`. If 'commit', the modification check is
          restricted to comparing the submodule's HEAD commit to the one
          recorded in the superdataset. If 'no', the state of the subdataset is
          not evaluated.

        Returns
        -------
        dict
          Each content item has an entry under a pathlib `Path` object instance
          pointing to its absolute path inside the repository (this path is
          guaranteed to be underneath `Repo.path`).
          Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'
          `state`
            Can be 'added', 'untracked', 'clean', 'deleted', 'modified'.
        """
        lgr.debug('Query status of %r for %s paths',
                  self, len(paths) if paths else 'all')
        return self.diffstatus(
            fr='HEAD' if self.get_hexsha() else None,
            to=None,
            paths=paths,
            untracked=untracked,
            eval_submodule_state=eval_submodule_state)

    def diff(self, fr, to, paths=None, untracked='all',
             eval_submodule_state='full'):
        """Like status(), but reports changes between to arbitrary revisions

        Parameters
        ----------
        fr : str or None
          Revision specification (anything that Git understands). Passing
          `None` considers anything in the target state as new.
        to : str or None
          Revision specification (anything that Git understands), or None
          to compare to the state of the work tree.
        paths : list or None
          If given, limits the query to the specified paths. To query all
          paths specify `None`, not an empty list.
        untracked : {'no', 'normal', 'all'}
          If and how untracked content is reported when `to` is None:
          'no': no untracked files are reported; 'normal': untracked files
          and entire untracked directories are reported as such; 'all': report
          individual files even in fully untracked directories.
        eval_submodule_state : {'full', 'commit', 'no'}
          If 'full' (the default), the state of a submodule is evaluated by
          considering all modifications, with the treatment of untracked files
          determined by `untracked`. If 'commit', the modification check is
          restricted to comparing the submodule's HEAD commit to the one
          recorded in the superdataset. If 'no', the state of the subdataset is
          not evaluated.

        Returns
        -------
        dict
          Each content item has an entry under a pathlib `Path` object instance
          pointing to its absolute path inside the repository (this path is
          guaranteed to be underneath `Repo.path`).
          Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'
          `state`
            Can be 'added', 'untracked', 'clean', 'deleted', 'modified'.
        """
        return {k: v for k, v in self.diffstatus(
            fr=fr, to=to, paths=paths,
            untracked=untracked,
            eval_submodule_state=eval_submodule_state).items()
            if v.get('state', None) != 'clean'}

    def diffstatus(self, fr, to, paths=None, untracked='all',
                   eval_submodule_state='full', eval_file_type=True,
                   _cache=None):
        """Like diff(), but reports the status of 'clean' content too"""
        return self._diffstatus(
            fr, to, paths, untracked, eval_submodule_state, eval_file_type,
            _cache)

    def _diffstatus(self, fr, to, paths, untracked, eval_state,
                    eval_file_type, _cache):
        """Just like diffstatus(), but supports an additional evaluation
        state 'global'. If given, it will return a single 'modified'
        (vs. 'clean') state label for the entire repository, as soon as
        it can."""
        def _get_cache_key(label, paths, ref, untracked=None):
            return self.path, label, tuple(paths) if paths else None, \
                ref, untracked

        if _cache is None:
            _cache = {}

        if paths:
            # at this point we must normalize paths to the form that
            # Git would report them, to easy matching later on
            paths = [ut.Path(p) for p in paths]
            paths = [
                p.relative_to(self.pathobj) if p.is_absolute() else p
                for p in paths
            ]

        # TODO report more info from get_content_info() calls in return
        # value, those are cheap and possibly useful to a consumer
        # we need (at most) three calls to git
        if to is None:
            # everything we know about the worktree, including os.stat
            # for each file
            key = _get_cache_key('ci', paths, None, untracked)
            if key in _cache:
                to_state = _cache[key]
            else:
                to_state = self.get_content_info(
                    paths=paths, ref=None, untracked=untracked,
                    eval_file_type=eval_file_type)
                _cache[key] = to_state
            # we want Git to tell us what it considers modified and avoid
            # reimplementing logic ourselves
            key = _get_cache_key('mod', paths, None)
            if key in _cache:
                modified = _cache[key]
            else:
                modified = set(
                    self.pathobj.joinpath(ut.PurePosixPath(p))
                    for p in self._git_custom_command(
                        # low-level code cannot handle pathobjs
                        [str(p) for p in paths] if paths else None,
                        ['git', 'ls-files', '-z', '-m'])[0].split('\0')
                    if p)
                _cache[key] = modified
        else:
            key = _get_cache_key('ci', paths, to)
            if key in _cache:
                to_state = _cache[key]
            else:
                to_state = self.get_content_info(
                    paths=paths, ref=to, eval_file_type=eval_file_type)
                _cache[key] = to_state
            # we do not need worktree modification detection in this case
            modified = None
        # origin state
        key = _get_cache_key('ci', paths, fr)
        if key in _cache:
            from_state = _cache[key]
        else:
            if fr:
                from_state = self.get_content_info(
                    paths=paths, ref=fr, eval_file_type=eval_file_type)
            else:
                # no ref means from nothing
                from_state = {}
            _cache[key] = from_state

        status = OrderedDict()
        for f, to_state_r in to_state.items():
            props = None
            if f not in from_state:
                # this is new, or rather not known to the previous state
                props = dict(
                    state='added' if to_state_r['gitshasum'] else 'untracked',
                )
                if 'type' in to_state_r:
                    props['type'] = to_state_r['type']
            elif to_state_r['gitshasum'] == from_state[f]['gitshasum'] and \
                    (modified is None or f not in modified):
                if to_state_r['type'] != 'dataset':
                    # no change in git record, and no change on disk
                    props = dict(
                        # at this point we know that the reported object ids
                        # for this file are identical in the to and from
                        # records.  If to is None, we're comparing to the
                        # working tree and a deleted file will still have an
                        # identical id, so we need to check whether the file is
                        # gone before declaring it clean. This working tree
                        # check is irrelevant and wrong if to is a ref.
                        state='clean' if to is not None or (f.exists() or \
                              f.is_symlink()) else 'deleted',
                        type=to_state_r['type'],
                    )
                else:
                    # a dataset
                    props = dict(type=to_state_r['type'])
                    if to is not None:
                        # we can only be confident without looking
                        # at the worktree, if we compare to a recorded
                        # state
                        props['state'] = 'clean'
                    else:
                        # report the shasum that we know, for further
                        # wrangling of subdatasets below
                        props['gitshasum'] = to_state_r['gitshasum']
                        props['prev_gitshasum'] = from_state[f]['gitshasum']
            else:
                # change in git record, or on disk
                props = dict(
                    # TODO we could have a new file that is already staged
                    # but had subsequent modifications done to it that are
                    # unstaged. Such file would presently show up as 'added'
                    # ATM I think this is OK, but worth stating...
                    state='modified' if f.exists() or \
                    f.is_symlink() else 'deleted',
                    # TODO record before and after state for diff-like use
                    # cases
                    type=to_state_r['type'],
                )
            state = props.get('state', None)
            if eval_state == 'global' and \
                    state not in ('clean', None):
                # any modification means globally 'modified'
                return 'modified'
            if state in ('clean', 'added', 'modified'):
                props['gitshasum'] = to_state_r['gitshasum']
                if 'bytesize' in to_state_r:
                    # if we got this cheap, report it
                    props['bytesize'] = to_state_r['bytesize']
                elif props['state'] == 'clean' and 'bytesize' in from_state[f]:
                    # no change, we can take this old size info
                    props['bytesize'] = from_state[f]['bytesize']
            if state in ('clean', 'modified', 'deleted'):
                props['prev_gitshasum'] = from_state[f]['gitshasum']
            status[f] = props

        for f, from_state_r in from_state.items():
            if f not in to_state:
                # we new this, but now it is gone and Git is not complaining
                # about it being missing -> properly deleted and deletion
                # stages
                status[f] = dict(
                    state='deleted',
                    type=from_state_r['type'],
                    # report the shasum to distinguish from a plainly vanished
                    # file
                    gitshasum=from_state_r['gitshasum'],
                )
                if eval_state == 'global':
                    return 'modified'

        if to is not None or eval_state == 'no':
            # if we have `to` we are specifically comparing against
            # a recorded state, and this function only attempts
            # to label the state of a subdataset, not investigate
            # specifically what the changes in subdatasets are
            # this is done by a high-level command like rev-diff
            # so the comparison within this repo and the present
            # `state` label are all we need, and they are done already
            if eval_state == 'global':
                return 'clean'
            else:
                return status

        # loop over all subdatasets and look for additional modifications
        for f, st in status.items():
            f = str(f)
            if 'state' in st or not st['type'] == 'dataset':
                # no business here
                continue
            if not GitRepo.is_valid_repo(f):
                # submodule is not present, no chance for a conflict
                st['state'] = 'clean'
                continue
            # we have to recurse into the dataset and get its status
            subrepo = GitRepo(f)
            subrepo_commit = subrepo.get_hexsha()
            st['gitshasum'] = subrepo_commit
            # subdataset records must be labeled clean up to this point
            # test if current commit in subdataset deviates from what is
            # recorded in the dataset
            st['state'] = 'modified' \
                if st['prev_gitshasum'] != subrepo_commit \
                else 'clean'
            if eval_state == 'global' and st['state'] == 'modified':
                return 'modified'
            if eval_state == 'commit':
                continue
            # the recorded commit did not change, so we need to make
            # a more expensive traversal
            st['state'] = subrepo._diffstatus(
                # we can use 'HEAD' because we know that the commit
                # did not change. using 'HEAD' will facilitate
                # caching the result
                fr='HEAD',
                to=None,
                paths=None,
                untracked=untracked,
                eval_state='global',
                eval_file_type=False,
                _cache=_cache) if st['state'] == 'clean' else 'modified'
            if eval_state == 'global' and st['state'] == 'modified':
                return 'modified'

        if eval_state == 'global':
            return 'clean'
        else:
            return status

    def _save_pre(self, paths, _status, **kwargs):
        # helper to get an actionable status report
        if paths is not None and not paths and not _status:
            return
        if _status is None:
            if 'untracked' not in kwargs:
                kwargs['untracked'] = 'normal'
            status = self.status(
                paths=paths,
                **{k: kwargs[k] for k in kwargs
                   if k in ('untracked', 'eval_submodule_state')})
        else:
            # we want to be able to add items down the line
            # make sure to detach from prev. owner
            status = _status.copy()
        status = OrderedDict(
            (k, v) for k, v in status.items()
            if v.get('state', None) != 'clean'
        )
        return status

    def get_staged_paths(self):
        """Returns a list of any stage repository path(s)

        This is a rather fast call, as it will not depend on what is going on
        in the worktree.
        """
        try:
            stdout, stderr = self._git_custom_command(
                None,
                ['git', 'diff', '--name-only', '--staged'],
                cwd=self.path,
                log_stderr=True,
                log_stdout=True,
                log_online=False,
                expect_stderr=False,
                expect_fail=True)
        except CommandError as e:
            lgr.debug(exc_str(e))
            stdout = ''
        return [f for f in stdout.split('\n') if f]

    def _save_post(self, message, status, partial_commit):
        # helper to commit changes reported in status
        _datalad_msg = False
        if not message:
            message = 'Recorded changes'
            _datalad_msg = True

        # TODO remove pathobj stringification when commit() can
        # handle it
        to_commit = [str(f.relative_to(self.pathobj))
                     for f, props in status.items()] \
                    if partial_commit else None
        if not partial_commit or to_commit:
            # we directly call GitRepo.commit() to avoid a whole slew
            # if direct-mode safeguards and workarounds in the AnnexRepo
            # implementation (which also run an additional dry-run commit
            GitRepo.commit(
                self,
                files=to_commit,
                msg=message,
                _datalad_msg=_datalad_msg,
                options=None,
                # do not raise on empty commit
                # it could be that the `add` in this save-cycle has already
                # brought back a 'modified' file into a clean state
                careless=True,
            )

    def save(self, message=None, paths=None, _status=None, **kwargs):
        """Save dataset content.

        Parameters
        ----------
        message : str or None
          A message to accompany the changeset in the log. If None,
          a default message is used.
        paths : list or None
          Any content with path matching any of the paths given in this
          list will be saved. Matching will be performed against the
          dataset status (GitRepo.status()), or a custom status provided
          via `_status`. If no paths are provided, ALL non-clean paths
          present in the repo status or `_status` will be saved.
        _status : dict or None
          If None, Repo.status() will be queried for the given `ds`. If
          a dict is given, its content will be used as a constraint.
          For example, to save only modified content, but no untracked
          content, set `paths` to None and provide a `_status` that has
          no entries for untracked content.
        **kwargs :
          Additional arguments that are passed to underlying Repo methods.
          Supported:

          - git : bool (passed to Repo.add()
          - eval_submodule_state : {'full', 'commit', 'no'}
            passed to Repo.status()
          - untracked : {'no', 'normal', 'all'} - passed to Repo.satus()
        """
        return list(
            self.save_(
                message=message,
                paths=paths,
                _status=_status,
                **kwargs
            )
        )

    def save_(self, message=None, paths=None, _status=None, **kwargs):
        """Like `save()` but working as a generator."""
        from datalad.interface.results import get_status_dict

        status = self._save_pre(paths, _status, **kwargs)
        if not status:
            # all clean, nothing todo
            lgr.debug('Nothing to save in %r, exiting early', self)
            return

        # three things are to be done:
        # - remove (deleted if not already staged)
        # - add (modified/untracked)
        # - commit (with all paths that have been touched, to bypass
        #   potential pre-staged bits)

        need_partial_commit = True if self.get_staged_paths() else False

        # remove first, because removal of a subds would cause a
        # modification of .gitmodules to be added to the todo list
        to_remove = [
            # TODO remove pathobj stringification when delete() can
            # handle it
            str(f.relative_to(self.pathobj))
            for f, props in status.items()
            if props.get('state', None) == 'deleted' and
            # staged deletions have a gitshasum reported for them
            # those should not be processed as git rm will error
            # due to them being properly gone already
            not props.get('gitshasum', None)]
        vanished_subds = any(
            props.get('type', None) == 'dataset' and
            props.get('state', None) == 'deleted'
            for f, props in status.items())
        if to_remove:
            for r in self.remove(
                    to_remove,
                    # we would always see individual files
                    recursive=False):
                # TODO normalize result
                yield get_status_dict(
                    action='delete',
                    refds=self.pathobj,
                    # TODO make remove() report the type
                    # for now it claims to report on files only
                    type='file',
                    path=(self.pathobj / ut.PurePosixPath(r)),
                    # make remove() report on failures too
                    status='ok',
                    logger=lgr)

        # TODO this additonal query should not be, base on status as given
        # if anyhow possible, however, when paths are given, status may
        # not contain all required information. In case of path=None AND
        # _status=None, we should be able to avoid this, because
        # status should have the full info already
        # looks for contained repositories
        added_submodule = False
        untracked_dirs = [f.relative_to(self.pathobj)
                          for f, props in status.items()
                          if props.get('state', None) == 'untracked' and
                          props.get('type', None) == 'directory']
        to_add_submodules = []
        if untracked_dirs:
            to_add_submodules = [sm for sm, sm_props in
                self.get_content_info(
                    untracked_dirs,
                    ref=None,
                    # request exhaustive list, so that everything that is
                    # still reported as a directory must be its own repository
                    untracked='all').items()
                if sm_props.get('type', None) == 'directory']
            to_add_submodules = _prune_deeper_repos(to_add_submodules)
            for cand_sm in to_add_submodules:
                branch = self.get_active_branch()
                adjusted_match = ADJUSTED_BRANCH_EXPR.match(
                    branch if branch else '')
                try:
                    self.add_submodule(
                        str(cand_sm.relative_to(self.pathobj)),
                        url=None,
                        name=None,
                        branch=adjusted_match.group('name') if adjusted_match
                        else branch
                    )
                except (CommandError, InvalidGitRepositoryError) as e:
                    yield get_status_dict(
                        action='add_submodule',
                        ds=self,
                        path=self.pathobj / ut.PurePosixPath(cand_sm),
                        status='error',
                        message=e.stderr if hasattr(e, 'stderr')
                        else ('not a Git repository: %s', exc_str(e)),
                        logger=lgr)
                    continue
                # This mirrors the result structure yielded for
                # to_stage_submodules below.
                yield get_status_dict(
                    action='add',
                    refds=self.pathobj,
                    type='file',
                    key=None,
                    path=self.pathobj / ut.PurePosixPath(cand_sm),
                    status='ok',
                    logger=lgr)
                added_submodule = True
        if not need_partial_commit:
            # without a partial commit an AnnexRepo would ignore any submodule
            # path in its add helper, hence `git add` them explicitly
            to_stage_submodules = {
                str(f.relative_to(self.pathobj)): props
                for f, props in status.items()
                if props.get('state', None) in ('modified', 'untracked')
                and props.get('type', None) == 'dataset'}
            if to_stage_submodules:
                lgr.debug(
                    '%i submodule path(s) to stage in %r %s',
                    len(to_stage_submodules), self,
                    to_stage_submodules
                    if len(to_stage_submodules) < 10 else '')
                for r in GitRepo._save_add(
                        self,
                        to_stage_submodules,
                        git_opts=None):
                    yield r

        if added_submodule or vanished_subds:
            # need to include .gitmodules in what needs saving
            status[self.pathobj.joinpath('.gitmodules')] = dict(
                type='file', state='modified')
            if hasattr(self, 'annexstatus') and not kwargs.get('git', False):
                # we cannot simply hook into the coming add-call
                # as this would go to annex, so make a dedicted git-add
                # call to ensure .gitmodules is not annexed
                # in any normal DataLad dataset .gitattributes will
                # prevent this, but in a plain repo it won't
                # https://github.com/datalad/datalad/issues/3306
                for r in GitRepo._save_add(
                        self,
                        {op.join(self.path, '.gitmodules'): None}):
                    yield r
        to_add = {
            # TODO remove pathobj stringification when add() can
            # handle it
            str(f.relative_to(self.pathobj)): props
            for f, props in status.items()
            if (props.get('state', None) in ('modified', 'untracked') and
                f not in to_add_submodules)}
        if to_add:
            lgr.debug(
                '%i path(s) to add to %s %s',
                len(to_add), self, to_add if len(to_add) < 10 else '')
            for r in self._save_add(
                    to_add,
                    git_opts=None,
                    **{k: kwargs[k] for k in kwargs
                       if k in (('git',) if hasattr(self, 'annexstatus')
                                else tuple())}):
                yield r

        self._save_post(message, status, need_partial_commit)
        # TODO yield result for commit, prev helper checked hexsha pre
        # and post...

    def _save_add(self, files, git_opts=None):
        """Simple helper to add files in save()"""
        from datalad.interface.results import get_status_dict
        try:
            # without --verbose git 2.9.3  add does not return anything
            add_out = self._git_custom_command(
                list(files.keys()),
                ['git', 'add'] + assure_list(git_opts) + ['--verbose']
            )
            # get all the entries
            for r in self._process_git_get_output(*add_out):
                yield get_status_dict(
                    action=r.get('command', 'add'),
                    refds=self.pathobj,
                    type='file',
                    path=(self.pathobj / ut.PurePosixPath(r['file']))
                    if 'file' in r else None,
                    status='ok' if r.get('success', None) else 'error',
                    key=r.get('key', None),
                    # while there is no git-annex underneath here, we
                    # tend to fake its behavior, so we can also support
                    # this type of messaging
                    message='\n'.join(r['error-messages'])
                    if 'error-messages' in r else None,
                    logger=lgr)
        except OSError as e:
            lgr.error("add: %s" % e)
            raise


# TODO
# remove submodule: nope, this is just deinit_submodule + remove
# status?


def _fixup_submodule_dotgit_setup(ds, relativepath):
    """Implementation of our current of .git in a subdataset

    Each subdataset/module has its own .git directory where a standalone
    repository would have it. No gitdir files, no symlinks.
    """
    # move .git to superrepo's .git/modules, remove .git, create
    # .git-file
    path = opj(ds.path, relativepath)
    subds_dotgit = opj(path, ".git")

    repo = GitRepo(path, create=False)
    if repo.dot_git.parent == repo.pathobj:
        # this is what we want
        return

    # first we want to remove any conflicting worktree setup
    # done by git to find the checkout at the mountpoint of the
    # submodule, if we keep that, any git command will fail
    # after we move .git
    # Ben: Shouldn't we re-setup a possible worktree afterwards?
    repo.config.unset('core.worktree', where='local')
    # what we have here is some kind of reference, remove and
    # replace by the target
    os.remove(subds_dotgit)
    # make absolute
    src_dotgit = str(repo.dot_git)
    # move .git
    from os import rename, listdir, rmdir
    assure_dir(subds_dotgit)
    for dot_git_entry in listdir(src_dotgit):
        rename(opj(src_dotgit, dot_git_entry),
               opj(subds_dotgit, dot_git_entry))
    assert not listdir(src_dotgit)
    rmdir(src_dotgit)
