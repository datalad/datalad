# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Internal low-level interface to Git repositories

"""

import logging
from os import environ
import re
import time
from weakref import WeakValueDictionary

from datalad.config import (
    ConfigManager,
)
from datalad.core.dataset import (
    PathBasedFlyweight,
    RepoInterface,
    path_based_str_repr,
)
from datalad.utils import (
    ensure_list,
    Path,
)
from datalad.support.exceptions import (
    CommandError,
    GitIgnoreError,
    InvalidGitRepositoryError,
)
from datalad.cmd import (
    GitRunner,
    run_gitcommand_on_file_list_chunks,
)

lgr = logging.getLogger('datalad.core.dataset.gitrepo')


@path_based_str_repr
class GitRepo(RepoInterface, metaclass=PathBasedFlyweight):
    """Representation of a git repository

    """
    # We must check git config to have name and email set, but
    # should do it once
    _config_checked = False

    # Begin Flyweight:

    _unique_instances = WeakValueDictionary()

    GIT_MIN_VERSION = "2.19.1"
    git_version = None

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

    def __init__(self, path):
        """Creates representation of git repository at `path`.

        Parameters
        ----------
        path: str
          path to the git repository; In case it's not an absolute path,
          it's relative to PWD
        """
        self.path = path
        self.pathobj = Path(path)
        self._cfg = None

        # Note, that the following objects are used often and therefore are
        # stored for performance. Path object creation comes with a cost. Most
        # noteably, this is used for validity checking of the repository.
        self.dot_git = self._get_dot_git(self.pathobj, ok_missing=True)
        self._valid_git_test_path = self.dot_git / 'HEAD'

        # Could be used to e.g. disable automatic garbage and autopacking
        # ['-c', 'receive.autogc=0', '-c', 'gc.auto=0']
        self._GIT_COMMON_OPTIONS = []

        self._cmd_call_wrapper = GitRunner(cwd=path)

        # Set by fake_dates_enabled to cache config value across this instance.
        self._fake_dates_enabled = None

    def __hash__(self):
        # the flyweight key is already determining unique instances
        # add the class name to distinguish from strings of a path
        return hash((self.__class__.__name__, self.__weakref__.key))

    def __del__(self):
        # unbind possibly bound ConfigManager, to prevent all kinds of weird
        # stalls etc
        self._cfg = None

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        """
        return self.path == obj.path

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

    @staticmethod
    def _get_dot_git(pathobj, *, ok_missing=False, maybe_relative=False):
        """Given a pathobj to a repository return path to .git/ directory

        Parameters
        ----------
        pathobj: Path
        ok_missing: bool, optional
          Allow for .git to be missing (useful while sensing before repo is initialized)
        maybe_relative: bool, optional
          Return path relative to pathobj

        Raises
        ------
        RuntimeError
          When ok_missing is False and .git path does not exist

        Returns
        -------
        Path
          Absolute (unless maybe_relative=True) path to resolved .git/ directory
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
        elif not (ok_missing or dot_git.exists()):
            raise RuntimeError("Missing .git in %s." % pathobj)
        # Primarily a compat kludge for get_git_dir, remove when it is deprecated
        if maybe_relative:
            try:
                dot_git = dot_git.relative_to(pathobj)
            except ValueError:
                # is not a subpath, return as is
                lgr.debug("Path %r is not subpath of %r", dot_git, pathobj)
        return dot_git

    def is_valid_git(self):
        """Returns whether the underlying repository appears to be still valid

        Note, that this almost identical to the classmethod
        GitRepo.is_valid_repo().  However, if we are testing an existing
        instance, we can save Path object creations. Since this testing is done
        a lot, this is relevant.  Creation of the Path objects in

        Also note, that this method is bound to an instance but still
        class-dependent, meaning that a subclass cannot simply overwrite it.
        This is particularly important for the call from within __init__(),
        which in turn is called by the subclasses' __init__. Using an overwrite
        would lead to the wrong thing being called.
        """

        return self.dot_git.exists() and (
            not self.dot_git.is_dir() or self._valid_git_test_path.exists()
        )

    def is_with_annex(self):
        """Report if GitRepo (assumed) has (remotes with) a git-annex branch
        """
        return any(
            b['refname:strip=2'] == 'git-annex'
            or b['refname:strip=2'].endswith('/git-annex')
            for b in self.for_each_ref_(
                fields='refname:strip=2',
                pattern=['refs/heads', 'refs/remotes'])
        )

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

        out, _ = self._call_git(cmd)
        for line in out.splitlines():
            props = line.split('\0')
            if len(fields) != len(props):
                raise RuntimeError(
                    'expected fields {} from git-for-each-ref, but got: {}'.format(
                        fields, props))
            yield dict(zip(fields, props))

    def _call_git(self, args, files=None, expect_stderr=False, expect_fail=False,
                  cwd=None, env=None):
        """Allows for calling arbitrary commands.

        Internal helper to the call_git*() methods.

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
        stdout, stderr

        Raises
        ------
        CommandError if the call exits with a non-zero status.
        """
        cmd = ['git'] + self._GIT_COMMON_OPTIONS + args

        if self.fake_dates_enabled:
            env = self.add_fake_dates(env)

        try:
            out, err = run_gitcommand_on_file_list_chunks(
                self._cmd_call_wrapper.run,
                cmd,
                files,
                log_stderr=True,
                log_stdout=True,
                log_online=False,
                expect_stderr=expect_stderr,
                cwd=cwd,
                env=env,
                shell=None,
                expect_fail=expect_fail)
        except CommandError as e:
            ignored = re.search(GitIgnoreError.pattern, e.stderr)
            if ignored:
                raise GitIgnoreError(cmd=e.cmd, msg=e.stderr,
                                     code=e.code, stdout=e.stdout,
                                     stderr=e.stderr,
                                     paths=ignored.groups()[0].splitlines())
            raise

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
        out, _ = self._call_git(args, files,
                                expect_stderr=expect_stderr,
                                expect_fail=expect_fail)
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
        out, _ = self._call_git(args, files, expect_stderr=expect_stderr)
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
            self._call_git(
                args, files, expect_fail=True, expect_stderr=expect_stderr)
        except CommandError:
            return False
        return True

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
        env = (env if env is not None else environ).copy()
        if 'DATALAD_FAKE_DATE' in env:
            # there is already a fake date setup
            return env
        # prevent infinite recursion, should this function be called again
        # inside the next call.
        environ['DATALAD_FAKE_DATE'] = '1'
        last_date = list(self.for_each_ref_(
            fields='committerdate:raw',
            count=1,
            pattern='refs/heads',
            sort="-committerdate",
        ))
        del environ['DATALAD_FAKE_DATE']

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
        # leave a marker to prevent duplicate processing
        env["DATALAD_FAKE_DATE"] = date

        return env

    @property
    def fake_dates_enabled(self):
        """Is the repository configured to use fake dates?
        """
        if self._fake_dates_enabled is None:
            self._fake_dates_enabled = \
                self.config.getbool('datalad', 'fake-dates', default=False)
        return self._fake_dates_enabled
