# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Core interface to Git repositories

At the moment the GitRepo class provided here is not meant to be used
directly, but is primarily a vehicle for a slow refactoring process.

While is could be used directly in some cases, note that the singleton
handling implemented here will not allow switching between this
implementation and the old-standard from datalad.support.gitrepo for the
lifetime of a singleton.
"""

__all__ = ['GitRepo']

import logging
from os import environ
from os.path import lexists
import re
import threading
import time
from weakref import (
    finalize,
    WeakValueDictionary
)
from datalad.cmd import (
    GitWitlessRunner,
    StdOutErrCapture,
)
from datalad.config import ConfigManager
from datalad.dataset.repo import (
    PathBasedFlyweight,
    RepoInterface,
    path_based_str_repr,
)
from datalad.support.exceptions import (
    CommandError,
    GitIgnoreError,
    InvalidGitRepositoryError,
    PathKnownToRepositoryError,
)
from datalad.utils import (
    ensure_list,
    Path,
)


lgr = logging.getLogger('datalad.dataset.gitrepo')


@path_based_str_repr
class GitRepo(RepoInterface, metaclass=PathBasedFlyweight):
    """Representation of a Git repository

    """
    # Could be used to e.g. disable automatic garbage and autopacking
    # ['-c', 'receive.autogc=0', '-c', 'gc.auto=0']
    _GIT_COMMON_OPTIONS = ["-c", "diff.ignoreSubmodules=none"]
    _git_cmd_prefix = ["git"] + _GIT_COMMON_OPTIONS

    # Begin Flyweight:

    _unique_instances = WeakValueDictionary()

    def _flyweight_invalid(self):
        return not self.is_valid()

    @classmethod
    def _flyweight_reject(cls, id_, *args, **kwargs):
        pass

    @classmethod
    def _cleanup(cls, path):
        # Ben: I think in case of GitRepo there's nothing to do ATM. Statements
        #      like the one in the out commented __del__ above, don't make sense
        #      with python's GC, IMO, except for manually resolving cyclic
        #      references (not the case w/ ConfigManager ATM).
        lgr.log(1, "Finalizer called on: GitRepo(%s)", path)

    def __hash__(self):
        # the flyweight key is already determining unique instances
        # add the class name to distinguish from strings of a path
        return hash((self.__class__.__name__, self.__weakref__.key))

    # End Flyweight

    def __init__(self, path):
        # A lock to prevent multiple threads performing write operations in parallel
        self._write_lock = threading.Lock()

        # Note, that the following three path objects are used often and
        # therefore are stored for performance. Path object creation comes with
        # a cost. Most notably, this is used for validity checking of the
        # repository.
        self.pathobj = Path(path)
        self.dot_git = _get_dot_git(self.pathobj, ok_missing=True)
        self._valid_git_test_path = self.dot_git / 'HEAD'

        self._cfg = None
        self._git_runner = GitWitlessRunner(cwd=self.pathobj)

        self.__fake_dates_enabled = None

        # Finally, register a finalizer (instead of having a __del__ method).
        # This will be called by garbage collection as well as "atexit". By
        # keeping the reference here, we can also call it explicitly.
        # Note, that we can pass required attributes to the finalizer, but not
        # `self` itself. This would create an additional reference to the object
        # and thereby preventing it from being collected at all.
        self._finalizer = finalize(self, GitRepo._cleanup, self.pathobj)

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        """
        return self.pathobj == obj.pathobj

    def is_valid(self_or_path):
        """Returns whether the underlying repository appears to be still valid

        This method can be used as an instance method or a class method.
        """
        # preserving notes from the original implementations in GitRepo
        #
        # Note, that this almost identical to the classmethod is_valid_repo().
        # However, if we are testing an existing instance, we can save Path object
        # creations. Since this testing is done a lot, this is relevant. Creation
        # of the Path objects in is_valid_repo() takes nearly half the time of the
        # entire function.

        # Also note, that this method is bound to an instance but still
        # class-dependent, meaning that a subclass cannot simply overwrite it.
        # This is particularly important for the call from within __init__(),
        # which in turn is called by the subclasses' __init__. Using an overwrite
        # would lead to the wrong thing being called.
        if not isinstance(self_or_path, GitRepo):
            # called like a classmethod, perform test without requiring
            # a repo instance
            if not isinstance(self_or_path, Path):
                self_or_path = Path(self_or_path)
            dot_git_path = self_or_path / '.git'
            return (dot_git_path.exists() and (
                not dot_git_path.is_dir() or (dot_git_path / 'HEAD').exists()
            )) or (self_or_path / 'HEAD').exists()
        else:
            # called as a method of a repo instance
            return self_or_path.dot_git.exists() and (
                not self_or_path.dot_git.is_dir()
                or self_or_path._valid_git_test_path.exists()
            )

    @property
    def cfg(self):
        """Get a ConfigManager instance for this repository

        Returns
        -------
        ConfigManager
        """
        if self._cfg is None:
            # associate with this dataset and read the entire config hierarchy
            self._cfg = ConfigManager(dataset=self, source='any')
        return self._cfg

    @property
    def _fake_dates_enabled(self):
        """Is the repository configured to use fake dates?

        This is an internal query performance helper for the datalad.fake-dates
        config option.
        """
        if self.__fake_dates_enabled is None:
            self.__fake_dates_enabled = \
                self.cfg.getbool('datalad', 'fake-dates', default=False)
        return self.__fake_dates_enabled

    def add_fake_dates_to_env(self, env=None):
        """Add fake dates to `env`.

        Parameters
        ----------
        env : dict, optional
            Environment variables.

        Returns
        -------
        A dict (copied from env), with date-related environment
        variables for git and git-annex set.
        """
        env = (env if env is not None else environ).copy()
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
            seconds = self.cfg.obtain("datalad.fake-dates-start")
        seconds_new = seconds + 1
        date = "@{} +0000".format(seconds_new)

        lgr.debug("Setting date to %s",
                  time.strftime("%a %d %b %Y %H:%M:%S +0000",
                                time.gmtime(seconds_new)))

        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
        env["GIT_ANNEX_VECTOR_CLOCK"] = str(seconds_new)

        return env

    def _call_git(self, args, files=None, expect_stderr=False, expect_fail=False,
                  env=None, read_only=False):
        """Allows for calling arbitrary commands.

        Internal helper to the call_git*() methods.

        The parameters, return value, and raised exceptions match those
        documented for `call_git`.
        """
        runner = self._git_runner
        stderr_log_level = {True: 5, False: 11}[expect_stderr]

        cmd = self._git_cmd_prefix + args

        if not read_only and self._fake_dates_enabled:
            env = self.add_fake_dates_to_env(env if env else runner.env)

        protocol = StdOutErrCapture
        out = err = None
        try:
            if not read_only:
                self._write_lock.acquire()
            if files:
                # only call the wrapper if needed (adds distraction logs
                # otherwise, and also maintains the possibility to connect
                # stdin in the future)
                res = runner.run_on_filelist_chunks(
                    cmd,
                    files,
                    protocol=protocol,
                    env=env)
            else:
                res = runner.run(
                    cmd,
                    protocol=protocol,
                    env=env)
        except CommandError as e:
            ignored = re.search(GitIgnoreError.pattern, e.stderr)
            if ignored:
                raise GitIgnoreError(cmd=e.cmd, msg=e.stderr,
                                     code=e.code, stdout=e.stdout,
                                     stderr=e.stderr,
                                     paths=ignored.groups()[0].splitlines())
            lgr.log(5 if expect_fail else 11, str(e))
            raise
        finally:
            if not read_only:
                self._write_lock.release()

        out = res['stdout']
        err = res['stderr']
        if err:
            for line in err.splitlines():
                lgr.log(stderr_log_level,
                        "stderr| " + line.rstrip('\n'))
        return out, err

    def call_git(self, args, files=None,
                 expect_stderr=False, expect_fail=False, read_only=False):
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
        read_only : bool, optional
          By setting this to True, the caller indicates that the command does
          not write to the repository, which lets this function skip some
          operations that are necessary only for commands the modify the
          repository. Beware that even commands that are conceptually
          read-only, such as `git-status` and `git-diff`, may refresh and write
          the index.

        Returns
        -------
        standard output (str)

        Raises
        ------
        CommandError if the call exits with a non-zero status.
        """
        out, _ = self._call_git(args, files,
                                expect_stderr=expect_stderr,
                                expect_fail=expect_fail,
                                read_only=read_only)
        return out

    def call_git_items_(self, args, files=None, expect_stderr=False, sep=None,
                        read_only=False):
        """Call git, splitting output on `sep`.

        Parameters
        ----------
        sep : str, optional
          Split the output by `str.split(sep)` rather than `str.splitlines`.

        All other parameters match those described for `call_git`.

        Returns
        -------
        Generator that yields output items.

        Raises
        ------
        CommandError if the call exits with a non-zero status.
        """
        out, _ = self._call_git(args, files, expect_stderr=expect_stderr,
                                read_only=read_only)
        yield from (out.split(sep) if sep else out.splitlines())

    def call_git_oneline(self, args, files=None, expect_stderr=False, read_only=False):
        """Call git for a single line of output.

        All other parameters match those described for `call_git`.

        Raises
        ------
        CommandError if the call exits with a non-zero status.
        AssertionError if there is more than one line of output.
        """
        lines = list(self.call_git_items_(args, files=files,
                                          expect_stderr=expect_stderr,
                                          read_only=read_only))
        if len(lines) > 1:
            raise AssertionError(
                "Expected {} to return single line, but it returned {}"
                .format(["git"] + args, lines))
        return lines[0]

    def call_git_success(self, args, files=None, expect_stderr=False, read_only=False):
        """Call git and return true if the call exit code of 0.

        All parameters match those described for `call_git`.

        Returns
        -------
        bool
        """
        try:
            self._call_git(
                args, files, expect_fail=True, expect_stderr=expect_stderr,
                read_only=read_only)

        except CommandError:
            return False
        return True

    def init(self, sanity_checks=True, init_options=None):
        """Initializes the Git repository.

        Parameters
        ----------
        create_sanity_checks: bool, optional
          Whether to perform sanity checks during initialization if the target
          path already exists, such as that new repository is not created in
          the directory where git already tracks some files.
        init_options: list, optional
          Additional options to be appended to the `git-init` call.
        """
        pathobj = self.pathobj
        path = str(pathobj)

        if not lexists(path):
            pathobj.mkdir(parents=True)
        elif sanity_checks:
            # Verify that we are not trying to initialize a new git repository
            # under a directory some files of which are already tracked by git
            # use case: https://github.com/datalad/datalad/issues/3068
            try:
                stdout, _ = self._call_git(
                    ['-C', path, 'ls-files'],
                    expect_fail=True,
                    read_only=True,
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

        cmd = ['-C', path, 'init']
        cmd.extend(ensure_list(init_options))
        lgr.debug(
            "Initialize empty Git repository at '%s'%s",
            path,
            ' %s' % cmd[3:] if cmd[3:] else '')

        stdout, stderr = self._call_git(
            cmd,
            # we don't want it to scream on stdout
            expect_fail=True,
            # there is no commit, and none will be made
            read_only=True)

        # after creation we need to reconsider .git path
        self.dot_git = _get_dot_git(self.pathobj, ok_missing=True)

        return self

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
        fields = ensure_list(fields)
        cmd = [
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
            for k in ensure_list(sort):
                cmd.append('--sort={}'.format(k))
        if pattern:
            cmd += ensure_list(pattern)
        if count:
            cmd.append('--count={:d}'.format(count))

        for line in self.call_git_items_(cmd, read_only=True):
            props = line.split('\0')
            if len(fields) != len(props):
                raise RuntimeError(
                    'expected fields {} from git-for-each-ref, but got: {}'.format(
                        fields, props))
            yield dict(zip(fields, props))


#
# Internal helpers
#
def _get_dot_git(pathobj, *, ok_missing=False):
    """Given a pathobj to a repository return path to .git/ directory

    Parameters
    ----------
    pathobj: Path
    ok_missing: bool, optional
      Allow for .git to be missing (useful while sensing before repo is
      initialized)

    Raises
    ------
    RuntimeError
      When ok_missing is False and .git path does not exist

    Returns
    -------
    Path
      Absolute path to resolved .git/ directory
    """
    dot_git = pathobj / '.git'
    if dot_git.is_file():
        with dot_git.open() as f:
            line = f.readline()
            if line.startswith("gitdir: "):
                dot_git = pathobj / line[7:].strip()
            else:
                raise InvalidGitRepositoryError("Invalid .git file")
    elif dot_git.is_symlink():
        dot_git = dot_git.resolve()
    elif not dot_git.exists() and \
            (pathobj / 'HEAD').exists() and \
            (pathobj / 'config').exists():
        # looks like a bare repo
        dot_git = pathobj
    elif not (ok_missing or dot_git.exists()):
        raise RuntimeError("Missing .git in %s." % pathobj)
    return dot_git
