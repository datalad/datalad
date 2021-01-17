# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Internal core interface to Git repositories

"""

__all__ = ['GitRepo']

from collections import OrderedDict
import logging
from os import (
    environ,
    readlink,
)
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
    BatchedCommand,
)
from datalad.config import (
    ConfigManager,
    _parse_gitconfig_dump,
)
from datalad.dataset.repo import (
    PathBasedFlyweight,
    RepoInterface,
    path_based_str_repr,
)
from datalad.core.local.repo import repo_from_path
from datalad.support.exceptions import (
    CommandError,
    GitIgnoreError,
    InvalidGitReferenceError,
    InvalidGitRepositoryError,
    PathKnownToRepositoryError,
)
from datalad.support.external_versions import external_versions
from datalad.support.path import get_parent_paths
from datalad.utils import (
    ensure_list,
    Path,
    PurePosixPath,
)


lgr = logging.getLogger('datalad.dataset.gitrepo')


@path_based_str_repr
class GitRepo(RepoInterface, metaclass=PathBasedFlyweight):
    """Representation of a Git repository

    """
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

        # Could be used to e.g. disable automatic garbage and autopacking
        # ['-c', 'receive.autogc=0', '-c', 'gc.auto=0']
        self._GIT_COMMON_OPTIONS = []
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

        cmd = ['git'] + self._GIT_COMMON_OPTIONS + args

        env = None
        if not read_only and self._fake_dates_enabled:
            env = self.add_fake_dates_to_env(runner.env)

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
        # use git-log and not git-show due to faster performance with
        # complex commits (e.g. octopus merges)
        # https://github.com/datalad/datalad/issues/4801
        cmd = ['log', '-1', '-z', '--format=' + fmt]
        if commitish is not None:
            cmd.append(commitish + "^{commit}")
        # make sure Git takes our argument as a revision
        cmd.append('--')
        try:
            stdout = self.call_git(
                cmd, expect_stderr=True, expect_fail=True,
                read_only=True)
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

    def get_active_branch(self):
        """Get the name of the active branch

        Returns
        -------
        str or None
          Returns None if there is no active branch, i.e. detached HEAD,
          and the branch name otherwise.
        """
        try:
            out = self.call_git(["symbolic-ref", "HEAD"], expect_fail=True,
                                read_only=True)
        except CommandError as e:
            if 'HEAD is not a symbolic ref' in e.stderr:
                lgr.debug("detached HEAD in {0}".format(self))
                return None
            else:
                raise e
        return out.strip()[11:]  # strip refs/heads/

    def get_corresponding_branch(self, branch=None):
        """Always returns None, a plain GitRepo has no managed branches"""
        return None

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
        str or, if no commitish was given and there are no commits yet, None.

        Raises
        ------
        ValueError
          If a commitish was given, but no corresponding commit could be
          determined.
        """
        # use --quiet because the 'Needed a single revision' error message
        # that is the result of running this in a repo with no commits
        # isn't useful to report
        cmd = ['rev-parse', '--quiet', '--verify', '{}^{{commit}}'.format(
            commitish if commitish else 'HEAD')
        ]
        if short:
            cmd.append('--short')
        try:
            return self.call_git_oneline(cmd, read_only=True)
        except CommandError as e:
            if commitish is None:
                return None
            raise ValueError("Unknown commit identifier: %s" % commitish)

    def ls_state(self, paths=None, ref=None, untracked='all',
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
        lgr.debug('%s.ls_state(...)', self)
        # TODO limit by file type to replace code in subdatasets command
        info = OrderedDict()

        if paths:
            # path matching will happen against what Git reports
            # and Git always reports POSIX paths
            # any incoming path has to be relative already, so we can simply
            # convert unconditionally
            paths = [PurePosixPath(p) for p in paths]

        path_strs = list(map(str, paths)) if paths else None
        if path_strs and (not ref or external_versions["cmd:git"] >= "2.29.0"):
            # If a path points within a submodule, we need to map it to the
            # containing submodule before feeding it to ls-files or ls-tree.
            #
            # Before Git 2.29.0, ls-tree and ls-files differed in how they
            # reported paths within submodules: ls-files provided no output,
            # and ls-tree listed the submodule. Now they both return no output.
            submodules = [str(s["path"].relative_to(self.pathobj))
                          for s in self.get_submodules_()]
            path_strs = get_parent_paths(path_strs, submodules)

        # this will not work in direct mode, but everything else should be
        # just fine
        if not ref:
            # make sure no operations are pending before we figure things
            # out in the worktree. old gitrepo had a precommit() for that
            if hasattr(self, 'precommit'):
                self.precommit()

            # --exclude-standard will make sure to honor and standard way
            # git can be instructed to ignore content, and will prevent
            # crap from contaminating untracked file reports
            cmd = ['ls-files', '--stage', '-z']
            # untracked report mode, using labels from `git diff` option style
            if untracked == 'all':
                cmd += ['--exclude-standard', '-o']
            elif untracked == 'normal':
                cmd += ['--exclude-standard', '-o', '--directory', '--no-empty-directory']
            elif untracked == 'no':
                pass
            else:
                raise ValueError(
                    'unknown value for `untracked`: {}'.format(untracked))
            props_re = re.compile(
                r'(?P<type>[0-9]+) (?P<sha>.*) (.*)\t(?P<fname>.*)$')
        else:
            cmd = ['ls-tree', ref, '-z', '-r', '--full-tree', '-l']
            props_re = re.compile(
                r'(?P<type>[0-9]+) ([a-z]*) (?P<sha>[^ ]*) [\s]*(?P<size>[0-9-]+)\t(?P<fname>.*)$')

        lgr.debug('Query repo: %s', cmd)
        try:
            stdout = self.call_git(
                cmd,
                files=path_strs,
                expect_fail=True,
                read_only=True)
        except CommandError as exc:
            if "fatal: Not a valid object name" in exc.stderr:
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
                path=str(self.pathobj),
                output_proc=_read_symlink_target_from_catfile,
            )
        else:
            def try_readlink(path):
                try:
                    return readlink(path)
                except OSError:
                    # readlink will fail if the symlink reported by ls-files is
                    # not in the working tree (it could be removed or
                    # unlocked). Fall back to a slower method.
                    return str(Path(path).resolve())

            _get_link_target = try_readlink

        try:
            _gitrepo_ls_state_parse_line_helper(
                self.pathobj,
                ref,
                info,
                stdout.split('\0'),
                props_re,
                _get_link_target)
        finally:
            if ref and _get_link_target:
                # cancel batch process
                _get_link_target.close()

        lgr.debug('Done %s.ls_state(...)', self)
        return info

    def compare_states(self, fr, to, paths=None, untracked='all',
                       eval_submodule_state='full', eval_file_type=True,
                       _cache=None):
        """Simplified `git status/diff` analog.

        This method essentially performs two calls to `ls_state()`, to
        gather information, and then performs a comparison of records
        for the union of repository content reported across both states.

        Parameters
        ----------
        fr : str or None
          Revision specification for the "from" state. Passed as `ref` to
          `ls_state()`.
        to : str or None
          Revision specification for the "to" (target) state. Passed as `ref` to
          `ls_state()`.
        paths : list or None
          If given, limits the query to the specified paths. To query all
          paths specify `None`, not an empty list. If a query path points
          into a subdataset, a report is made on the subdataset record
          within the queried dataset only (no recursion). Paths must either
          be absolute or relative to the repository root.
        untracked : {'no', 'normal', 'all'}
          If and how untracked content is reported:
          'no': no untracked files are reported; 'normal': untracked files
          and entire untracked directories are reported as such; 'all': report
          individual files even in fully untracked directories.
        eval_submodule_state : {'full', 'commit', 'no', 'global'}
          If 'full' (the default), the state of a submodule is evaluated by
          considering all modifications, with the treatment of untracked files
          determined by `untracked`. If 'commit', the modification check is
          restricted to comparing the submodule's HEAD commit to the one
          recorded in the superdataset. If 'no', the state of the subdataset is
          not evaluated. With the special mode 'global', the runtime and return
          value behavior is changed to return a single 'modified' (vs. 'clean')
          state label for the entire repository, as soon as possible, and
          avoid any further inspection of submodules.
        eval_file_type : bool
          If True, inspect file type of untracked files, and report annex
          symlink pointers as type 'file'. This convenience comes with a
          cost; disable to get faster performance if this information
          is not needed.

        Returns
        -------
        dict or str
          With `eval_submodule_state='global' either 'modified' or 'clean' is
          returned. In any other case, a a dictionary with comparison results
          is returned.

          Each content item has an entry under a pathlib `Path` object instance
          pointing to its absolute path inside the repository (this path is
          guaranteed to be underneath `Repo.path`).
          Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'
          `state`
            Can be 'added', 'untracked', 'clean', 'deleted', 'modified'.
                     _cache=None):
        """
        def _get_cache_key(label, paths, ref, untracked=None):
            return self.pathobj, label, tuple(paths) if paths else None, \
                ref, untracked

        if _cache is None:
            _cache = {}

        if paths:
            # at this point we must normalize paths to the form that
            # Git would report them, to easy matching later on
            paths = [Path(p) for p in paths]
            paths = [
                p.relative_to(self.pathobj) if p.is_absolute() else p
                for p in paths
            ]

        # TODO report more info from ls() calls in return
        # value, those are cheap and possibly useful to a consumer
        # we need (at most) three calls to git
        if to is None:
            # everything we know about the worktree, including os.stat
            # for each file
            key = _get_cache_key('ci', paths, None, untracked)
            if key in _cache:
                to_state = _cache[key]
            else:
                to_state = self.ls_state(
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
                    self.pathobj.joinpath(PurePosixPath(p))
                    for p in self.call_git_items_(
                        ['ls-files', '-z', '-m'],
                        # low-level code cannot handle pathobjs
                        files=[str(p) for p in paths] if paths else None,
                        sep='\0',
                        read_only=True)
                    if p)
                _cache[key] = modified
        else:
            key = _get_cache_key('ci', paths, to)
            if key in _cache:
                to_state = _cache[key]
            else:
                to_state = self.ls_state(
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
                from_state = self.ls_state(
                    paths=paths, ref=fr, eval_file_type=eval_file_type)
            else:
                # no ref means from nothing
                from_state = {}
            _cache[key] = from_state

        status = OrderedDict()
        for f, to_state_r in to_state.items():
            props = _gitrepo_compare_states_get_props_helper(
                f,
                from_state.get(f, None),
                to_state_r,
                # are we comparing against a recorded commit or the worktree
                to is not None,
                # if we have worktree modification info, report if
                # path is reported as modified in it
                modified and f in modified,
                eval_submodule_state)
            # potential early exit in "global" eval mode
            if eval_submodule_state == 'global' and \
                    props.get('state', None) not in ('clean', None):
                # any modification means globally 'modified'
                return 'modified'
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
                if eval_submodule_state == 'global':
                    return 'modified'

        if to is not None or eval_submodule_state == 'no':
            # if we have `to` we are specifically comparing against
            # a recorded state, and this function only attempts
            # to label the state of a subdataset, not investigate
            # specifically what the changes in subdatasets are
            # this is done by a high-level command like rev-diff
            # so the comparison within this repo and the present
            # `state` label are all we need, and they are done already
            if eval_submodule_state == 'global':
                return 'clean'
            else:
                return status

        # loop over all subdatasets and look for additional modifications
        for f, st in status.items():
            f = str(f)
            if 'state' in st or not st['type'] == 'dataset':
                # no business here
                continue
            if not GitRepo.is_valid(f):
                # submodule is not present, no chance for a conflict
                st['state'] = 'clean'
                continue
            # we have to recurse into the dataset and get its status
            subrepo = repo_from_path(f)
            # get the HEAD commit, or the one of the corresponding branch
            # only that one counts re super-sub relationship
            # save() syncs the corresponding branch each time
            subrepo_commit = subrepo.get_hexsha(subrepo.get_corresponding_branch())
            st['gitshasum'] = subrepo_commit
            # subdataset records must be labeled clean up to this point
            # test if current commit in subdataset deviates from what is
            # recorded in the dataset
            st['state'] = 'modified' \
                if st['prev_gitshasum'] != subrepo_commit \
                else 'clean'
            if eval_submodule_state == 'global' and st['state'] == 'modified':
                return 'modified'
            if eval_submodule_state == 'commit':
                continue
            # the recorded commit did not change, so we need to make
            # a more expensive traversal
            st['state'] = subrepo.compare_states(
                # we can use 'HEAD' because we know that the commit
                # did not change. using 'HEAD' will facilitate
                # caching the result
                fr='HEAD',
                to=None,
                paths=None,
                untracked=untracked,
                eval_submodule_state='global',
                eval_file_type=False,
                _cache=_cache) if st['state'] == 'clean' else 'modified'
            if eval_submodule_state == 'global' and st['state'] == 'modified':
                return 'modified'

        if eval_submodule_state == 'global':
            return 'clean'
        else:
            return status

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

        modinfo = _parse_gitmodules(self)
        for path, props in self.ls_state(
                paths=paths,
                ref=None,
                untracked='no',
                eval_file_type=False).items():
            if props.get('type', None) != 'dataset':
                # make sure this method never talks about non-dataset
                # content
                continue
            props["path"] = path
            props.update(modinfo.get(path, {}))
            yield props


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


def _gitrepo_ls_state_parse_line_helper(repopathobj, ref, info, lines,
                                        props_re, get_link_target):
    """Internal helper of ls() to parse Git output"""
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
            # Kludge: Filter out paths starting with .git/ to work around
            # an `ls-files -o` bug that was fixed in Git 2.25.
            #
            # TODO: Drop this condition when GIT_MIN_VERSION is at least
            # 2.25.
            if line.startswith(".git/"):
                lgr.debug("Filtering out .git/ file: %s", line)
                continue
            # not known to Git, but Git always reports POSIX
            path = PurePosixPath(line)
            inf['gitshasum'] = None
        else:
            # again Git reports always in POSIX
            path = PurePosixPath(props.group('fname'))

        # revisit the file props after this path has not been rejected
        if props:
            inf['gitshasum'] = props.group('sha')
            inf['type'] = mode_type_map.get(
                props.group('type'), props.group('type'))
            if get_link_target and inf['type'] == 'symlink' and \
                    ((ref is None and '.git/annex/objects' in \
                      Path(
                        get_link_target(str(repopathobj / path))
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
        path = repopathobj.joinpath(path)
        if 'type' not in inf:
            # be nice and assign types for untracked content
            inf['type'] = 'symlink' if path.is_symlink() \
                else 'directory' if path.is_dir() else 'file'
        info[path] = inf


def _gitrepo_compare_states_get_props_helper(
        f, from_state, to_state, against_commit, modified_in_worktree,
        eval_submodule_state):
    """Helper to determine diff properties for a single path

    Parameters
    ----------
    f : Path
    from_state : dict
    to_state : dict
    against_commit : bool
      Flag whether `to_state` reflects a commit or the worktree.
    modified_in_worktree : bool
      Flag whether a worktree modification is reported. This is ignored
      when `against_commit` is True.
    eval_submodule_state : {'commit', 'no', ...}
    """
    if against_commit:
        # we can ignore any worktree modification reported when
        # comparing against a commit
        modified_in_worktree = False

    props = {}
    if 'type' in to_state:
        props['type'] = to_state['type']

    to_sha = to_state['gitshasum']
    from_sha = from_state['gitshasum'] if from_state else None

    # determine the state of `f` from from_state and to_state records, if
    # it can be determined conclusively from it. If not, it will
    # stay None for now
    state = None
    if not from_state:
        # this is new, or rather not known to the previous state
        state = 'added' if to_sha else 'untracked'
    elif to_sha == from_sha and not modified_in_worktree:
        # something that is seemingly unmodified, based on the info
        # gathered so far
        if to_state['type'] == 'dataset':
            if against_commit or eval_submodule_state == 'commit':
                # we compare against a recorded state, just based on
                # the shas we can be confident, otherwise the state
                # of a subdataset isn't fully known yet, because
                # `modified_in_worktree` will only reflect changes
                # in the commit of a subdataset without looking into
                # it for uncommitted changes. Such tests are done
                # later and based on further conditionals for
                # performance reasons
                state = 'clean'
        else:
            # no change in git record, and no change on disk
            # at this point we know that the reported object ids
            # for this file are identical in the to and from
            # records.  If to is None, we're comparing to the
            # working tree and a deleted file will still have an
            # identical id, so we need to check whether the file is
            # gone before declaring it clean. This working tree
            # check is irrelevant and wrong if to is a ref.
            state = 'clean' \
                if against_commit or (f.exists() or f.is_symlink()) \
                else 'deleted'
    else:
        # change in git record, or on disk
        # for subdatasets leave the 'modified' judgement to the caller
        # for supporting corner cases, such as adjusted branch
        # which require inspection of a subdataset
        # TODO we could have a new file that is already staged
        # but had subsequent modifications done to it that are
        # unstaged. Such file would presently show up as 'added'
        # ATM I think this is OK, but worth stating...
        state = ('modified'
                 if against_commit or to_state['type'] != 'dataset'
                 else None
                ) if f.exists() or f.is_symlink() else 'deleted'
        # TODO record before and after state for diff-like use
        # cases

    if state in ('clean', 'added', 'modified', None):
        # assign present gitsha to any record
        # state==None can only happen for subdatasets that
        # already existed, so also assign a sha for them
        props['gitshasum'] = to_sha
        if 'bytesize' in to_state:
            # if we got this cheap, report it
            props['bytesize'] = to_state['bytesize']
        elif state == 'clean' and 'bytesize' in from_state:
            # no change, we can take this old size info
            props['bytesize'] = from_state['bytesize']
    if state in ('clean', 'modified', 'deleted', None):
        # assign previous gitsha to any record
        # state==None can only happen for subdatasets that
        # already existed, so also assign a sha for them
        props['prev_gitshasum'] = from_sha
    if state:
        # only report a state if we could determine any
        # outside code tests for existence of the property
        # and not (always) for the value
        props['state'] = state
    return props


def _parse_gitmodules(repo):
    # TODO read .gitconfig from Git blob?
    gitmodules = repo.pathobj / '.gitmodules'
    if not gitmodules.exists():
        return {}
    # pull out file content
    out = repo.call_git(
        ['config', '-z', '-l', '--file', '.gitmodules'],
        read_only=True)
    # abuse our config parser
    # disable multi-value report, because we could not deal with them
    # anyways, and they should not appear in a normal .gitmodules file
    # but could easily appear when duplicates are included. In this case,
    # we better not crash
    db, _ = _parse_gitconfig_dump(out, cwd=repo.path, multi_value=False)
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
        modpath = repo.pathobj / PurePosixPath(props['path'])
        modprops['gitmodule_name'] = name
        out[modpath] = modprops
    return out
