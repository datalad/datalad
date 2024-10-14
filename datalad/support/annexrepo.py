# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to git-annex by Joey Hess.

For further information on git-annex see https://git-annex.branchable.com/.

"""

import json
import logging
import os
import re
import warnings
from itertools import chain
from multiprocessing import cpu_count
from os import linesep
from os.path import (
    curdir,
    exists,
    isdir,
)
from os.path import join as opj
from os.path import (
    lexists,
    normpath,
)
from typing import Dict
from weakref import (
    WeakValueDictionary,
    finalize,
)

import datalad.utils as ut
from datalad.cmd import (  # KillOutput,
    BatchedCommand,
    GitWitlessRunner,
    SafeDelCloseMixin,
    StdOutCapture,
    StdOutErrCapture,
    WitlessProtocol,
)
from datalad.consts import WEB_SPECIAL_REMOTE_UUID
# imports from same module:
from datalad.dataset.repo import RepoInterface
from datalad.dochelpers import (
    borrowdoc,
    borrowkwargs,
)
from datalad.log import log_progress
from datalad.runner.protocol import GeneratorMixIn
from datalad.runner.utils import (
    AssemblingDecoderMixIn,
    LineSplitter,
)
from datalad.support.annex_utils import (
    _fake_json_for_non_existing,
    _get_non_existing_from_annex_output,
    _sanitize_key,
)
from datalad.support.exceptions import CapturedException
from datalad.ui import ui
from datalad.utils import (
    Path,
    PurePosixPath,
    auto_repr,
    ensure_list,
    on_windows,
    split_cmdline,
    unlink,
)

from .exceptions import (
    AccessDeniedError,
    AccessFailedError,
    AnnexBatchCommandError,
    CommandError,
    CommandNotAvailableError,
    DirectModeNoLongerSupportedError,
    FileInGitError,
    FileNotInAnnexError,
    IncompleteResultsError,
    InsufficientArgumentsError,
    InvalidAnnexRepositoryError,
    InvalidGitRepositoryError,
    MissingExternalDependency,
    NoSuchPathError,
    OutdatedExternalDependency,
    OutOfSpaceError,
    RemoteNotAvailableError,
)
from .external_versions import external_versions
from .gitrepo import (
    GitRepo,
    normalize_path,
    normalize_paths,
    to_options,
)

lgr = logging.getLogger('datalad.annex')


class AnnexRepo(GitRepo, RepoInterface):
    """Representation of an git-annex repository.

    Paths given to any of the class methods will be interpreted as relative
    to PWD, in case this is currently beneath AnnexRepo's base dir
    (`self.path`). If PWD is outside of the repository, relative paths
    will be interpreted as relative to `self.path`. Absolute paths will be
    accepted either way.
    """

    # Begin Flyweight:
    _unique_instances = WeakValueDictionary()

    def _flyweight_invalid(self):
        return not self.is_valid_annex(allow_noninitialized=True)

    # End Flyweight:

    # Web remote UUID, kept here for backward compatibility
    WEB_UUID = WEB_SPECIAL_REMOTE_UUID

    # To be assigned and checked to be good enough upon first call to AnnexRepo
    # 6.20160923 -- --json-progress for get
    # 6.20161210 -- annex add  to add also changes (not only new files) to git
    # 6.20170220 -- annex status provides --ignore-submodules
    # 6.20180416 -- annex handles unicode filenames more uniformly
    # 6.20180913 -- annex fixes all known to us issues for v6
    # 7          -- annex makes v7 mode default on crippled systems. We demand it for consistent operation
    # 7.20190503 -- annex introduced mimeencoding support needed for our text2git
    #
    # When bumping this, check whether datalad.repo.version needs to be
    # adjusted.
    GIT_ANNEX_MIN_VERSION = '8.20200309'
    git_annex_version = None
    supports_direct_mode = None
    repository_versions = None
    _version_kludges = {}

    def __init__(self, path, runner=None,
                 backend=None, always_commit=True,
                 create=True, create_sanity_checks=True,
                 init=False, batch_size=None, version=None, description=None,
                 git_opts=None, annex_opts=None, annex_init_opts=None,
                 repo=None, fake_dates=False):
        """Creates representation of git-annex repository at `path`.

        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        Parameters
        ----------
        path: str
          Path to git-annex repository. In case it's not an absolute path, it's
          relative to PWD
        runner: Runner, optional
          Provide a Runner in case AnnexRepo shall not create it's own.
          This is especially needed in case of desired dry runs.
        backend: str, optional
          Set default backend used by this annex. This does NOT affect files,
          that are already annexed nor will it automatically migrate files,
          hat are 'getted' afterwards.
        create: bool, optional
          Create and initialize an annex repository at path, in case
          there is none. If set to False, and this repository is not an annex
          repository (initialized or not), an exception is raised.
        create_sanity_checks: bool, optional
          Passed to GitRepo.
        init: bool, optional
          Initialize git-annex repository (run "git annex init") if path is an
          annex repository which just was not yet initialized by annex (e.g. a
          fresh git clone). Note that if `create=True`, then initialization
          would happen
        batch_size: int, optional
          If specified and >0, instructs annex to batch this many commands before
          annex adds acts on git repository (e.g. adds them them to index for addurl).
        version: int, optional
          If given, pass as --version to `git annex init`
        description: str, optional
          Short description that humans can use to identify the
          repository/location, e.g. "Precious data on my laptop"
        """

        # BEGIN Repo validity test
        # We want to fail early for tests, that would be performed a lot. In particular this is about
        # AnnexRepo.is_valid_repo. We would use the latter to decide whether or not to call AnnexRepo() only for
        # __init__ to then test the same things again. If we fail early we can save the additional test from outer
        # scope.
        do_init = False
        super(AnnexRepo, self).__init__(
            path, runner=runner,
            create=create, create_sanity_checks=create_sanity_checks,
            repo=repo, git_opts=git_opts, fake_dates=fake_dates)

        # Check whether an annex already exists at destination
        # XXX this doesn't work for a submodule!

        # NOTE: We are in __init__ here and already know that GitRepo.is_valid_git is True, since super.__init__  was
        #       called. Therefore: check_git=False
        if not self.is_valid_annex(check_git=False):
            # so either it is not annex at all or just was not yet initialized
            # TODO: There's still potential to get a bit more performant. is_with_annex() is checking again, what
            #       is_valid_annex did. However, this marginal here, considering the call to git-annex-init.
            if self.is_with_annex():
                # it is an annex repository which was not initialized yet
                if create or init:
                    lgr.debug('Annex repository was not yet initialized at %s.'
                              ' Initializing ...' % self.path)
                    do_init = True
            elif create:
                lgr.debug('Initializing annex repository at %s...', self.path)
                do_init = True
            else:
                raise InvalidAnnexRepositoryError("No annex found at %s." % self.path)

        # END Repo validity test

        # initialize
        self._uuid = None
        self._annex_common_options = ["-c", "annex.dotfiles=true"]

        if annex_opts or annex_init_opts:
            lgr.warning("TODO: options passed to git-annex and/or "
                        "git-annex-init are currently ignored.\n"
                        "options received:\n"
                        "git-annex: %s\ngit-annex-init: %s" %
                        (annex_opts, annex_init_opts))

        # Below was initially introduced for setting for direct mode workaround,
        # where we changed _GIT_COMMON_OPTIONS and had to avoid passing
        # --worktree=. -c core.bare=False to git annex commands, so for their
        # invocation we kept and used pristine version of the
        # common options.  yoh thought it would be good to keep this as a copy
        # just in case we do need to pass annex specific options, even if
        # there is no need ATM
        self._ANNEX_GIT_COMMON_OPTIONS = self._GIT_COMMON_OPTIONS[:]
        self.always_commit = always_commit

        config = self.config
        if version is None:
            version = config.get("datalad.repo.version", None)
            # we might get an empty string here
            # TODO: if we use obtain() instead, we get an error complaining
            # '' cannot be converted to int (via Constraint as defined for
            # "datalad.repo.version" in common_cfg
            # => Allow conversion to result in None?
            if version:
                try:
                    version = int(version)
                except ValueError:
                    # Just give a warning if things look off and let
                    # git-annex-init complain if it can't actually handle it.
                    lgr.warning(
                        "Expected an int for datalad.repo.version, got %s",
                        version)
            else:
                # The above comment refers to an empty string case. The commit
                # (f12eb03f40) seems to deal with direct mode, so perhaps this
                # isn't reachable anymore.
                version = None

        if do_init:
            self._init(version=version, description=description)

        # TODO: RM DIRECT  eventually, but should remain while we have is_direct_mode
        self._direct_mode = None

        # Handle cases of detecting repositories with no longer supported
        # direct mode.
        # Could happen in case we didn't specify anything, but annex forced
        # direct mode due to FS or an already existing repo was in direct mode,
        if self._is_direct_mode_from_config():
            raise DirectModeNoLongerSupportedError(
                self,
                "Git configuration reports repository being in direct mode"
            )

        if config.getbool("datalad", "repo.direct", default=False):
            raise DirectModeNoLongerSupportedError(
                self,
                "datalad.repo.direct configuration instructs to use direct mode"
            )

        self._batched = BatchedAnnexes(
            batch_size=batch_size, git_options=self._ANNEX_GIT_COMMON_OPTIONS)

        # set default backend for future annex commands:
        # TODO: Should the backend option of __init__() also migrate
        # the annex, in case there are annexed files already?
        if backend:
            self.set_default_backend(backend, persistent=True)

        # will be evaluated lazily
        self._n_auto_jobs = None

        # Finally, register a finalizer (instead of having a __del__ method).
        # This will be called by garbage collection as well as "atexit". By
        # keeping the reference here, we can also call it explicitly.
        # Note, that we can pass required attributes to the finalizer, but not
        # `self` itself. This would create an additional reference to the object
        # and thereby preventing it from being collected at all.
        self._finalizer = finalize(self, AnnexRepo._cleanup, self.path,
                                   self._batched)

    def set_default_backend(self, backend, persistent=True, commit=True):
        """Set default backend

        Parameters
        ----------
        backend : str
        persistent : bool, optional
          If persistent, would add/commit to .gitattributes. If not -- would
          set within .git/config
        """
        if persistent:
            # could be set in .gitattributes or $GIT_DIR/info/attributes
            if 'annex.backend' in self.get_gitattributes('.')['.']:
                lgr.debug(
                    "Not (re)setting backend since seems already set in git attributes"
                )
            else:
                lgr.debug("Setting annex backend to %s (persistently)", backend)
                git_attributes_file = '.gitattributes'
                self.set_gitattributes(
                    [('*', {'annex.backend': backend})],
                    git_attributes_file)
                self.add(git_attributes_file, git=True)
                if commit:
                    self.commit(
                        "Set default backend for all files to be %s" % backend,
                        _datalad_msg=True,
                        files=[git_attributes_file]
                    )
        else:
            lgr.debug("Setting annex backend to %s (in .git/config)", backend)
            self.config.set('annex.backend', backend, scope='local')

    @classmethod
    def _cleanup(cls, path, batched):

        lgr.log(1, "Finalizer called on: AnnexRepo(%s)", path)

        # Ben: With switching to finalize rather than del, I think the
        #      safe_del_debug isn't needed anymore. However, time will tell and
        #      it doesn't hurt.

        def safe__del__debug(e):
            """We might be too late in the game and either .debug or exc_str
            are no longer bound"""
            try:
                return lgr.debug(str(e))
            except (AttributeError, NameError):
                return

        try:
            if batched is not None:
                batched.close()
        except TypeError as e:
            # Workaround:
            # most likely something wasn't accessible anymore; doesn't really
            # matter since we wanted to delete it anyway.
            #
            # Nevertheless, in some cases might be an issue and it is a strange
            # thing to happen, since we check for things being None herein as
            # well as in super class __del__;
            # At least log it:
            safe__del__debug(e)

    def is_managed_branch(self, branch=None):
        """Whether `branch` is managed by git-annex.

        ATM this returns True if on an adjusted branch of annex v6+ repository:
        either 'adjusted/my_branch(unlocked)' or 'adjusted/my_branch(fixed)'

        Note: The term 'managed branch' is used to make clear it's meant to be
        more general than the v6+ 'adjusted branch'.

        Parameters
        ----------
        branch: str
          name of the branch; default: active branch

        Returns
        -------
        bool
          True if on a managed branch, False otherwise
        """

        if branch is None:
            branch = self.get_active_branch()
        # Note: `branch` might still be None, due to detached HEAD
        # (or no checkout at all)
        return (branch and branch.startswith('adjusted/'))

    def get_corresponding_branch(self, branch=None):
        """Get the name of a potential corresponding branch.

        Parameters
        ----------
        branch: str, optional
          Name of the branch to report a corresponding branch for;
          defaults to active branch

        Returns
        -------
        str or None
          Name of the corresponding branch, or `None` if there is no
          corresponding branch.
        """

        if branch is None:
            branch = self.get_active_branch()

        if self.is_managed_branch(branch):
            if branch.startswith('adjusted/'):
                if branch.endswith('(unlocked)'):
                    cor_branch = branch[9:-10]
                elif branch.endswith('(fixed)'):
                    cor_branch = branch[9:-7]
                else:
                    cor_branch = branch[9:]
                    lgr.warning("Unexpected naming of adjusted branch '%s'.%s"
                                "Assuming '%s' to be the corresponding branch.",
                                branch, linesep, cor_branch)
            else:
                raise NotImplementedError(
                    "Detection of annex-managed branch '{}' follows a pattern "
                    "not implemented herein.".format(branch))
            return cor_branch

        else:
            return None

    def get_tracking_branch(self, branch=None, remote_only=False,
                            corresponding=True):
        """Get the tracking branch for `branch` if there is any.

        By default returns the tracking branch of the corresponding branch if
        `branch` is a managed branch.

        Parameters
        ----------
        branch: str
          local branch to look up. If none is given, active branch is used.
        remote_only : bool
            Don't return a value if the upstream remote is set to "." (meaning
            this repository).
        corresponding: bool
          If True actually look up the corresponding branch of `branch` (also if
          `branch` isn't explicitly given)

        Returns
        -------
        tuple
            (remote or None, refspec or None) of the tracking branch
        """

        if branch is None:
            branch = self.get_active_branch()

        return super(AnnexRepo, self).get_tracking_branch(
            remote_only=remote_only,
            branch=(self.get_corresponding_branch(branch) or branch)
            if corresponding else branch)

    @classmethod
    def _check_git_annex_version(cls):
        ver = external_versions['cmd:annex']
        # in case it is missing
        msg = "Visit http://handbook.datalad.org/r.html?install " \
              "for instructions on how to install DataLad and git-annex."

        exc_kwargs = dict(
            name="git-annex",
            msg=msg,
            ver=cls.GIT_ANNEX_MIN_VERSION
        )
        if not ver:
            raise MissingExternalDependency(**exc_kwargs)
        elif ver < cls.GIT_ANNEX_MIN_VERSION:
            raise OutdatedExternalDependency(ver_present=ver, **exc_kwargs)
        cls.git_annex_version = ver

    @classmethod
    def check_direct_mode_support(cls):
        """Does git-annex version support direct mode?

        The result is cached at `cls.supports_direct_mode`.

        Returns
        -------
        bool
        """
        if cls.supports_direct_mode is None:
            warnings.warn(
                "DataLad's minimum git-annex version is above 7.20190912, "
                "the last version to support direct mode. "
                "The check_direct_mode_support method "
                "and supports_direct_mode attribute will be removed "
                "in an upcoming release.",
                DeprecationWarning)
            cls.supports_direct_mode = False
        return cls.supports_direct_mode

    @classmethod
    def check_repository_versions(cls):
        """Get information on supported and upgradable repository versions.

        The result is cached at `cls.repository_versions`.

        Returns
        -------
        dict
          supported -> list of supported versions (int)
          upgradable -> list of upgradable versions (int)
        """
        if cls.repository_versions is None:
            key_remap = {
                "supported repository versions": "supported",
                "upgrade supported from repository versions": "upgradable"}
            out = GitWitlessRunner().run(
                ["git", "annex", "version"],
                protocol=StdOutErrCapture)
            kvs = (ln.split(":", 1) for ln in out['stdout'].splitlines())
            cls.repository_versions = {
                key_remap[k]: list(map(int, v.strip().split()))
                for k, v in kvs if k in key_remap}
        return cls.repository_versions

    @classmethod
    def _check_version_kludges(cls, key):
        """Cache some annex-version-specific kludges in one go.

        Return the kludge under `key`.
        """
        kludges = cls._version_kludges
        if kludges:
            return kludges[key]

        if cls.git_annex_version is None:
            cls._check_git_annex_version()

        ver = cls.git_annex_version
        kludges["fromkey-supports-unlocked"] = ver > "8.20210428"
        # applies to get, drop, move, copy, whereis
        kludges["grp1-supports-batch-keys"] = ver >= "8.20210903"
        # applies to find, findref to list all known.
        # was added in 10.20221212-17-g0b2dd374d on 20221220.
        kludges["find-supports-anything"] = ver >= "10.20221213"
        # applies to log, unannex and may be other commands,
        # was added 10.20230407 release, respecting core.quotepath
        kludges["quotepath-respected"] = \
            "yes" if ver >= '10.20230408' else \
            "maybe" if ver > '10.20230407' else \
            "no"
        cls._version_kludges = kludges
        return kludges[key]

    @classmethod
    def _unquote_annex_path(cls, s):
        """Remove surrounding "" around the filename, and unquote \"

        This is minimal necessary transformation of the quoted filename in care of
        core.quotepath=false, i.e. whenever all unicode characters remain as is.

        All interfaces should aim to operate on --json machine readable output,
        so we are not striving to have it super efficient here since should not be used
        often.
        """
        respected = cls._check_version_kludges('quotepath-respected')
        if respected == 'no':
            return s
        quoted = s.startswith('"') and s.endswith('"')
        if respected in ('maybe', 'yes'):
            # not necessarily correct if e.g. filename has "" around it originally
            # but this is a check only for a range of development versions, so mostly
            # for local/CI runs ATM
            if not quoted:
                return s
        else:
            raise RuntimeError(f"Got unknown {respected}")
        return s[1:-1].replace(r'\"', '"')

    @staticmethod
    def get_size_from_key(key):
        """A little helper to obtain size encoded in a key

        Returns
        -------
        int or None
          size of the file or None if either no size is encoded in the key or
          key was None itself

        Raises
        ------
        ValueError
          if key is considered invalid (at least its size-related part)
        """
        if not key:
            return None

        # see: https://git-annex.branchable.com/internals/key_format/
        key_parts = key.split('--')
        key_fields = key_parts[0].split('-')
        parsed = {field[0]: int(field[1:]) if field[1:].isdigit() else None
                  for field in key_fields[1:]
                  if field[0] in "sSC"}

        # don't lookup the dict for the same things several times;
        # Is there a faster (and more compact) way of doing this? Note, that
        # locals() can't be updated.
        s = parsed.get('s')
        S = parsed.get('S')
        C = parsed.get('C')

        if S is None and C is None:
            return s  # also okay if s is None as well -> no size to report
        elif s is None:
            # s is None, while S and/or C are not.
            raise ValueError("invalid key: {}".format(key))
        elif S and C:
            if C <= int(s / S):
                return S
            else:
                return s % S
        else:
            # S or C are given with the respective other one missing
            raise ValueError("invalid key: {}".format(key))

    @normalize_path
    def get_file_size(self, path):
        fpath = opj(self.path, path)
        return 0 if not exists(fpath) else os.stat(fpath).st_size

    def is_initialized(self):
        """quick check whether this appears to be an annex-init'ed repo
        """
        # intended to avoid calling self._init, when it's not needed, since this check is clearly
        # cheaper than git-annex-init (which would be safe to just call)

        return (self.dot_git / 'annex').exists()

    @borrowdoc(GitRepo, 'is_valid_git')
    def is_valid_annex(self, allow_noninitialized=False, check_git=True):

        initialized_annex = (self.is_valid_git() if check_git else True) and (self.dot_git / 'annex').exists()

        if allow_noninitialized:
            try:
                return initialized_annex or ((self.is_valid_git() if check_git else True) and self.is_with_annex())
            except (NoSuchPathError, InvalidGitRepositoryError):
                return False
        else:
            return initialized_annex

    @classmethod
    def is_valid_repo(cls, path, allow_noninitialized=False):
        """Return True if given path points to an annex repository
        """

        def git_file_has_annex(p):
            """Return True if `p` contains a .git file, that points to a git
            dir with a subdir 'annex'"""
            _git = opj(p, '.git')
            if not os.path.isfile(_git):
                return False
            with open(_git, "r") as f:
                line = f.readline()
                if line.startswith("gitdir: "):
                    return exists(opj(p, line[8:], 'annex'))
                else:
                    lgr.debug("Invalid .git file: %s", _git)
                    return False

        initialized_annex = GitRepo.is_valid_repo(path) and \
                            (exists(opj(path, '.git', 'annex')) or
                             git_file_has_annex(path))

        if allow_noninitialized:
            try:
                return initialized_annex or GitRepo(path, create=False, init=False).is_with_annex()
            except (NoSuchPathError, InvalidGitRepositoryError):
                return False
        else:
            return initialized_annex

    def set_remote_url(self, name, url, push=False):
        """Set the URL a remote is pointing to

        Sets the URL of the remote `name`. Requires the remote to already exist.

        Parameters
        ----------
        name: str
          name of the remote
        url: str
        push: bool
          if True, set the push URL, otherwise the fetch URL;
          if True, additionally set annexurl to `url`, to make sure annex uses
          it to talk to the remote, since access via fetch URL might be
          restricted.
        """

        if push:
            # if we are to set a push url, also set 'annexUrl' for this remote,
            # in order to make git-annex use it, when talking to the remote.
            # (see http://git-annex.branchable.com/bugs/annex_ignores_pushurl_and_uses_only_url_upon___34__copy_--to__34__/)
            var = 'remote.{0}.{1}'.format(name, 'annexurl')
            self.config.set(var, url, scope='local', reload=True)
        super(AnnexRepo, self).set_remote_url(name, url, push)

    def set_remote_dead(self, name):
        """Announce to annex that remote is "dead"
        """
        return self.call_annex(["dead", name])

    def is_remote_annex_ignored(self, remote):
        """Return True if remote is explicitly ignored"""
        return self.config.getbool(
            'remote.{}'.format(remote), 'annex-ignore',
            default=False
        )

    def is_special_annex_remote(self, remote, check_if_known=True):
        """Return whether remote is a special annex remote

        Decides based on the presence of an annex- option and lack of a
        configured URL for the remote.
        """
        if check_if_known:
            if remote not in self.get_remotes():
                raise RemoteNotAvailableError(remote)
        opts = self.config.options('remote.{}'.format(remote))
        if "url" in opts:
            is_special = False
        elif any(o.startswith("annex-") for o in opts
                 if o not in ["annex-uuid", "annex-ignore"]):
            # It's possible that there isn't a special-remote related option
            # (we only filter out a few common ones), but given that there is
            # no URL it should be a good bet that this is a special remote.
            is_special = True
        else:
            is_special = False
            lgr.warning("Remote '%s' has no URL or annex- option. "
                        "Is it mis-configured?",
                        remote)
        return is_special

    @borrowkwargs(GitRepo)
    def get_remotes(self,
                    with_urls_only=False,
                    exclude_special_remotes=False):
        """Get known (special-) remotes of the repository

        Parameters
        ----------
        exclude_special_remotes: bool, optional
          if True, don't return annex special remotes

        Returns
        -------
        remotes : list of str
          List of names of the remotes
        """
        remotes = super(AnnexRepo, self).get_remotes(with_urls_only=with_urls_only)

        if exclude_special_remotes:
            return [
                remote for remote in remotes
                if not self.is_special_annex_remote(remote, check_if_known=False)
            ]
        else:
            return remotes

    def get_special_remotes(self, include_dead:bool = False) -> Dict[str, dict]:
        """Get info about all known (not just enabled) special remotes.

        The present implementation is not able to report on special remotes
        that have only been configured in a private annex repo
        (annex.private=true).

        Parameters
        ----------
        include_dead: bool, optional
          Whether to include remotes announced dead.

        Returns
        -------
        dict
          Keys are special remote UUIDs. Each value is a dictionary with
          configuration information git-annex has for the remote. This should
          include the 'type' and 'name' as well as any `initremote` parameters
          that git-annex stores.

          Note: This is a faithful translation of git-annex:remote.log with one
          exception. For a special remote initialized with the --sameas flag,
          git-annex stores the special remote name under the "sameas-name" key,
          we copy this value under the "name" key so that callers don't have to
          check two places for the name. If you need to detect whether you're
          working with a sameas remote, the presence of either "sameas-name" or
          "sameas-uuid" is a reliable indicator.
        """
        argspec = re.compile(r'^([^=]*)=(.*)$')
        srs = {}

        # We provide custom implementation to access this metadata since ATM
        # no git-annex command exposes it on CLI.
        #
        # Information will potentially be obtained from remote.log within
        # git-annex branch, and git-annex's journal, which might exist e.g.
        # due to alwayscommit=false operations
        sources = []
        try:
            sources.append(
                list(
                    self.call_git_items_(
                        ['cat-file', 'blob', 'git-annex:remote.log'],
                        read_only=True)
                )
            )
        except CommandError as e:
            if (
                ('Not a valid object name git-annex:remote.log' in e.stderr) or  # e.g. git 2.30.2
                ("fatal: path 'remote.log' does not exist in 'git-annex'" in e.stderr) or # e.g. 2.35.1+next.20220211-1
                ("fatal: invalid object name 'git-annex'" in e.stderr) # e.g., 2.43.0
            ):
                # no special remotes configured - might still be in the journal
                pass
            else:
                # some unforeseen error
                raise e

        journal_path = self.dot_git / "annex" / "journal" / "remote.log"
        if journal_path.exists():
            sources.append(journal_path.read_text().splitlines())

        for line in chain(*sources):
            # be precise and split by spaces
            fields = line.split(' ')
            # special remote UUID
            sr_id = fields[0]
            # the rest are config args for enableremote
            sr_info = dict(argspec.match(arg).groups()[:2] for arg in fields[1:])
            if "name" not in sr_info:
                name = sr_info.get("sameas-name")
                if name is None:
                    lgr.warning(
                        "Encountered git-annex remote without a name or "
                        "sameas-name value: %s",
                        sr_info)
                else:
                    sr_info["name"] = name
            srs[sr_id] = sr_info

        # remove dead ones
        if not include_dead:
            # code largely copied from drop.py:_detect_nondead_annex_at_remotes
            # but not using -p and rather blob as above
            try:
                for line in self.call_git_items_(
                        ['cat-file', 'blob', 'git-annex:trust.log']):
                    columns = line.split()
                    if columns[1] == 'X':
                        # .pop if present
                        srs.pop(columns[0], None)
            except CommandError as e:
                # this is not a problem per-se, probably file is not there, just log
                CapturedException(e)
        return srs

    def _call_annex(self, args, files=None, jobs=None, protocol=StdOutErrCapture,
                    git_options=None, stdin=None, merge_annex_branches=True,
                    **kwargs):
        """Internal helper to run git-annex commands

        Standard command options are applied in addition to the given arguments,
        and certain error conditions are detected (if possible) and dedicated
        exceptions are raised.

        Parameters
        ----------
        args: list
          List of git-annex command arguments.
        files: list, optional
          If command passes list of files. If list is too long
          (by number of files or overall size) it will be split, and multiple
          command invocations will follow
        jobs : int or 'auto', optional
          If 'auto', the number of jobs will be determined automatically,
          informed by the configuration setting
          'datalad.runtime.max-annex-jobs'.
        protocol : WitlessProtocol, optional
          Protocol class to pass to GitWitlessRunner.run(). By default this is
          StdOutErrCapture, which will provide default logging behavior and
          guarantee that stdout/stderr are included in potential CommandError
          exception.
        git_options: list, optional
          Additional arguments for Git to include in the git-annex call
          (in a position prior to the 'annex' subcommand.
        stdin: File-like, optional
          stdin to connect to the git-annex process. Only used when `files`
          is None.
        merge_annex_branches: bool, optional
          If False, annex.merge-annex-branches=false config will be set for
          git-annex call.  Useful for operations which are not intended to
          benefit from updating information about remote git-annexes
        **kwargs:
          Additional arguments are passed on to the WitlessProtocol constructor

        Returns
        -------
        dict
          Return value of WitlessRunner.run(). The content of the dict is
          determined by the given `protocol`. By default, it provides git-annex's
          stdout and stderr (under these key names)

        Raises
        ------
        CommandError
          If the call exits with a non-zero status.

        OutOfSpaceError
          If a corresponding statement was detected in git-annex's output on
          stderr. Only supported if the given protocol captured stderr.

        RemoteNotAvailableError
          If a corresponding statement was detected in git-annex's output on
          stderr. Only supported if the given protocol captured stderr.
        """
        if self.git_annex_version is None:
            self._check_git_annex_version()

        # git portion of the command
        cmd = ['git'] + self._ANNEX_GIT_COMMON_OPTIONS

        if git_options:
            cmd += git_options

        if not self.always_commit:
            cmd += ['-c', 'annex.alwayscommit=false']

        if not merge_annex_branches:
            cmd += ['-c', 'annex.merge-annex-branches=false']

        # annex portion of the command
        cmd.append('annex')
        cmd += args

        if lgr.getEffectiveLevel() <= 8:
            cmd.append('--debug')

        if self._annex_common_options:
            cmd += self._annex_common_options

        if jobs == 'auto':
            # Limit to # of CPUs (but at least 3 to start with)
            # and also an additional config constraint (by default 1
            # due to https://github.com/datalad/datalad/issues/4404)
            jobs = self._n_auto_jobs or min(
                self.config.obtain('datalad.runtime.max-annex-jobs'),
                max(3, cpu_count()))
            # cache result to avoid repeated calls to cpu_count()
            self._n_auto_jobs = jobs
        if jobs and jobs != 1:
            cmd.append('-J%d' % jobs)

        runner = self._git_runner
        env = None
        if self.fake_dates_enabled:
            env = self.add_fake_dates(runner.env)

        try:
            if files:
                if issubclass(protocol, GeneratorMixIn):
                    return runner.run_on_filelist_chunks_items_(
                        cmd,
                        files,
                        protocol=protocol,
                        env=env,
                        **kwargs)
                else:
                    return runner.run_on_filelist_chunks(
                        cmd,
                        files,
                        protocol=protocol,
                        env=env,
                        **kwargs)
            else:
                return runner.run(
                    cmd,
                    stdin=stdin,
                    protocol=protocol,
                    env=env,
                    **kwargs)
        except CommandError as e:
            # Note: A call might result in several 'failures', that can be or
            # cannot be handled here. Detection of something, we can deal with,
            # doesn't mean there's nothing else to deal with.

            # OutOfSpaceError:
            # Note:
            # doesn't depend on anything in stdout. Therefore check this before
            # dealing with stdout
            out_of_space_re = re.search(
                "not enough free space, need (.*) more", e.stderr
            )
            if out_of_space_re:
                raise OutOfSpaceError(cmd=['annex'] + args,
                                      sizemore_msg=out_of_space_re.groups()[0])

            # RemoteNotAvailableError:
            remote_na_re = re.search(
                "there is no available git remote named \"(.*)\"", e.stderr
            )
            if remote_na_re:
                raise RemoteNotAvailableError(cmd=['annex'] + args,
                                              remote=remote_na_re.groups()[0])

            # TEMP: Workaround for git-annex bug, where it reports success=True
            # for annex add, while simultaneously complaining, that it is in
            # a submodule:
            # TODO: For now just reraise. But independently on this bug, it
            # makes sense to have an exception for that case
            in_subm_re = re.search(
                "fatal: Pathspec '(.*)' is in submodule '(.*)'", e.stderr
            )
            if in_subm_re:
                raise e

            # we don't know how to handle this, just pass it on
            raise

    def _call_annex_records(self, args, files=None, jobs=None,
                            git_options=None,
                            stdin=None,
                            merge_annex_branches=True,
                            progress=False,
                            **kwargs):
        """Internal helper to run git-annex commands with JSON result processing

        `_call_annex()` is used for git-annex command execution, using
        AnnexJsonProtocol.

        Parameters
        ----------
        args: list
          See `_call_annex()` for details.
        files: list, optional
          See `_call_annex()` for details.
        jobs : int or 'auto', optional
          See `_call_annex()` for details.
        git_options: list, optional
          See `_call_annex()` for details.
        stdin: File-like, optional
          See `_call_annex()` for details.
        merge_annex_branches: bool, optional
          See `_call_annex()` for details.
        **kwargs:
          Additional arguments are passed on to the AnnexJsonProtocol constructor

        Returns
        -------
        list(dict)
          List of parsed result records.

        Raises
        ------
        CommandError
          See `_call_annex()` for details.
        OutOfSpaceError
          See `_call_annex()` for details.
        RemoteNotAvailableError
          See `_call_annex()` for details.
        RuntimeError
          Output from the git-annex process was captured, but no structured
          records could be parsed.
        """
        protocol = AnnexJsonProtocol

        args = args[:] + ['--json', '--json-error-messages']
        if progress:
            args += ['--json-progress']

        out = None
        try:
            out = self._call_annex(
                args,
                files=files,
                jobs=jobs,
                protocol=protocol,
                git_options=git_options,
                stdin=stdin,
                merge_annex_branches=merge_annex_branches,
                **kwargs,
            )
        except CommandError as e:
            not_existing = None
            if e.kwargs.get('stdout_json'):
                # See if may be it was within stdout_json, as e.g. was added around
                # 10.20230407-99-gbe36e208c2 to 'add' together with
                # 'message-id': 'FileNotFound'
                out = {'stdout_json': e.kwargs.get('stdout_json', [])}
                not_existing = []
                for j in out['stdout_json']:
                    if j.get('message-id') == 'FileNotFound':
                        not_existing.append(j['file'])
                        # for consistency with our "_fake_json_for_non_existing" records
                        # but not overloading one if there is one
                        j.setdefault('note', 'not found')

            if not not_existing:
                # Workaround for not existing files as long as older annex doesn't
                # report it within JSON.
                # see http://git-annex.branchable.com/bugs/copy_does_not_reflect_some_failed_copies_in_--json_output/
                not_existing = _get_non_existing_from_annex_output(e.stderr)
                if not_existing:
                    if not out:
                        out = {'stdout_json': []}
                    out['stdout_json'].extend(_fake_json_for_non_existing(not_existing, args[0]))

            # Note: insert additional code here to analyse failure and possibly
            # raise a custom exception

            # If it was not about non-existing but running failed -- re-raise
            if not not_existing:
                raise e

            #if e.stderr:
            #    # else just warn about present errors
            #    shorten = lambda x: x[:1000] + '...' if len(x) > 1000 else x

            #    _log = lgr.debug if kwargs.get('expect_fail', False) else lgr.warning
            #    _log(
            #        "Running %s resulted in stderr output: %s",
            #        args, shorten(e.stderr)
            #    )

        # git-annex fails to non-zero exit when reporting an error on
        # non-existing paths in some versions and/or commands.
        # Hence, check for it on non-failure, too. This became apparent with
        # annex 10.20220222, but was a somewhat "hidden" issue for longer.
        #
        # Note, that this may become unnecessary after annex'
        # ce91f10132805d11448896304821b0aa9c6d9845 (Feb 28, 2022)
        # "fix annex.skipunknown false error propagation"
        if 'stderr' in out:
            not_existing = _get_non_existing_from_annex_output(out['stderr'])
            if not_existing:
                if out is None:
                    out = {'stdout_json': []}
                out['stdout_json'].extend(
                    _fake_json_for_non_existing(not_existing, args[0])
                )

        json_objects = out.pop('stdout_json')

        if out.get('stdout'):
            if json_objects:
                # We at least received some valid json output, so warn about
                # non-json output and continue.
                lgr.warning("Received non-json lines for --json command: %s",
                            out)
            else:
                raise RuntimeError(
                    "Received no json output for --json command, only:\n{}"
                    .format(out))

        # A special remote might send a message via "info". This is supposed
        # to be printed by annex but in case of
        # `--json` is returned by annex as "{'info': '<message>'}". See
        # https://git-annex.branchable.com/design/external_special_remote_protocol/#index5h2
        #
        # So, Ben thinks we should just spit it out here, since everything
        # calling _call_annex_records is concerned with the actual results
        # being returned. Moreover, this kind of response is special to
        # particular special remotes rather than particular annex commands.
        # So, likely there's nothing callers could do about it other than
        # spitting it out.
        return_objects = []
        for obj in json_objects:
            if len(obj.keys()) == 1 and obj['info']:
                lgr.info(obj['info'])
            else:
                return_objects.append(obj)

        return return_objects

    def _call_annex_records_items_(self,
                                   args,
                                   files=None,
                                   jobs=None,
                                   git_options=None,
                                   stdin=None,
                                   merge_annex_branches=True,
                                   progress=False,
                                   **kwargs):
        """Yielding git-annex command execution with JSON result processing

        `_call_annex()` is used for git-annex command execution, using
        GeneratorAnnexJsonProtocol. This means _call_annex() will yield
        results as soon as they are available.

        For a description of the parameters and raised exceptions, please
        refer to _call_annex_records().

        Returns
        -------
        Generator(something)
        list(dict)
          List of parsed result records.
        """
        protocol_class = GeneratorAnnexJsonProtocol

        args = args[:] + ['--json', '--json-error-messages']
        if progress:
            args += ['--json-progress']

        json_objects_received = False
        try:
            for json_object in self._call_annex(
                                      args,
                                      files=files,
                                      jobs=jobs,
                                      protocol=protocol_class,
                                      git_options=git_options,
                                      stdin=stdin,
                                      merge_annex_branches=merge_annex_branches,
                                      **kwargs):
                if len(json_object) == 1 and json_object.get('info', None):
                    lgr.info(json_object['info'])
                else:
                    json_objects_received = True
                    yield json_object

        except CommandError as e:
            # Note: Workaround for not existing files as long as annex doesn't
            # report it within JSON response:
            # see http://git-annex.branchable.com/bugs/copy_does_not_reflect_some_failed_copies_in_--json_output/
            not_existing = _get_non_existing_from_annex_output(e.stderr)
            yield from _fake_json_for_non_existing(not_existing, args[0])

            # Note: insert additional code here to analyse failure and possibly
            # raise a custom exception

            # if we didn't raise before, just depend on whether or not we seem
            # to have some json to return. It should contain information on
            # failure in keys 'success' and 'note'
            # TODO: This is not entirely true. 'annex status' may return empty,
            # while there was a 'fatal:...' in stderr, which should be a
            # failure/exception
            # Or if we had empty stdout but there was stderr
            if json_objects_received is False and e.stderr:
                raise e

        # In contrast to _call_annex_records, this method does not warn about
        # additional non-JSON data on stdout, nor does is raise a RuntimeError
        # if only non-JSON data was received on stdout.
        return

    def call_annex_records(self, args, files=None):
        """Call annex with `--json*` to request structured result records

        This method behaves like `call_annex()`, but returns parsed result
        records.

        Parameters
        ----------
        args : list of str
          Arguments to pass to `annex`.
        files : list of str, optional
          File arguments to pass to `annex`. The advantage of passing these here
          rather than as part of `args` is that the call will be split into
          multiple calls to avoid exceeding the maximum command line length.

        Returns
        -------
        list(dict)
          List of parsed result records.

        Raises
        ------
        CommandError if the call exits with a non-zero status. All result
        records captured until the non-zero exit are available in the
        exception's `kwargs`-dict attribute under key 'stdout_json'.

        See `_call_annex()` for more information on Exceptions.
        """
        return self._call_annex_records(args, files=files)

    def call_annex(self, args, files=None):
        """Call annex and return standard output.

        Parameters
        ----------
        args : list of str
          Arguments to pass to `annex`.
        files : list of str, optional
          File arguments to pass to `annex`. The advantage of passing these here
          rather than as part of `args` is that the call will be split into
          multiple calls to avoid exceeding the maximum command line length.

        Returns
        -------
        standard output (str)

        Raises
        ------
        See `_call_annex()` for information on Exceptions.
        """
        return self._call_annex(
            args,
            files=files,
            protocol=StdOutErrCapture)['stdout']

    def call_annex_success(self, args, files=None):
        """Call git-annex and return true if the call exit code of 0.

        All parameters match those described for `call_annex`.

        Returns
        -------
        bool
        """
        try:
            self.call_annex(args, files)
        except CommandError:
            return False
        return True

    def call_annex_items_(self, args, files=None, sep=None):
        """Call git-annex, splitting output on `sep`.

        Parameters
        ----------
        args : list of str
          Arguments to pass to `git-annex`.
        files : list of str, optional
          File arguments to pass to `annex`. The advantage of passing these here
          rather than as part of `args` is that the call will be split into
          multiple calls to avoid exceeding the maximum command line length.
        sep : str, optional
          Split the output by `str.split(sep)` rather than `str.splitlines`.

        Returns
        -------
        Generator that yields output items.

        Raises
        ------
        See `_call_annex()` for information on Exceptions.
        """
        class GeneratorStdOutErrCapture(GeneratorMixIn,
                                        AssemblingDecoderMixIn,
                                        StdOutErrCapture):
            def __init__(self):
                GeneratorMixIn.__init__(self)
                AssemblingDecoderMixIn.__init__(self)
                StdOutErrCapture.__init__(self)

            def pipe_data_received(self, fd, data):
                if fd == 1:
                    self.send_result(
                        ("stdout", self.decode(fd, data, self.encoding)))
                    return
                super().pipe_data_received(fd, data)

        line_splitter = LineSplitter(separator=sep)
        for source, content in self._call_annex(
                                args,
                                files=files,
                                protocol=GeneratorStdOutErrCapture):

            if source == "stdout":
                yield from line_splitter.process(content)

        remaining_content = line_splitter.finish_processing()
        if remaining_content is not None:
            yield remaining_content

    def call_annex_oneline(self, args, files=None):
        """Call annex for a single line of output.

        This method filters prior output line selection to exclude git-annex
        status output that is triggered by command execution, but is not
        related to the particular command. This includes lines like:

          (merging ... into git-annex)
          (recording state ...)

        Parameters
        ----------
        args : list of str
          Arguments to pass to `annex`.
        files : list of str, optional
          File arguments to pass to `annex`. The advantage of passing these here
          rather than as part of `args` is that the call will be split into
          multiple calls to avoid exceeding the maximum command line length.

        Returns
        -------
        str
          Either a single output line, or an empty string if there was no
          output.
        Raises
        ------
        AssertionError if there is more than one line of output.

        See `_call_annex()` for information on Exceptions.
        """
        # ignore some lines
        # see https://git-annex.branchable.com/todo/output_of_wanted___40__and_possibly_group_etc__41___should_not_be_polluted_with___34__informational__34___messages/
        # that links claims it is fixed, but '(recording state in git...)'
        # still appear as of 8.20201103-1
        lines = [
            l for l in self.call_annex_items_(args, files=files)
            if l and not re.search(
                r'\((merging .* into git-annex|recording state ).*\.\.\.\)', l
            )
        ]

        if len(lines) > 1:
            raise AssertionError(
                "Expected {} to return single line, but it returned {}"
                .format(["git", 'annex'] + args, lines))
        return lines[0] if lines else ''

    def _is_direct_mode_from_config(self):
        """Figure out if in direct mode from the git config.

        Since relies on reading config, expensive to be used often

        Returns
        -------
        True if in direct mode, False otherwise.
        """
        # If .git/config lacks an entry "direct",
        # it's actually indirect mode.
        self.config.reload()
        return self.config.getbool("annex", "direct", False)

    def is_direct_mode(self):
        """Return True if annex is in direct mode

        Returns
        -------
        True if in direct mode, False otherwise.
        """
        self._direct_mode = None

        if self._direct_mode is None:
            # we need to figure it out
            self._direct_mode = self._is_direct_mode_from_config()
        return self._direct_mode

    def is_crippled_fs(self):
        """Return True if git-annex considers current filesystem 'crippled'.

        Returns
        -------
        True if on crippled filesystem, False otherwise
        """

        self.config.reload()
        return self.config.getbool("annex", "crippledfilesystem", False)

    @property
    def supports_unlocked_pointers(self):
        """Return True if repository version supports unlocked pointers.
        """
        try:
            return self.config.getint("annex", "version") >= 6
        except KeyError:
            # If annex.version isn't set (e.g., an uninitialized repo), assume
            # that unlocked pointers are supported given that they are with the
            # minimum git-annex version.
            return True

    def _init(self, version=None, description=None):
        """Initializes an annex repository.

        Note: This is intended for private use in this class by now.
        If you have an object of this class already,
        there shouldn't be a need to 'init' again.

        """
        # MIH: this function is required for re-initing repos. The logic
        # in the constructor is rather convoluted and doesn't acknowledge
        # the case of a perfectly healthy annex that just needs a new
        # description
        # will keep leading underscore in the name for know, but this is
        # not private
        # TODO: provide git and git-annex options.
        opts = []
        if description is not None:
            opts += [description]
        if version is not None:
            version = str(version)
            supported_versions = AnnexRepo.check_repository_versions()['supported']
            if version not in supported_versions:
                first_supported_version = int(supported_versions[0])
                if int(version) < first_supported_version:
                    lgr.info("Annex repository version %s will be upgraded to %s or later version",
                             version, first_supported_version)
                    # and if it is higher than any supported -- we will just let git-annex to do
                    # what it wants to do
            opts += ['--version', '{0}'.format(version)]

        # TODO: RM DIRECT?  or RF at least ?
        # Note: git-annex-init kills a possible tracking branch for
        # 'annex/direct/my_branch', if we just cloned from a repo in direct
        # mode. We want to preserve the information about the tracking branch,
        # as if the source repo wasn't in direct mode.
        # Note 2: Actually we do it for all 'managed branches'. This might turn
        # out to not be necessary
        sections_to_preserve = ["branch.{}".format(branch)
                                for branch in self.get_branches()
                                if self.is_managed_branch(branch)
                                and "branch.{}".format(branch) in
                                self.config.sections()]
        for sct in sections_to_preserve:
            orig_branch = sct[7:]
            new_branch = \
                self.get_corresponding_branch(orig_branch) or orig_branch
            new_section = "branch.{}".format(new_branch)
            for opt in self.config.options(sct):
                orig_value = self.config.get_value(sct, opt)
                new_value = orig_value.replace(orig_branch, new_branch)
                self.config.add(var=new_section + "." + opt,
                                value=new_value,
                                scope='local',
                                reload=False)
        self._call_annex(['init'] + opts, protocol=AnnexInitOutput)
        # TODO: When to expect stderr?
        # on crippled filesystem for example (think so)?
        self.config.reload()

    @normalize_paths
    def get(self, files, remote=None, options=None, jobs=None, key=False):
        """Get the actual content of files

        Parameters
        ----------
        files : list of str
            paths to get
        remote : str, optional
            from which remote to fetch content
        options : list of str, optional
            commandline options for the git annex get command
        jobs : int or None, optional
            how many jobs to run in parallel (passed to git-annex call).
            If not specified (None), then
        key : bool, optional
            If provided file value is actually a key

        Returns
        -------
        files : list of dict
        """
        options = options[:] if options else []

        if self.config.get("annex.retry") is None:
            options.extend(
                ["-c",
                 "annex.retry={}".format(
                     self.config.obtain("datalad.annex.retry"))])

        if remote:
            if remote not in self.get_remotes():
                raise RemoteNotAvailableError(
                    remote=remote,
                    cmd="annex get",
                    msg="Remote is not known. Known are: %s"
                    % (self.get_remotes(),)
                )
            self._maybe_open_ssh_connection(remote)
            options += ['--from', remote]

        # analyze provided files to decide which actually are needed to be
        # fetched

        if not key:
            expected_downloads, fetch_files = self._get_expected_files(
                files, ['--not', '--in', '.'],
                merge_annex_branches=False  # interested only in local info
            )
        else:
            fetch_files = files
            assert len(files) == 1, "When key=True only a single file be provided"
            expected_downloads = {files[0]: AnnexRepo.get_size_from_key(files[0])}

        if not fetch_files:
            lgr.debug("No files found needing fetching.")
            return []

        if len(fetch_files) != len(files):
            lgr.debug("Actually getting %d files", len(fetch_files))

        # TODO: provide more meaningful message (possibly aggregating 'note'
        #  from annex failed ones
        # TODO: reproduce DK's bug on OSX, and either switch to
        #  --batch mode (I don't think we have --progress support in long
        #  alive batch processes ATM),
        if key:
            cmd = ['get'] + options + ['--key'] + files
            files_arg = None
        else:
            cmd = ['get'] + options
            files_arg = files
        results = self._call_annex_records(
            cmd,
            # TODO: eventually make use of --batch mode
            files=files_arg,
            jobs=jobs,
            progress=True,
            # filter(bool,   to avoid trying to add up None's when size is not known
            total_nbytes=sum(filter(bool, expected_downloads.values())),
        )
        results_list = list(results)
        # TODO:  should we here compare fetch_files against result_list
        # and vomit an exception of incomplete download????
        return results_list

    def _get_expected_files(self, files, expr, merge_annex_branches=True):
        """Given a list of files, figure out what to be downloaded

        Parameters
        ----------
        files
        expr: list
          Expression to be passed into annex's find

        Returns
        -------
        expected_files : dict
          key -> size
        fetch_files : list
          files to be fetched
        """
        lgr.debug("Determine what files match the query to work with")
        # Let's figure out first which files/keys and of what size to download
        expected_files = {}
        fetch_files = []
        keys_seen = set()
        unknown_sizes = []  # unused atm
        # for now just record total size, and
        for j in self._call_annex_records(
                ['find'] + expr, files=files,
                merge_annex_branches=merge_annex_branches
        ):
            # TODO: some files might not even be here.  So in current fancy
            # output reporting scheme we should then theoretically handle
            # those cases here and say 'impossible' or something like that
            if not j.get('success', True):
                # TODO: I guess do something with yielding and filtering for
                # what need to be done and what not
                continue
            key = j['key']
            size = j.get('bytesize')
            if key in keys_seen:
                # multiple files could point to the same key.  no need to
                # request multiple times
                continue
            keys_seen.add(key)
            assert j['file']
            fetch_files.append(j['file'])
            if size and size.isdigit():
                expected_files[key] = int(size)
            else:
                expected_files[key] = None
                unknown_sizes.append(j['file'])
        return expected_files, fetch_files

    @normalize_paths
    def add(self, files, git=None, backend=None, options=None, jobs=None,
            git_options=None, annex_options=None, update=False):
        """Add file(s) to the repository.

        Parameters
        ----------
        files: list of str
          list of paths to add to the annex
        git: bool
          if True, add to git instead of annex.
        backend:
        options:
        update: bool
          --update option for git-add. From git's manpage:
           Update the index just where it already has an entry matching
           <pathspec>. This removes as well as modifies index entries to match
           the working tree, but adds no new files.

           If no <pathspec> is given when --update option is used, all tracked
           files in the entire working tree are updated (old versions of Git
           used to limit the update to the current directory and its
           subdirectories).

           Note: Used only, if a call to git-add instead of git-annex-add is
           performed

        Returns
        -------
        list of dict or dict
        """

        return list(self.add_(
            files, git=git, backend=backend, options=options, jobs=jobs,
            git_options=git_options, annex_options=annex_options, update=update
        ))

    def add_(self, files, git=None, backend=None, options=None, jobs=None,
            git_options=None, annex_options=None, update=False):
        """Like `add`, but returns a generator"""
        if update and not git:
            raise InsufficientArgumentsError("option 'update' requires 'git', too")

        if git_options:
            # TODO: note that below we would use 'add with --dry-run
            # so passed here options might need to be passed into it??
            lgr.warning("add: git_options not yet implemented. Ignored.")

        if annex_options:
            lgr.warning("annex_options not yet implemented. Ignored.")

        options = options[:] if options else []

        # TODO: RM DIRECT? not clear if this code didn't become "generic" and
        #       not only "direct mode" specific, so kept for now.
        # Note: As long as we support direct mode, one should not call
        # super().add() directly. Once direct mode is gone, we might remove
        # `git` parameter and call GitRepo's add() instead.

        def _get_to_be_added_recs(paths):
            """Try to collect what actually is going to be added

            This is used for progress information
            """

            # TODO: RM DIRECT? might remain useful to detect submods left in direct mode
            # Note: if a path involves a submodule in direct mode, while we
            # are not in direct mode at current level, we might still fail.
            # Hence the except clause is still needed. However, this is
            # unlikely, since direct mode usually should be used only, if it
            # was enforced by FS and/or OS and therefore concerns the entire
            # hierarchy.
            _git_options = ['--dry-run', '-N', '--ignore-missing']
            try:
                for r in super(AnnexRepo, self).add_(
                        files, git_options=_git_options, update=update):
                    yield r
                    return
            except CommandError as e:
                ce = CapturedException(e)
                # TODO: RM DIRECT?  left for detection of direct mode submodules
                if AnnexRepo._is_annex_work_tree_message(e.stderr):
                    raise DirectModeNoLongerSupportedError(
                        self) from e
                raise

        # Theoretically we could have done for git as well, if it could have
        # been batched
        # Call git annex add for any to have full control of whether to go
        # to git or to annex
        # 1. Figure out what actually will be added
        to_be_added_recs = _get_to_be_added_recs(files)
        # collect their sizes for the progressbar
        expected_additions = {
            rec['file']: self.get_file_size(rec['file'])
            for rec in to_be_added_recs
        }

        # if None -- leave it to annex to decide
        if git is False:
            options.append("--force-large")

        if git:
            # explicitly use git-add with --update instead of git-annex-add
            # TODO: This might still need some work, when --update AND files
            # are specified!
            for r in super(AnnexRepo, self).add(
                    files,
                    git=True,
                    git_options=git_options,
                    update=update):
                yield r

        else:
            if backend:
                options.extend(('--backend', backend))
            for r in self._call_annex_records(
                    ['add'] + options,
                    files=files,
                    jobs=jobs,
                    total_nbytes=sum(expected_additions.values())):
                yield r

    @normalize_paths
    def get_file_key(self, files, batch=None):
        """DEPRECATED. Use get_content_annexinfo()

        See the method body for how to use get_content_annexinfo() to
        replace get_file_key().

        For single-file queries it is recommended to consider
        get_file_annexinfo()
        """
        import warnings
        warnings.warn(
            "AnnexRepo.get_file_key() is deprecated, "
            "use get_content_annexinfo() instead.",
            DeprecationWarning)

        # this is only needed, because a previous implementation wanted to
        # disect reasons for not being able to report a key: file not there,
        # file in git, but not annexed. If not for that, this could be
        #init = None
        init = dict(
            zip(
                [self.pathobj / f for f in files],
                [{} for i in range(len(files))]
            )
        )
        info = self.get_content_annexinfo(
            files,
            init=init,
        )
        keys = [r.get('key', '') for r in info.values()]

        # everything below is only needed to achieve compatibility with the
        # complex behavior of a previous implementation if not for that, we
        # could achieve uniform behavior regardless of input specifics with a
        # simple
        #return keys

        if batch is not True and len(files) == 1 and '' in keys:
            not_found = [
                p
                for p, r in info.items()
                if r.get('success') is False and r.get('note') == 'not found'
            ]
            if not_found:
                raise FileNotInAnnexError(
                    cmd='find',
                    msg=f"File not in annex: {not_found}",
                    filename=not_found)

            no_annex = [p for p, r in info.items() if not r]
            if no_annex:
                raise FileInGitError(
                    cmd='find',
                    msg=f"File not in annex, but git: {no_annex}",
                    filename=no_annex)

        if batch is True and len(files) == 1 and len(keys) == 1:
            keys = keys[0]

        return keys

    @normalize_paths
    def unlock(self, files):
        """unlock files for modification

        Note: This method is silent about errors in unlocking a file (e.g, the
        file has not content). Use the higher-level interface.unlock to get
        more informative reporting.

        Parameters
        ----------
        files: list of str

        Returns
        -------
        list of str
          successfully unlocked files
        """
        if not files:
            return
        return [j["file"] for j in
                self.call_annex_records(["unlock"], files=files)
                if j["success"]]

    def adjust(self, options=None):
        """enter an adjusted branch

        This command is only available in a v6+ git-annex repository.

        Parameters
        ----------
        options: list of str
          currently requires '--unlock' or '--fix';
          default: --unlock
        """
        # TODO: Do we want to catch the case that
        # "adjusted/<current_branch_name>(unlocked)" already exists and
        # just check it out? Or fail like annex itself does?

        # version check:
        if not self.supports_unlocked_pointers:
            raise CommandNotAvailableError(
                cmd='git annex adjust',
                msg=('git-annex-adjust requires a '
                     'version that supports unlocked pointers'))

        options = options[:] if options else to_options(unlock=True)
        self.call_annex(['adjust'] + options)

    @normalize_paths
    def unannex(self, files, options=None):
        """undo accidental add command

        Use this to undo an accidental git annex add command. Note that for
        safety, the content of the file remains in the annex, until you use git
        annex unused and git annex dropunused.

        Parameters
        ----------
        files: list of str
        options: list of str

        Returns
        -------
        list of str
          successfully unannexed files
        """

        options = options[:] if options else []
        prefix = 'unannex'
        suffix = 'ok'
        return [
            # we cannot .split here since filename could have spaces
            self._unquote_annex_path(line[len(prefix) + 1 : -(len(suffix) + 1)])
            for line in self.call_annex_items_(['unannex'] + options, files=files)
            if line.split()[0] == prefix and line.split()[-1] == suffix
        ]

    @normalize_paths(map_filenames_back=True)
    def find(self, files, batch=False):
        """Run `git annex find` on file(s).

        Parameters
        ----------
        files: list of str
            files to find under annex
        batch: bool, optional
            initiate or continue with a batched run of annex find, instead of just
            calling a single git annex find command. If any items in `files`
            are directories, this value is treated as False.

        Returns
        -------
        A dictionary the maps each item in `files` to its `git annex find`
        result. Items without a successful result will be an empty string, and
        multi-item results (which can occur for if `files` includes a
        directory) will be returned as a list.
        """
        objects = {}
        # Ignore batch=True if any path is a directory because `git annex find
        # --batch` always returns an empty string for directories.
        if batch and not any(isdir(opj(self.path, f)) for f in files):
            find = self._batched.get(
                'find', json=True, path=self.path,
                # Since we are just interested in local information
                git_options=['-c', 'annex.merge-annex-branches=false']
            )
            objects = {f: json_out.get("file", "")
                       for f, json_out in zip(files, find(files))}
        else:
            for f in files:
                try:
                    res = self._call_annex(
                        ['find', "--print0"],
                        files=[f],
                        merge_annex_branches=False,
                    )
                    items = res['stdout'].rstrip("\0").split("\0")
                    objects[f] = items[0] if len(items) == 1 else items
                except CommandError:
                    objects[f] = ''

        return objects

    def _check_files(self, fn, files, batch):
        # Helper that isolates the common logic in `file_has_content` and
        # `is_under_annex`. `fn` is the annex command used to do the check, and
        # `quick_fn` is the non-annex variant.
        pointers = self.supports_unlocked_pointers
        # We're only concerned about modified files in V6+ mode. In V5
        # `find` returns an empty string for unlocked files.
        #
        # ATTN: test_AnnexRepo_file_has_content has a failure before Git
        # v2.13 (tested back to v2.9) because this diff call unexpectedly
        # reports a type change as modified.
        modified = {
            f for f in self.call_git_items_(
                ['diff', '--name-only', '-z'], sep='\0')
            if f
        } if pointers else set()
        annex_res = fn(files, normalize_paths=False, batch=batch)
        return [bool(annex_res.get(f) and
                     not (pointers and normpath(f) in modified))
                for f in files]

    @normalize_paths
    def file_has_content(self, files, allow_quick=False, batch=False):
        """Check whether files have their content present under annex.

        Parameters
        ----------
        files: list of str
            file(s) to check for being actually present.
        allow_quick: bool, optional
            This is no longer supported.

        Returns
        -------
        list of bool
            For each input file states whether file has content locally
        """
        # TODO: Also provide option to look for key instead of path
        return self._check_files(self.find, files, batch)

    @normalize_paths
    def is_under_annex(self, files, allow_quick=False, batch=False):
        """Check whether files are under annex control

        Parameters
        ----------
        files: list of str
            file(s) to check for being under annex
        allow_quick: bool, optional
            This is no longer supported.

        Returns
        -------
        list of bool
            For each input file states whether file is under annex
        """
        # theoretically in direct mode files without content would also be
        # broken symlinks on the FSs which support it, but that would complicate
        # the matters

        # This is an ugly hack to prevent files from being treated as
        # remotes by `git annex info`. See annex's `nameToUUID'`.
        files = [opj(curdir, f) for f in files]

        def check(files, **kwargs):
            # Filter out directories because it doesn't make sense to ask if
            # they are under annex control and `info` can only handle
            # non-directories.
            return self.info([f for f in files if not isdir(f)],
                             fast=True, **kwargs)

        return self._check_files(check, files, batch)

    def init_remote(self, name, options):
        """Creates a new special remote

        Parameters
        ----------
        name: str
            name of the special remote
        """
        # TODO: figure out consistent way for passing options + document
        self.call_annex(['initremote'] + [name] + options)
        self.config.reload()

    def enable_remote(self, name, options=None, env=None):
        """Enables use of an existing special remote

        Parameters
        ----------
        name: str
            name, the special remote was created with
        options: list, optional
        """

        # MIH thinks there should be no `env` argument at all
        # https://github.com/datalad/datalad/issues/5162
        env = env or self._git_runner.env
        try:
            from unittest.mock import patch
            with patch.object(self._git_runner, 'env', env):
                # TODO: outputs are nohow used/displayed. Eventually convert to
                # to a generator style yielding our "dict records"
                self.call_annex(['enableremote', name] + ensure_list(options))
        except CommandError as e:
            if re.match(r'.*StatusCodeException.*statusCode = 401', e.stderr):
                raise AccessDeniedError(e.stderr)
            elif 'FailedConnectionException' in e.stderr:
                raise AccessFailedError(e.stderr)
            else:
                raise e
        self.config.reload()

    def merge_annex(self, remote=None):  # do not use anymore, use localsync()
        self.localsync(remote)

    def sync(self, remotes=None, push=True, pull=True, commit=True,
             content=False, all=False, fast=False):
        """This method is deprecated, use call_annex(['sync', ...]) instead.

        Synchronize local repository with remotes

        Use  this  command  when you want to synchronize the local repository
        with one or more of its remotes. You can specify the remotes (or
        remote groups) to sync with by name; the default if none are specified
        is to sync with all remotes.

        Parameters
        ----------
        remotes: str, list(str), optional
          Name of one or more remotes to be sync'ed.
        push : bool
          By default, git pushes to remotes.
        pull : bool
          By default, git pulls from remotes
        commit : bool
          A commit is done by default. Disable to avoid  committing local
          changes.
        content : bool
          Normally, syncing does not transfer the contents of annexed
          files.  This option causes the content of files in the work tree
          to also be uploaded and downloaded as necessary.
        all : bool
          This option, when combined with `content`, makes all available
          versions of all files be synced, when preferred content settings
          allow
        fast : bool
          Only sync with the remotes with the lowest annex-cost value
          configured
        """
        import warnings
        warnings.warn(
            "AnnexRepo.sync() is deprecated, use call_annex(['sync', ...]) "
            "instead.",
            DeprecationWarning)
        args = []
        args.extend(to_options(push=push, no_push=not push,
                               # means: '--push' if push else '--no-push'
                               pull=pull, no_pull=not pull,
                               commit=commit, no_commit=not commit,
                               content=content, no_content=not content,
                               all=all,
                               fast=fast))
        args.extend(ensure_list(remotes))
        self.call_annex(['sync'] + args)

    @normalize_path
    def add_url_to_file(self, file_, url, options=None, backend=None,
                        batch=False, git_options=None, annex_options=None,
                        unlink_existing=False):
        """Add file from url to the annex.

        Downloads `file` from `url` and add it to the annex.
        If annex knows `file` already,
        records that it can be downloaded from `url`.

        Note: Consider using the higher-level `download_url` instead.

        Parameters
        ----------
        file_: str

        url: str

        options: list
            options to the annex command

        batch: bool, optional
            initiate or continue with a batched run of annex addurl, instead of just
            calling a single git annex addurl command

        unlink_existing: bool, optional
            by default crashes if file already exists and is under git.
            With this flag set to True would first remove it.

        Returns
        -------
        dict
          In batch mode only ATM returns dict representation of json output returned
          by annex
        """

        if git_options:
            lgr.warning("add_url_to_file: git_options not yet implemented. Ignored.")

        if annex_options:
            lgr.warning("annex_options not yet implemented. Ignored.")

        options = options[:] if options else []
        if backend:
            options.extend(('--backend', backend))
        git_options = []
        if lexists(opj(self.path, file_)) and \
                unlink_existing and \
                not self.is_under_annex(file_):
            # already under git, we can't addurl for under annex
            lgr.warning(
                "File %s:%s is already under git, removing so it could possibly"
                " be added under annex", self, file_
            )
            unlink(opj(self.path, file_))
        if not batch or self.fake_dates_enabled:
            if batch:
                lgr.debug("Not batching addurl call "
                          "because fake dates are enabled")
            files_opt = '--file=%s' % file_
            out_json = self._call_annex_records(
                ['addurl'] + options + [files_opt] + [url],
                progress=True,
            )
            if len(out_json) != 1:
                raise AssertionError(
                    "should always be a single-item list, Got: %s"
                    % str(out_json))
            # Make the output's structure match bcmd's.
            out_json = out_json[0]
            # Don't capture stderr, since download progress provided by wget
            # uses stderr.
        else:
            options += ['--with-files']
            if backend:
                options += ['--backend=%s' % backend]
            # Initializes (if necessary) and obtains the batch process
            bcmd = self._batched.get(
                # Since backend will be critical for non-existing files
                'addurl_to_file_backend:%s' % backend,
                annex_cmd='addurl',
                git_options=git_options,
                annex_options=options,  # --raw ?
                path=self.path,
                json=True
            )
            try:
                out_json = bcmd((url, file_))
            except Exception as exc:
                # if isinstance(exc, IOError):
                #     raise
                raise AnnexBatchCommandError(
                    cmd="addurl",
                    msg="Adding url %s to file %s failed" % (url, file_)) from exc
            assert \
                (out_json.get('command') == 'addurl'), \
                "no exception was raised and no 'command' in result out_json=%s" % str(out_json)
        if not out_json.get('success', False):
            raise (AnnexBatchCommandError if batch else CommandError)(
                    cmd="addurl",
                    msg="Error, annex reported failure for addurl (url='%s'): %s"
                    % (url, str(out_json)))
        return out_json

    def add_urls(self, urls, options=None, backend=None, cwd=None,
                 jobs=None,
                 git_options=None, annex_options=None):
        """Downloads each url to its own file, which is added to the annex.

        .. deprecated:: 0.17
            Use add_url_to_file() or call_annex() instead.

        Parameters
        ----------
        urls: list of str

        options: list, optional
            options to the annex command

        cwd: string, optional
            working directory from within which to invoke git-annex
        """
        warnings.warn(
            "AnnexRepo.add_urls() is deprecated and will be removed in a "
            "future release. Use AnnexRepo.add_url_to_file() or "
            "AnnexRepo.call_annex() instead.",
            DeprecationWarning)

        if git_options:
            lgr.warning("add_urls: git_options not yet implemented. Ignored.")

        git_options = []
        if cwd:
            git_options.extend(('-C', cwd))

        if annex_options:
            lgr.warning("annex_options not yet implemented. Ignored.")

        options = options[:] if options else []

        if backend:
            options.extend(('--backend', backend))

        return self._call_annex_records(
            ['addurl'] + options + urls,
            git_options=git_options,
            progress=True)

    @normalize_path
    def rm_url(self, file_, url):
        """Record that the file is no longer available at the url.

        Parameters
        ----------
        file_: str

        url: str
        """
        self.call_annex(['rmurl'], files=[file_, url])

    @normalize_path
    def get_urls(self, file_, key=False, batch=False):
        """Get URLs for a file/key

        Parameters
        ----------
        file_: str
        key: bool, optional
            Whether provided files are actually annex keys

        Returns
        -------
        A list of URLs
        """
        locations = self.whereis(file_, output='full', key=key, batch=batch)
        return locations.get(WEB_SPECIAL_REMOTE_UUID, {}).get('urls', [])

    @normalize_paths
    def drop(self, files, options=None, key=False, jobs=None):
        """Drops the content of annexed files from this repository.

        Drops only if possible with respect to required minimal number of
        available copies.

        Parameters
        ----------
        files: list of str
            paths to drop
        options : list of str, optional
            commandline options for the git annex drop command
        jobs : int, optional
            how many jobs to run in parallel (passed to git-annex call)

        Returns
        -------
        list(JSON objects)
          'success' item in each object indicates failure/success per file
          path.
        """

        # annex drop takes either files or options
        # --all, --unused, --key, or --incomplete
        # for now, most simple test; to be replaced by a more general solution
        # (exception thrown by _run_annex_command)
        if not files and \
                (not options or
                 not any([o in options for o in
                          ["--all", "--unused", "--key", "--incomplete"]])):
            raise InsufficientArgumentsError("drop() requires at least to "
                                             "specify 'files' or 'options'")

        options = ensure_list(options)

        if key:
            # we can't drop multiple in 1 line, and there is no --batch yet, so
            # one at a time
            files = ensure_list(files)
            options = options + ['--key']
            res = [
                self._call_annex_records(
                    ['drop'] + options + [k],
                    jobs=jobs)
                for k in files
            ]
            # `normalize_paths` ... magic, useful?
            if len(files) == 1:
                return res[0]
            else:
                return res
        else:
            return self._call_annex_records(
                ['drop'] + options,
                files=files,
                jobs=jobs)

    def drop_key(self, keys, options=None, batch=False):
        """Drops the content of annexed files from this repository referenced by keys

        Dangerous: it drops without checking for required minimal number of
        available copies.

        Parameters
        ----------
        keys: list of str, str

        batch: bool, optional
            initiate or continue with a batched run of annex dropkey, instead of just
            calling a single git annex dropkey command
        """
        keys = [keys] if isinstance(keys, str) else keys

        options = options[:] if options else []
        options += ['--force']
        if not batch or self.fake_dates_enabled:
            if batch:
                lgr.debug("Not batching drop_key call "
                          "because fake dates are enabled")
            json_objects = self.call_annex_records(
                ['dropkey'] + options, files=keys
            )
        else:
            json_objects = self._batched.get(
                'dropkey',
                annex_options=options, json=True, path=self.path
            )(keys)
        # TODO: RF to be consistent with the rest (IncompleteResultError or alike)
        # and/or completely refactor since drop above also has key option
        for j in json_objects:
            assert j.get('success', True)

    # TODO: a dedicated unit-test
    def _whereis_json_to_dict(self, j):
        """Convert json record returned by annex whereis --json to our dict representation for it
        """
        # process 'whereis' containing list of remotes
        remotes = {remote['uuid']: {x: remote.get(x, None)
                                    for x in ('description', 'here', 'urls')
                                    }
                   for remote in j['whereis']}
        return remotes

    # TODO: reconsider having any magic at all and maybe just return a list/dict always
    @normalize_paths
    def whereis(self, files, output='uuids', key=False, options=None, batch=False):
        """Lists repositories that have actual content of file(s).

        Parameters
        ----------
        files: list of str
            files to look for
        output: {'descriptions', 'uuids', 'full'}, optional
            If 'descriptions', a list of remotes descriptions returned is per
            each file. If 'full', for each file a dictionary of all fields
            is returned as returned by annex
        key: bool, optional
            Whether provided files are actually annex keys
        options: list, optional
            Options to pass into git-annex call

        Returns
        -------
        list of list of unicode  or dict
            if output == 'descriptions', contains a list of descriptions of remotes
            for each input file, describing the remote for each remote, which
            was found by git-annex whereis, like::

                u'me@mycomputer:~/where/my/repo/is [origin]' or
                u'web' or
                u'me@mycomputer:~/some/other/clone'

            if output == 'uuids', returns a list of uuids.
            if output == 'full', returns a dictionary with filenames as keys
            and values a detailed record, e.g.::

                {'00000000-0000-0000-0000-000000000001': {
                  'description': 'web',
                  'here': False,
                  'urls': ['http://127.0.0.1:43442/about.txt', 'http://example.com/someurl']
                }}
        """
        OUTPUTS = {'descriptions', 'uuids', 'full'}
        if output not in OUTPUTS:
            raise ValueError(
                "Unknown value output=%r. Known are %s"
                % (output, ', '.join(map(repr, OUTPUTS)))
            )

        options = ensure_list(options, copy=True)
        if batch:
            # TODO: --batch-keys was added to 8.20210903
            if key:
                if not self._check_version_kludges("grp1-supports-batch-keys"):
                    raise ValueError("batch=True for `key=True` requires git-annex >= 8.20210903")
                bkw = {'batch_opt': '--batch-keys'}
            else:
                bkw = {}
            bcmd = self._batched.get('whereis', annex_options=options,
                                     json=True, path=self.path, **bkw)
            json_objects = bcmd(files)
        else:
            cmd = ['whereis'] + options

            def _call_cmd(cmd, files=None):
                """Helper to reuse consistently in case of --key and not invocations"""
                try:
                    return self.call_annex_records(cmd, files=files)
                except CommandError as e:
                    if e.stderr.startswith('Invalid'):
                        # would happen when git-annex is called with incompatible options
                        raise
                    # whereis may exit non-zero when there are too few known copies
                    # callers of whereis are interested in exactly that information,
                    # which we deliver via result, not via exception
                    return e.kwargs.get('stdout_json', [])

            if key:
                # whereis --key takes only a single key at a time so we need to loop
                json_objects = []
                for k in files:
                    json_objects.extend(_call_cmd(cmd + ["--key", k]))
            else:
                json_objects = _call_cmd(cmd, files)

        # json_objects can contain entries w/o a "whereis" field. Unknown to
        # git paths in particular are returned in such records. Code below is
        # only concerned with actual whereis results.
        whereis_json_objects = [o for o in json_objects if "whereis" in
                                o.keys()]

        if output in {'descriptions', 'uuids'}:
            return [
                [remote.get(output[:-1]) for remote in j.get('whereis')]
                if j.get('success') else []
                for j in whereis_json_objects
            ]
        elif output == 'full':
            # TODO: we might want to optimize storage since many remotes entries will be the
            # same so we could just reuse them instead of brewing copies
            return {
                j['key']
                if (key or '--all' in options)
                # report is always POSIX, but normalize_paths wants to match against
                # the native representation
                else str(Path(PurePosixPath(j['file'])))
                if on_windows else j['file']
                : self._whereis_json_to_dict(j)
                for j in whereis_json_objects
                if not j.get('key', '').endswith('.this-is-a-test-key')
            }

    # TODO:
    # I think we should make interface cleaner and less ambiguous for those annex
    # commands which could operate on globs, files, and entire repositories, separating
    # those out, e.g. annex_info_repo, annex_info_files at least.
    # If we make our calling wrappers work without relying on invoking from repo topdir,
    # then returned filenames would not need to be mapped, so we could easily work on dirs
    # and globs.
    # OR if explicit filenames list - return list of matching entries, if globs/dirs -- return dict?
    @normalize_paths(map_filenames_back=True)
    def info(self, files, batch=False, fast=False):
        """Provide annex info for file(s).

        Parameters
        ----------
        files: list of str
            files to look for

        Returns
        -------
        dict
          Info for each file
        """

        options = ['--bytes', '--fast'] if fast else ['--bytes']

        if not batch:
            json_objects = self._call_annex_records(
                ['info'] + options, files=files, merge_annex_branches=False,
                exception_on_error=False,
            )
        else:
            # according to passing of the test_AnnexRepo_is_under_annex
            # test with batch=True, there is no need for explicit
            # exception_on_error=False, batched process does not raise
            # CommandError.
            json_objects = self._batched.get(
                'info',
                annex_options=options, json=True, path=self.path,
                git_options=['-c', 'annex.merge-annex-branches=false']
            )(files)

        # Some aggressive checks. ATM info can be requested only per file
        # json_objects is a generator, let's keep it that way
        # assert(len(json_objects) == len(files))
        # and that they all have 'file' equal to the passed one
        out = {}
        for j, f in zip(json_objects, files):
            # Starting with version of annex 8.20200330-100-g957a87b43
            # annex started to normalize relative paths.
            # ref: https://github.com/datalad/datalad/issues/4431
            # Use normpath around each side to ensure it is the same file
            assert normpath(j.pop('file')) == normpath(f)
            if not j['success']:
                j = None
            else:
                assert(j.pop('success') is True)
                # convert size to int
                j['size'] = int(j['size']) if 'unknown' not in j['size'] else None
                # and pop the "command" field
                j.pop("command")
            out[f] = j
        return out

    def repo_info(self, fast=False, merge_annex_branches=True):
        """Provide annex info for the entire repository.

        Parameters
        ----------
        fast : bool, optional
          Pass `--fast` to `git annex info`.
        merge_annex_branches : bool, optional
          Whether to allow git-annex if needed to merge annex branches, e.g. to
          make sure up to date descriptions for git annex remotes

        Returns
        -------
        dict
          Info for the repository, with keys matching the ones returned by annex
        """

        options = ['--bytes', '--fast'] if fast else ['--bytes']

        json_records = list(self._call_annex_records(
            ['info'] + options, merge_annex_branches=merge_annex_branches)
        )
        assert(len(json_records) == 1)

        # TODO: we need to abstract/centralize conversion from annex fields
        # For now just tune up few for immediate usability
        info = json_records[0]
        for k in info:
            if k.endswith(' size') or k.endswith(' disk space') or k.startswith('size of '):
                size = info[k].split()[0]
                if size.isdigit():
                    info[k] = int(size)
                else:
                    lgr.debug("Size %r reported to be %s, setting to None", k, size)
                    info[k] = None
        assert(info.pop('success'))
        assert(info.pop('command') == 'info')
        return info  # just as is for now

    def get_annexed_files(self, with_content_only=False, patterns=None):
        """Get a list of files in annex

        Parameters
        ----------
        with_content_only : bool, optional
            Only list files whose content is present.
        patterns : list, optional
            Globs to pass to annex's `--include=`. Files that match any of
            these will be returned (i.e., they'll be separated by `--or`).

        Returns
        -------
        A list of POSIX file names
        """
        if not patterns:
            args = [] if with_content_only else ['--include', "*"]
        else:
            if len(patterns) == 1:
                args = ['--include', patterns[0]]
            else:
                args = ['-(']
                for pat in patterns[:-1]:
                    args.extend(['--include', pat, "--or"])
                args.extend(['--include', patterns[-1]])
                args.append('-)')

            if with_content_only:
                args.extend(['--in', '.'])
        # TODO: JSON
        return list(
            self.call_annex_items_(
                ['find', '-c', 'annex.merge-annex-branches=false'] + args))

    def get_preferred_content(self, property, remote=None):
        """Get preferred content configuration of a repository or remote

        Parameters
        ----------
        property : {'wanted', 'required', 'group'}
          Type of property to query
        remote : str, optional
          If not specified (None), returns the property for the local
          repository.

        Returns
        -------
        str
          Whether the setting is returned, or `None` if there is none.

        Raises
        ------
        ValueError
          If an unknown property label is given.

        CommandError
          If the annex call errors.
        """
        if property not in ('wanted', 'required', 'group'):
            raise ValueError(
                'unknown preferred content property: {}'.format(property))
        return self.call_annex_oneline([property, remote or '.']) or None

    def set_preferred_content(self, property, expr, remote=None):
        """Set preferred content configuration of a repository or remote

        Parameters
        ----------
        property : {'wanted', 'required', 'group'}
          Type of property to query
        expr : str
          Any expression or label supported by git-annex for the
          given property.
        remote : str, optional
          If not specified (None), sets the property for the local
          repository.

        Returns
        -------
        str
          Raw git-annex output in response to the set command.

        Raises
        ------
        ValueError
          If an unknown property label is given.

        CommandError
          If the annex call errors.
        """
        if property not in ('wanted', 'required', 'group'):
            raise ValueError(
                'unknown preferred content property: {}'.format(property))
        return self.call_annex_oneline([property, remote or '.', expr])

    def get_groupwanted(self, name):
        """Get `groupwanted` expression for a group `name`

        Parameters
        ----------
        name : str
           Name of the groupwanted group
        """
        return self.call_annex_oneline(['groupwanted', name])

    def set_groupwanted(self, name, expr):
        """Set `expr` for the `name` groupwanted"""
        return self.call_annex_oneline(['groupwanted', name, expr])

    def precommit(self):
        """Perform pre-commit maintenance tasks, such as closing all batched annexes
        since they might still need to flush their changes into index
        """
        if self._batched is not None:
            self._batched.close()
        super(AnnexRepo, self).precommit()

    def get_contentlocation(self, key, batch=False):
        """Get location of the key content

        Normally under .git/annex objects in indirect mode and within file
        tree in direct mode.

        Unfortunately there is no (easy) way to discriminate situations
        when given key is simply incorrect (not known to annex) or its content
        not currently present -- in both cases annex just silently exits with -1


        Parameters
        ----------
        key: str
            key
        batch: bool, optional
            initiate or continue with a batched run of annex contentlocation

        Returns
        -------
        str
            path relative to the top directory of the repository. If no content
            is present, empty string is returned
        """

        if not batch:
            try:
                return next(self.call_annex_items_(['contentlocation', key]))
            except CommandError:
                return ''
        else:
            return self._batched.get('contentlocation', path=self.path)(key)

    @normalize_paths(serialize=True)
    def is_available(self, file_, remote=None, key=False, batch=False):
        """Check if file or key is available (from a remote)

        In case if key or remote is misspecified, it wouldn't fail but just keep
        returning False, although possibly also complaining out loud ;)

        Parameters
        ----------
        file_: str
            Filename or a key
        remote: str, optional
            Remote which to check.  If None, possibly multiple remotes are checked
            before positive result is reported
        key: bool, optional
            Whether provided files are actually annex keys
        batch: bool, optional
            Initiate or continue with a batched run of annex checkpresentkey

        Returns
        -------
        bool
            with True indicating that file/key is available from (the) remote
        """

        if key:
            key_ = file_
        else:
            # TODO with eval_availability=True, the following call
            # would already provide the answer to is_available? for
            # the local annex
            key_ = self.get_file_annexinfo(file_)['key']  # ?, batch=batch

        annex_input = [key_,] if not remote else [key_, remote]

        if not batch:
            return self.call_annex_success(['checkpresentkey'] + annex_input)
        else:
            annex_cmd = ["checkpresentkey"] + ([remote] if remote else [])
            try:
                out = self._batched.get(
                    ':'.join(annex_cmd), annex_cmd,
                    path=self.path)(key_)
            except CommandError:
                # git-annex runs in batch mode, but will still signal some
                # errors, e.g. an unknown remote, by exiting with a non-zero
                # return code.
                return False
            try:
                return {
                    # happens on travis in direct/heavy-debug mode, that process
                    # exits and closes stdout (upon unknown key) before we could
                    # read it, so we get None as the stdout.
                    # see https://github.com/datalad/datalad/issues/2330
                    # but it is associated with an unknown key, and for consistency
                    # we report False there too, as to ''
                    None: False,
                    '': False,  # when remote is misspecified ... stderr carries the msg
                    '0': False,
                    '1': True,
                }[out]
            except KeyError:
                raise ValueError(
                    "Received output %r from annex, whenever expect 0 or 1" % out
                )

    @normalize_paths
    def migrate_backend(self, files, backend=None):
        """Changes the backend used for `file`.

        The backend used for the key-value of `files`. Only files currently
        present are migrated.
        Note: There will be no notification if migrating fails due to the
        absence of a file's content!

        Parameters
        ----------
        files: list
            files to migrate.
        backend: str
            specify the backend to migrate to. If none is given, the
            default backend of this instance will be used.
        """

        if self.is_direct_mode():
            raise CommandNotAvailableError(
                'git-annex migrate',
                "Command 'migrate' is not available in direct mode.")
        self._call_annex(
            ['migrate'] + (['--backend', backend] if backend else []),
            files=files,
        )

    @classmethod
    def get_key_backend(cls, key):
        """Get the backend from a given key"""
        return key.split('-', 1)[0]

    @normalize_paths
    def get_file_backend(self, files):
        """Get the backend currently used for file(s).

        Parameters
        ----------
        files: list of str

        Returns
        -------
        list of str
            For each file in input list indicates the used backend by a str
            like "SHA256E" or "MD5".
        """

        return [
            p.get('backend', '')
            for p in self.get_content_annexinfo(files, init=None).values()
        ]

    @property
    def default_backends(self):
        self.config.reload()
        # TODO: Deprecate and remove this property? It's used in the tests and
        # datalad-crawler.
        #
        # git-annex used to try the list of backends in annex.backends in
        # order. Now it takes annex.backend if set, falling back to the first
        # value of annex.backends. See 4c1e3210f (annex.backend is the new name
        # for what was annex.backends, 2017-05-09).
        backend = self.get_gitattributes('.')['.'].get(
            'annex.backend',
            self.config.get("annex.backend", default=None))
        if backend:
            return [backend]

        backends = self.config.get("annex.backends", default=None)
        if backends:
            return backends.split()
        else:
            return None

    # comment out presently unnecessary functionality, bring back once needed
    #def fsck(self, paths=None, remote=None, fast=False, incremental=False,
    #         limit=None, annex_options=None, git_options=None):
    def fsck(self, paths=None, remote=None, fast=False,
             annex_options=None, git_options=None):
        """Front-end for git-annex fsck

        Parameters
        ----------
        paths : list
          Limit operation to specific paths.
        remote : str
          If given, the identified remote will be fsck'ed instead of the
          local repository.
        fast : bool
          If True, typically means that no actual content is being verified,
          but tests are limited to the presence of files.
        """
        #incremental : bool or {'continue'} or SCHEDULE
        #  If given, `fsck` is called with `--incremental`. If 'continue',
        #  `fsck` is additionally called with `--more`, and any other argument
        #  is given to `--incremental-schedule`.
        #limit : str or all
        #  If the function `all` is given, `fsck` is called with `--all`. Any
        #  other value is passed on to `--branch`.
        args = [] if annex_options is None else list(annex_options)
        if fast:
            args.append('--fast')
        if remote:
            args.append('--from={}'.format(remote))
        #if limit:
        #    # looks funky, but really is a test if the `all` function was passed
        #    # alternatives would have been 1) a dedicated argument (would need
        #    # a check for mutual exclusivity with --branch), or 2) a str-type
        #    # special values that has no meaning in Git and is less confusing
        #    if limit is all:
        #        args.append('--all')
        #    else:
        #        args.append('--branch={}'.format(limit))
        #if incremental == 'continue':
        #    args.append('--more')
        #elif incremental:
        #    args.append('--incremental')
        #    if not (incremental is True):
        #        args.append('--incremental-schedule={}'.format(incremental))
        try:
            return self._call_annex_records(
                ['fsck'] + args,
                files=paths,
                git_options=git_options,
            )
        except CommandError as e:
            # fsck may exit non-zero when there are too few known copies
            # callers of whereis are interested in exactly that information,
            # which we deliver via result, not via exception
            return e.kwargs.get('stdout_json', [])

    # We need --auto and --fast having exposed  TODO
    @normalize_paths(match_return_type=False)  # get a list even in case of a single item
    def copy_to(self, files, remote, options=None, jobs=None):
        """Copy the actual content of `files` to `remote`

        Parameters
        ----------
        files: str or list of str
            path(s) to copy
        remote: str
            name of remote to copy `files` to

        Returns
        -------
        list of str
           files successfully copied
        """
        warnings.warn(
            "AnnexRepo.copy_to() is deprecated and will be removed in a "
            "future release. Use the Dataset method push() instead.",
            DeprecationWarning)

        # find --in here --not --in remote
        # TODO: full support of annex copy options would lead to `files` being
        # optional. This means to check for whether files or certain options are
        # given and fail or just pass everything as is and try to figure out,
        # what was going on when catching CommandError

        if remote not in self.get_remotes():
            raise ValueError("Unknown remote '{0}'.".format(remote))

        options = options[:] if options else []

        # Note:
        # In case of single path, 'annex copy' will fail, if it cannot copy it.
        # With multiple files, annex will just skip the ones, it cannot deal
        # with. We'll do the same and report back what was successful
        # (see return value).
        # Therefore raise telling exceptions before even calling annex:
        if len(files) == 1:
            # Note, that for isdir we actually need an absolute path (which we don't get via normalize_paths)
            if not isdir(opj(self.path, files[0])):
                # for non-existing paths, get_file_annexinfo() will raise already
                if self.get_file_annexinfo(files[0]).get('key') is None:
                    raise FileInGitError(f'No known annex key for a file {files[0]}. Cannot copy')

        # TODO: RF -- logic is duplicated with get() -- the only difference
        # is the verb (copy, copy) or (get, put) and remote ('here', remote)?
        if '--key' not in options:
            expected_copys, copy_files = self._get_expected_files(
                files, ['--in', '.', '--not', '--in', remote])
        else:
            copy_files = files
            assert(len(files) == 1)
            expected_copys = {files[0]: AnnexRepo.get_size_from_key(files[0])}

        if not copy_files:
            lgr.debug("No files found needing copying.")
            return []

        if len(copy_files) != len(files):
            lgr.debug("Actually copying %d files", len(copy_files))

        self._maybe_open_ssh_connection(remote)
        annex_options = ['--to=%s' % remote]
        if options:
            annex_options.extend(split_cmdline(options))

        # filter out keys with missing size info
        total_nbytes = sum(i for i in expected_copys.values() if i) or None

        # TODO: provide more meaningful message (possibly aggregating 'note'
        #  from annex failed ones
        results = self._call_annex_records(
            ['copy'] + annex_options,
            files=files,  # copy_files,
            jobs=jobs,
            progress=True,
            total_nbytes=total_nbytes,
        )
        results_list = list(results)
        # XXX this is the only logic different ATM from get
        # check if any transfer failed since then we should just raise an Exception
        # for now to guarantee consistent behavior with non--json output
        # see https://github.com/datalad/datalad/pull/1349#discussion_r103639456
        from operator import itemgetter
        failed_copies = [e['file'] for e in results_list if not e['success']]
        good_copies = [
            e['file'] for e in results_list
            if e['success'] and
               e.get('note', '').startswith('to ')  # transfer did happen
        ]
        if failed_copies:
            # TODO: RF for new fancy scheme of outputs reporting
            raise IncompleteResultsError(
                results=good_copies, failed=failed_copies,
                msg="Failed to copy %d file(s)" % len(failed_copies))
        return good_copies

    @property
    def uuid(self):
        """Annex UUID

        Returns
        -------
        str
          Returns a the annex UUID, if there is any, or `None` otherwise.
        """
        if not self._uuid:
            self._uuid = self.config.get('annex.uuid', default=None)
        return self._uuid

    def get_description(self, uuid=None):
        """Get annex repository description

        Parameters
        ----------
        uuid : str, optional
          For which remote (based on uuid) to report description for

        Returns
        -------
        str or None
          None returned if not found
        """
        info = self.repo_info(fast=True)
        match = \
            (lambda x: x['here']) \
            if uuid is None \
            else (lambda x: x['uuid'] == uuid)

        matches = list(set(chain.from_iterable(
            [
                [r['description'] for r in remotes if match(r)]
                for k, remotes in info.items()
                if k.endswith(' repositories')
            ]
        )))

        if len(matches) == 1:
            # single hit as it should
            return matches[0]
        elif len(matches) == 2:
            lgr.warning(
                "Found multiple hits while searching. Returning first among: %s",
                str(matches)
            )
            return matches[0]
        else:
            return None

    def get_metadata(self, files, timestamps=False, batch=False):
        """Query git-annex file metadata

        Parameters
        ----------
        files : str or iterable(str)
          One or more paths for which metadata is to be queried. If one
          or more paths could be directories, `batch=False` must be given
          to prevent git-annex given an error. Due to technical limitations,
          such error will lead to a hanging process.
        timestamps: bool, optional
          If True, the output contains a '<metadatakey>-lastchanged'
          key for every metadata item, reflecting the modification
          time, as well as a 'lastchanged' key with the most recent
          modification time of any metadata item.
        batch: bool, optional
          If True, a `metadata --batch` process will be used, and only
          confirmed annex'ed files can be queried (else query will hang
          indefinitely). If False, invokes without --batch, and gives all files
          as arguments (this can be problematic with a large number of files).

        Returns
        -------
        generator
          One tuple per file (could be more items than input arguments
          when directories are given). First tuple item is the filename,
          second item is a dictionary with metadata key/value pairs. Note that annex
          metadata tags are stored under the key 'tag', which is a
          regular metadata item that can be manipulated like any other.
        """
        def _format_response(res):
            return (
                str(Path(PurePosixPath(res['file']))),
                res['fields'] if timestamps else \
                {k: v for k, v in res['fields'].items()
                 if not k.endswith('lastchanged')}
            )

        if not files:
            return
        if batch is False:
            # we can be lazy
            files = ensure_list(files)
        else:
            if isinstance(files, str):
                files = [files]
            # anything else is assumed to be an iterable (e.g. a generator)
        if batch is False:
            for res in self.call_annex_records(['metadata'], files=files):
                yield _format_response(res)
        else:
            # batch mode is different: we need to compose a JSON request object
            batched = self._batched.get('metadata', json=True, path=self.path)
            for f in files:
                res = batched.proc1(json.dumps({'file': f}))
                yield _format_response(res)

    def set_metadata(
            self, files, reset=None, add=None, init=None,
            remove=None, purge=None, recursive=False):
        """Manipulate git-annex file-metadata

        Parameters
        ----------
        files : str or list(str)
          One or more paths for which metadata is to be manipulated.
          The changes applied to each file item are uniform. However,
          the result may not be uniform across files, depending on the
          actual operation.
        reset : dict, optional
          Metadata items matching keys in the given dict are (re)set
          to the respective values.
        add : dict, optional
          The values of matching keys in the given dict appended to
          any possibly existing values. The metadata keys need not
          necessarily exist before.
        init : dict, optional
          Metadata items for the keys in the given dict are set
          to the respective values, if the key is not yet present
          in a file's metadata.
        remove : dict, optional
          Values in the given dict are removed from the metadata items
          matching the respective key, if they exist in a file's metadata.
          Non-existing values, or keys do not lead to failure.
        purge : list, optional
          Any metadata item with a key matching an entry in the given
          list is removed from the metadata.
        recursive : bool, optional
          If False, fail (with CommandError) when directory paths
          are given as `files`.

        Returns
        -------
        list
          JSON obj per modified file
        """
        return list(self.set_metadata_(
            files, reset=reset, add=add, init=init,
            remove=remove, purge=purge, recursive=recursive))

    def set_metadata_(
            self, files, reset=None, add=None, init=None,
            remove=None, purge=None, recursive=False):
        """Like set_metadata() but returns a generator"""

        def _genspec(expr, d):
            return [expr.format(k, v) for k, vs in d.items() for v in ensure_list(vs)]

        args = []
        spec = []
        for expr, d in (('{}={}', reset),
                        ('{}+={}', add),
                        ('{}?={}', init),
                        ('{}-={}', remove)):
            if d:
                spec.extend(_genspec(expr, d))
        # prefix all with '-s' and extend arg list
        args.extend(j for i in zip(['-s'] * len(spec), spec) for j in i)
        if purge:
            # and all '-r' args
            args.extend(j for i in zip(['-r'] * len(purge), purge)
                        for j in i)
        if not args:
            return

        if recursive:
            args.append('--force')

        # Make sure that batch add/addurl operations are closed so that we can
        # operate on files that were just added.
        self.precommit()

        for jsn in self.call_annex_records(
                ['metadata'] + args,
                files=files):
            yield jsn

    # TODO: RM DIRECT?  might remain useful to detect submods left in direct mode
    @staticmethod
    def _is_annex_work_tree_message(out):
        return re.match(
            r'.*This operation must be run in a work tree.*'
            r'git status.*failed in submodule',
            out,
            re.MULTILINE | re.DOTALL | re.IGNORECASE)


    def _mark_content_availability(self, info):
        objectstore = self.pathobj.joinpath(
            self.path, GitRepo.get_git_dir(self), 'annex', 'objects')
        for f, r in info.items():
            if 'key' not in r or 'has_content' in r:
                # not annexed or already processed
                continue
            # test hashdirmixed first, as it is used in non-bare repos
            # which be a more frequent target
            # TODO optimize order based on some check that reveals
            # what scheme is used in a given annex
            r['has_content'] = False
            # some keys like URL-s700145--https://arxiv.org/pdf/0904.3664v1.pdf
            # require sanitization to be able to mark content availability
            # correctly. Can't limit to URL backend only; custom key backends
            # may need it, too
            key = _sanitize_key(r['key'])
            for testpath in (
                    # ATM git-annex reports hashdir in native path
                    # conventions and the actual file path `f` in
                    # POSIX, weird...
                    # we need to test for the actual key file, not
                    # just the containing dir, as on windows the latter
                    # may not always get cleaned up on `drop`
                    objectstore.joinpath(
                        ut.Path(r['hashdirmixed']), key, key),
                    objectstore.joinpath(
                        ut.Path(r['hashdirlower']), key, key)):
                if testpath.exists():
                    r.pop('hashdirlower', None)
                    r.pop('hashdirmixed', None)
                    r['objloc'] = str(testpath)
                    r['has_content'] = True
                    break

    def get_file_annexinfo(self, path, ref=None, eval_availability=False,
                           key_prefix=''):
        """Query annex properties for a single file

        This is the companion to get_content_annexinfo() and offers
        simplified usage for single-file queries (the result lookup
        based on a path is not necessary.

        All keyword arguments have identical names and semantics as
        their get_content_annexinfo() counterparts. See their
        documentation for more information.

        Parameters
        ----------
        path : Path or str
          A single path to a file in the repository.

        Returns
        -------
        dict
          Keys and values match the values returned by get_content_annexinfo().
          If a file has no annex properties (i.e., a file that is directly
          checked into Git and is not annexed), the returned dictionary is
          empty.

        Raises
        ------
        ValueError
          When a given path is not matching a single file, but resolves to
          multiple files (e.g. a directory path)
        NoSuchPathError
          When the given path does not match any file in a repository
        """
        info = {k: v
                for k, v in self.get_content_annexinfo(
                    [path],
                    init=None,
                    ref=ref,
                    eval_availability=eval_availability).items()}
        if len(info) > 1:
            raise ValueError(
                "AnnexRepo.get_file_annexinfo() can handle handle a single "
                f"file path, but {path} resolved to {len(info)} paths")
        elif not info:
            # no error, there is a file, but we know nothing about it
            return {}
        path, props = info.popitem()
        # turn a file not found situation into an exception
        if props.get('success') is False and props.get('note') == 'not found':
            raise NoSuchPathError(path)
        # fold path into the report to give easy access to a normalized,
        # resolved Path instance
        props['path'] = path
        return props

    def get_content_annexinfo(
            self, paths=None, init='git', ref=None, eval_availability=False,
            key_prefix='', **kwargs):
        """
        Parameters
        ----------
        paths : list or None
          Specific paths to query info for. In `None`, info is reported for all
          content.
        init : 'git' or dict-like or None
          If set to 'git' annex content info will amend the output of
          GitRepo.get_content_info(), otherwise the dict-like object
          supplied will receive this information and the present keys will
          limit the report of annex properties. Alternatively, if `None`
          is given, no initialization is done, and no limit is in effect.
        ref : gitref or None
          If not None, annex content info for this Git reference will be
          produced, otherwise for the content of the present worktree.
        eval_availability : bool
          If this flag is given, evaluate whether the content of any annex'ed
          file is present in the local annex.
        **kwargs :
          Additional arguments for GitRepo.get_content_info(), if `init` is
          set to 'git'.

        Returns
        -------
        dict
          The keys/values match those reported by GitRepo.get_content_info().
          In addition, the following properties are added to each value
          dictionary:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory', where 'file'
            is also used for annex'ed files (corrects a 'symlink' report
            made by `get_content_info()`.
          `key`
            Annex key of a file (if an annex'ed file)
          `bytesize`
            Size of an annexed file in bytes.
          `has_content`
            Bool whether a content object for this key exists in the local
            annex (with `eval_availability`)
          `objloc`
            pathlib.Path of the content object in the local annex, if one
            is available (with `eval_availability`)
        """
        if init is None:
            info = dict()
        elif init == 'git':
            info = super(AnnexRepo, self).get_content_info(
                paths=paths, ref=ref, **kwargs)
        else:
            info = init

        if not paths and paths is not None:
            return info

        # use this funny-looking option with both find and findref
        # it takes care of git-annex reporting on any known key, regardless
        # of whether or not it actually (did) exist in the local annex.
        if self._check_version_kludges("find-supports-anything"):
            cmd = ['--anything']
        else:
            # --include=* was recommended by Joey in
            # https://git-annex.branchable.com/todo/add_--all___40__or_alike__41___to_find_and_findref/
            cmd = ['--include=*']
        files = None
        if ref:
            cmd = ['findref'] + cmd
            cmd.append(ref)
        else:
            cmd = ['find'] + cmd
            # stringify any pathobjs
            if paths:  # we have early exit above in case of [] and not None
                files = [str(p) for p in paths]
            else:
                cmd += ['--include', '*']

        for j in self.call_annex_records(cmd, files=files):
            path = self.pathobj.joinpath(ut.PurePosixPath(j['file']))
            rec = info.get(path, None)
            if rec is None:
                # git didn't report on this path
                if j.get('success', None) is False:
                    # Annex reports error on that file. Create an error entry,
                    # as we can't currently yield a prepared error result from
                    # within here.
                    rec = {'status': 'error', 'state': 'unknown'}
                elif init is not None:
                    # init constraint knows nothing about this path -> skip
                    continue
                else:
                    rec = {}
            rec.update({'{}{}'.format(key_prefix, k): j[k]
                       for k in j if k != 'file' and k != 'error-messages'})
            # change annex' `error-messages` into singular to match result
            # records:
            if j.get('error-messages', None):
                rec['error_message'] = '\n'.join(m.strip() for m in j['error-messages'])
            if 'bytesize' in rec:
                # it makes sense to make this an int that one can calculate with
                # with
                try:
                    rec['bytesize'] = int(rec['bytesize'])
                except ValueError:
                    # this would only ever happen, if the recorded key itself
                    # has no size info. Even for a URL key, this would mean
                    # that the server would have to not report size info at all
                    # but it does actually happen, e.g.
                    # URL--http&c%%ciml.info%dl%v0_9%ciml-v0_9-all.pdf
                    # from github.com/datalad-datasets/machinelearning-books
                    lgr.debug('Failed to convert "%s" to integer bytesize',
                              rec['bytesize'])
                    # remove the field completely to avoid ambiguous semantics
                    # of None/NaN etc.
                    del rec['bytesize']
            if rec.get('type') == 'symlink' and rec.get('key') is not None:
                # we have a tracked symlink with an associated annex key
                # this is only a symlink for technical reasons, but actually
                # a file from the user perspective.
                # homogenization of this kind makes the report more robust
                # across different representations of a repo
                # (think adjusted branches ...)
                rec['type'] = 'file'
            info[path] = rec
        # TODO make annex availability checks optional and move in here
        if eval_availability:
            self._mark_content_availability(info)
        return info

    def annexstatus(self, paths=None, untracked='all'):
        """
        .. deprecated:: 0.16
            Use get_content_annexinfo() or the test helper
            :py:func:`datalad.tests.utils_pytest.get_annexstatus` instead.
        """
        info = self.get_content_annexinfo(
            paths=paths,
            eval_availability=False,
            init=self.get_content_annexinfo(
                paths=paths,
                ref='HEAD',
                eval_availability=False,
                init=self.status(
                    paths=paths,
                    eval_submodule_state='full')
            )
        )
        self._mark_content_availability(info)
        return info

    def _save_add(self, files, git=None, git_opts=None):
        """Simple helper to add files in save()"""
        from datalad.interface.results import get_status_dict

        # alter default behavior of git-annex by considering dotfiles
        # too
        # however, this helper is controlled by save() which itself
        # operates on status() which itself honors .gitignore, so
        # there is a standard mechanism that is uniform between Git
        # Annex repos to decide on the behavior on a case-by-case
        # basis
        options = []
        # if None -- leave it to annex to decide
        if git is False:
            options.append("--force-large")
        if on_windows:
            # git-annex ignores symlinks on windows
            # https://github.com/datalad/datalad/issues/2955
            # check if there are any and pass them to git-add
            symlinks_toadd = {
                p: props for p, props in files.items()
                if props.get('type', None) == 'symlink'}
            if symlinks_toadd:
                for r in GitRepo._save_add(
                        self,
                        symlinks_toadd,
                        git_opts=git_opts):
                    yield r
            # trim `files` of symlinks
            files = {
                p: props for p, props in files.items()
                if props.get('type', None) != 'symlink'}

        expected_additions = None
        if ui.is_interactive:
            # without an interactive UI there is little benefit from
            # progressbar info, hence save the stat calls
            expected_additions = {p: self.get_file_size(p) for p in files}

        if git is True:
            yield from GitRepo._save_add(self, files, git_opts=git_opts)
        else:
            for r in self._call_annex_records(
                    ['add'] + options,
                    files=list(files.keys()),
                    # TODO
                    jobs=None,
                    total_nbytes=sum(expected_additions.values())
                    if expected_additions else None):
                yield get_status_dict(
                    action=r.get('command', 'add'),
                    refds=self.pathobj,
                    type='file',
                    path=(self.pathobj / ut.PurePosixPath(r['file']))
                    if 'file' in r else None,
                    status='ok' if r.get('success', None) else 'error',
                    key=r.get('key', None),
                    message='\n'.join(r['error-messages'])
                    if 'error-messages' in r else None,
                    logger=lgr)

    def _save_post(self, message, files, partial_commit,
                   amend=False, allow_empty=False):

        if amend and self.is_managed_branch() and \
                self.format_commit("%B").strip() == "git-annex adjusted branch":
            # We must not directly amend on an adjusted branch, but fix it
            # up after the fact. That is if HEAD is a git-annex commit.
            # Otherwise we still can amend-commit normally.
            # Note, that this may involve creating an empty commit first.
            amend = False
            adjust_amend = True
        else:
            adjust_amend = False

        # first do standard GitRepo business
        super(AnnexRepo, self)._save_post(
            message, files, partial_commit, amend,
            allow_empty=allow_empty or adjust_amend)
        # then sync potential managed branches
        self.localsync(managed_only=True)
        if adjust_amend:
            # We committed in an adjusted branch, but the goal is to amend in
            # corresponding branch.

            adjusted_branch = self.get_active_branch()
            corresponding_branch = self.get_corresponding_branch()
            old_sha = self.get_hexsha(corresponding_branch)

            org_commit_pointer = corresponding_branch + "~1"
            author_name, author_email, author_date, \
            old_parent, old_message = self.format_commit(
                "%an%x00%ae%x00%ad%x00%P%x00%B", org_commit_pointer).split('\0')
            new_env = (self._git_runner.env
                       if self._git_runner.env else os.environ).copy()
            # `message` might be empty - we need to take it from the to be
            # amended commit in that case:
            msg = message or old_message
            new_env.update({
                'GIT_AUTHOR_NAME': author_name,
                'GIT_AUTHOR_EMAIL': author_email,
                'GIT_AUTHOR_DATE': author_date
            })
            commit_cmd = ["commit-tree",
                          corresponding_branch + "^{tree}",
                          "-m", msg]
            if old_parent:
                commit_cmd.extend(["-p", old_parent])
            out, _ = self._call_git(commit_cmd, env=new_env, read_only=False)
            new_sha = out.strip()

            self.update_ref("refs/heads/" + corresponding_branch,
                            new_sha, old_sha)
            self.update_ref("refs/basis/" + adjusted_branch,
                            new_sha, old_sha)
            self.localsync(managed_only=True)

    def localsync(self, remote=None, managed_only=False):
        """Consolidate the local git-annex branch and/or managed branches.

        This method calls `git annex sync` to perform purely local operations
        that:

        1. Update the corresponding branch of any managed branch.

        2. Synchronize the local 'git-annex' branch with respect to particular
           or all remotes (as currently reflected in the local state of their
           remote 'git-annex' branches).

        If a repository has git-annex's 'synced/...' branches these will be
        updated.  Otherwise, such branches that are created by `git annex sync`
        are removed again after the sync is complete.

        Parameters
        ----------
        remote : str or list, optional
          If given, specifies the name of one or more remotes to sync against.
          If not given, all remotes are considered.
        managed_only : bool, optional
          Only perform a sync if a managed branch with a corresponding branch
          is detected. By default, a sync is always performed.
        """
        branch = self.get_active_branch()
        corresponding_branch = self.get_corresponding_branch(branch)
        branch = corresponding_branch or branch

        if managed_only and not corresponding_branch:
            lgr.debug('No sync necessary, no corresponding branch detected')
            return

        lgr.debug(
            "Sync local 'git-annex' branch%s.",
            ", and corresponding '{}' branch".format(corresponding_branch)
            if corresponding_branch else '')

        synced_branch = 'synced/{}'.format(branch)
        had_synced_branch = synced_branch in self.get_branches()
        cmd = ['sync']
        if remote:
            cmd.extend(ensure_list(remote))
        cmd.extend([
            # disable any external interaction and other magic
            '--no-push', '--no-pull', '--no-commit', '--no-resolvemerge',
            '--no-content'])
        self.call_annex(cmd)
        # a sync can establish new config (e.g. annex-uuid for a remote)
        self.config.reload()
        # cleanup sync'ed branch if we caused it
        if not had_synced_branch and synced_branch in self.get_branches():
            lgr.debug('Remove previously non-existent %s branch after sync',
                      synced_branch)
            self.call_git(
                ['branch', '-d', synced_branch],
            )


class AnnexJsonProtocol(WitlessProtocol):
    """Subprocess communication protocol for `annex ... --json` commands

    Importantly, parsed JSON content is returned as a result, not string output.

    This protocol also handles git-annex's JSON-style progress reporting.
    """
    # capture both streams and handle messaging completely
    proc_out = True
    proc_err = True

    def __init__(self, done_future=None, total_nbytes=None):
        if done_future is not None:
            warnings.warn("`done_future` argument is ignored "
                          "and will be removed in a future release",
                          DeprecationWarning)
        super().__init__()
        # to collect parsed JSON command output
        self.json_out = []
        self._global_pbar_id = 'annexprogress-{}'.format(id(self))
        self.total_nbytes = total_nbytes
        self._unprocessed = None

    def add_to_output(self, json_object):
        self.json_out.append(json_object)

    def connection_made(self, transport):
        super().connection_made(transport)
        self._pbars = set()
        # overall counter of processed bytes (computed from key reports)
        self._byte_count = 0
        if self.total_nbytes:
            # init global pbar, do here to be on top of first file
            log_progress(
                lgr.info,
                self._global_pbar_id,
                'Start annex operation',
                # do not crash if no command is reported
                unit=' Bytes',
                label='Total',
                total=self.total_nbytes,
                noninteractive_level=5,
            )
            self._pbars.add(self._global_pbar_id)

    def pipe_data_received(self, fd, data):
        if fd != 1:
            # let the base class decide what to do with it
            super().pipe_data_received(fd, data)
            return
        if self._unprocessed:
            data = self._unprocessed + data
            self._unprocessed = None
        # this is where the JSON records come in
        lines = data.splitlines()
        data_ends_with_eol = data.endswith(os.linesep.encode())
        del data
        for iline, line in enumerate(lines):
            try:
                j = json.loads(line)
            except Exception as exc:
                if line.strip():
                    # do not complain on empty lines
                    if iline == len(lines) - 1 and not data_ends_with_eol:
                        lgr.debug("Caught %s while trying to parse JSON line %s which might "
                                  "be not yet a full line", exc, line)
                        # it is the last line and fails to parse -- it can/likely
                        # to happen that it was not a complete line and that buffer
                        # got filled up/provided before the end of line.
                        # Store it so that it can be prepended to data in the next call.
                        self._unprocessed = line
                        break
                    # TODO turn this into an error result, or put the exception
                    # onto the result future -- needs more thought
                    lgr.error('Received undecodable JSON output: %s', line)
                continue
            self._proc_json_record(j)

    def _get_pbar_id(self, record):
        # NOTE: Look at the "action" field for byte-progress records and the
        # top-level `record` for the final record. The action record as a whole
        # should be stable link across byte-progress records, but a subset of
        # the keys is hard coded below so that the action record can be linked
        # to the final one.
        info = record.get("action") or record
        return 'annexprogress-{}-{}'.format(
            id(self),
            hash(frozenset((k, info.get(k))
                           for k in ["command", "key", "file"])))

    def _get_pbar_label(self, action):
        # do not crash if no command is reported
        label = action.get('command', '').capitalize()
        target = action.get('file') or action.get('key')
        if target:
            label += " " + target

        if label:
            from datalad.ui import utils as ui_utils

            # Reserving 55 characters for the progress bar is based
            # approximately off what used to be done in the now-removed
            # (948ccf3e18) ProcessAnnexProgressIndicators.
            max_label_width = ui_utils.get_console_width() - 55
            if max_label_width < 0:
                # We're squeezed. Just show bar.
                label = ""
            elif len(label) > max_label_width:
                mid = max_label_width // 2
                label = label[:mid] + " .. " + label[-mid:]
        return label

    def _proc_json_record(self, j):
        # check for progress reports and act on them immediately
        # but only if there is something to build a progress report from
        pbar_id = self._get_pbar_id(j)
        known_pbar = pbar_id in self._pbars
        action = j.get('action')

        is_progress = action and 'byte-progress' in j
        # ignore errors repeatedly reported in progress messages. Final message
        # will contain them
        if action and not is_progress:
            for err_msg in action.pop('error-messages', []):
                lgr.error(err_msg)

        if known_pbar and (not is_progress or
                           j.get('byte-progress') == j.get('total-size')):
            # take a known pbar down, completion or broken report
            log_progress(
                lgr.info,
                pbar_id,
                'Finished annex action: {}'.format(action),
                noninteractive_level=5,
            )
            self._pbars.discard(pbar_id)
            if is_progress:
                # The final record is yet to come.
                return

        if is_progress:
            if not known_pbar:
                # init the pbar, the is some progress left to be made
                # worth it
                log_progress(
                    lgr.info,
                    pbar_id,
                    'Start annex action: {}'.format(action),
                    label=self._get_pbar_label(action),
                    unit=' Bytes',
                    total=float(j.get('total-size', 0)),
                    noninteractive_level=5,
                )
                self._pbars.add(pbar_id)
            log_progress(
                lgr.info,
                pbar_id,
                j.get('percent-progress', 0),
                update=float(j.get('byte-progress', 0)),
                noninteractive_level=5,
            )
            # do not let progress reports leak into the return value
            return
        # update overall progress, do not crash when there is no key property
        # in the report (although there should be one)
        key_bytes = AnnexRepo.get_size_from_key(j.get('key', None))
        if key_bytes:
            self._byte_count += key_bytes
        # don't do anything to the results for now in terms of normalization
        # TODO the protocol could be made aware of the runner's CWD and
        # also any dataset the annex command is operating on. This would
        # enable 'file' property conversion to absolute paths
        self.add_to_output(j)

        if self.total_nbytes:
            if self.total_nbytes <= self._byte_count:
                # discard global pbar
                log_progress(
                    lgr.info,
                    self._global_pbar_id,
                    'Finished annex {}'.format(j.get('command', '')),
                    noninteractive_level=5,
                )
                self._pbars.discard(self._global_pbar_id)
            else:
                # log actual progress
                log_progress(
                    lgr.info,
                    self._global_pbar_id,
                    j.get('file', ''),
                    update=self._byte_count,
                    noninteractive_level=5,
                )

    def _prepare_result(self):
        # first let the base class do its thing
        results = super()._prepare_result()
        # now amend the results, make clear in the key-name that these records
        # came from stdout -- may not be important here or now, but it is easy
        # to imagine structured output on stderr at some point
        results['stdout_json'] = self.json_out
        return results

    def process_exited(self):
        # take down any progress bars that were not closed orderly
        for pbar_id in self._pbars:
            log_progress(
                lgr.info,
                pbar_id,
                'Finished',
                noninteractive_level=5,
            )
        if self._unprocessed:
            lgr.error(
                "%d bytes of received undecodable JSON output remain: %s",
                len(self._unprocessed), self._unprocessed
            )
        super().process_exited()


class GeneratorAnnexJsonProtocol(GeneratorMixIn, AnnexJsonProtocol):
    def __init__(self,
                 done_future=None,
                 total_nbytes=None):
        GeneratorMixIn.__init__(self)
        AnnexJsonProtocol.__init__(self, done_future, total_nbytes)

    def add_to_output(self, json_object):
        self.send_result(json_object)


class GeneratorAnnexJsonNoStderrProtocol(GeneratorAnnexJsonProtocol):
    def __init__(self,
                 done_future=None,
                 total_nbytes=None):
        GeneratorMixIn.__init__(self)
        AnnexJsonProtocol.__init__(self, done_future, total_nbytes)
        self.stderr_output = bytearray()

    def pipe_data_received(self, fd, data):
        if fd == 2:
            self.stderr_output += data
            # let the base class decide what to do with it
        super().pipe_data_received(fd, data)

    def process_exited(self):
        super().process_exited()
        if self.stderr_output:
            raise CommandError(
                msg="Unexpected stderr output",
                stderr=self.stderr_output.decode())


class AnnexInitOutput(WitlessProtocol, AssemblingDecoderMixIn):
    proc_out = True
    proc_err = True

    def __init__(self, done_future=None, encoding=None):
        WitlessProtocol.__init__(self, done_future, encoding)
        AssemblingDecoderMixIn.__init__(self)

    def pipe_data_received(self, fd, byts):
        line = self.decode(fd, byts, self.encoding)
        if fd == 1:
            res = re.search("(scanning for .* files)", line, flags=re.IGNORECASE)
            if res:
                lgr.info("%s (this may take some time)", res.groups()[0])
        elif fd == 2:
            lgr.info(line.strip())


@auto_repr(short=False)
class BatchedAnnex(BatchedCommand):
    """Container for an annex process which would allow for persistent communication
    """

    def __init__(self, annex_cmd, git_options=None, annex_options=None, path=None,
                 json=False, output_proc=None, batch_opt='--batch'):
        if not isinstance(annex_cmd, list):
            annex_cmd = [annex_cmd]
        cmd = \
            ['git'] + \
            (git_options if git_options else []) + \
            ['annex'] + \
            annex_cmd + \
            (annex_options if annex_options else []) + \
            (['--json', '--json-error-messages'] if json else []) + \
            [batch_opt] + \
            (['--debug'] if lgr.getEffectiveLevel() <= 8 else [])
        output_proc = \
            output_proc if output_proc else readline_json if json else None
        super(BatchedAnnex, self).__init__(
            cmd,
            path=path,
            output_proc=output_proc)


# TODO: Why was this commented out?
# @auto_repr
class BatchedAnnexes(SafeDelCloseMixin, dict):
    """Class to contain the registry of active batch'ed instances of annex for
    a repository
    """
    def __init__(self, batch_size=0, git_options=None):
        self.batch_size = batch_size
        self.git_options = git_options or []
        super(BatchedAnnexes, self).__init__()

    def get(self, codename, annex_cmd=None, **kwargs) -> BatchedAnnex:
        if annex_cmd is None:
            annex_cmd = codename

        git_options = self.git_options + kwargs.pop('git_options', [])
        if self.batch_size:
            git_options += ['-c', 'annex.queuesize=%d' % self.batch_size]

        # START RF/BF: extend codename to respect different options the process
        # is running with
        # TODO: Eventually there should be more RF'ing, since the actually used
        # codenames are partially reflecting this already. Any options used
        # therein should go away, since they are now automatically included.
        options = kwargs.copy()
        options['git_options'] = git_options
        options['annex_cmd'] = annex_cmd
        for key in options:
            codename += ':{0}:{1}'.format(key, options[key])
        # END RF/BF

        if codename not in self:
            # Create a new git-annex process we will keep around
            self[codename] = BatchedAnnex(annex_cmd,
                                          git_options=git_options,
                                          **kwargs)
        return self[codename]

    def clear(self):
        """Override just to make sure we don't rely on __del__ to close all
        the pipes"""
        self.close()
        super(BatchedAnnexes, self).clear()

    def close(self):
        """Close communication to all the batched annexes

        It does not remove them from the dictionary though
        """
        for p in self.values():
            p.close()


def readlines_until_ok_or_failed(stdout, maxlines=100):
    """Read stdout until line ends with ok or failed"""
    out = ''
    i = 0
    lgr.log(3, "Trying to receive from %s", stdout)
    while not stdout.closed:
        i += 1
        if maxlines > 0 and i > maxlines:
            raise IOError("Expected no more than %d lines. So far received: %r" % (maxlines, out))
        lgr.log(2, "Expecting a line")
        line = stdout.readline()
        lgr.log(2, "Received line %r", line)
        out += line
        if re.match(r'^.*\b(failed|ok)$', line.rstrip()):
            break
    return out.rstrip()


def readline_json(stdout):
    toload = stdout.readline().strip()
    try:
        return json.loads(toload) if toload else {}
    except json.JSONDecodeError:
        lgr.error('Received undecodable JSON output: %s', toload)
        return {}
