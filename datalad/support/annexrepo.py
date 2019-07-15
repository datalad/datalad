# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
import math
import os
import re
import shlex
import tempfile
import time

from itertools import chain
from os import linesep
from os.path import curdir
from os.path import join as opj
from os.path import exists
from os.path import islink
from os.path import realpath
from os.path import lexists
from os.path import isdir
from os.path import isabs
from os.path import relpath
from os.path import normpath
from subprocess import Popen, PIPE
from multiprocessing import cpu_count
from weakref import WeakValueDictionary

from six import string_types, PY2
from six import iteritems
from six.moves import filter
from git import InvalidGitRepositoryError

from datalad import ssh_manager
from datalad.dochelpers import exc_str
from datalad.dochelpers import borrowdoc
from datalad.dochelpers import borrowkwargs
from datalad.utils import linux_distribution_name
from datalad.utils import nothing_cm
from datalad.utils import auto_repr
from datalad.utils import on_windows
from datalad.utils import swallow_logs
from datalad.utils import assure_list
from datalad.utils import _path_
from datalad.utils import CMD_MAX_ARG
from datalad.utils import assure_unicode, assure_bytes
from datalad.utils import make_tempfile
from datalad.utils import partition
from datalad.utils import unlink
from datalad.support.json_py import loads as json_loads
from datalad.cmd import GitRunner

# imports from same module:
from .repo import RepoInterface
from .gitrepo import GitRepo
from .gitrepo import NoSuchPathError
from .gitrepo import _normalize_path
from .gitrepo import normalize_path
from .gitrepo import normalize_paths
from .gitrepo import GitCommandError
from .gitrepo import to_options
from . import ansi_colors
from .external_versions import external_versions
from .exceptions import CommandNotAvailableError
from .exceptions import CommandError
from .exceptions import FileNotInAnnexError
from .exceptions import FileInGitError
from .exceptions import FileNotInRepositoryError
from .exceptions import AnnexBatchCommandError
from .exceptions import InsufficientArgumentsError
from .exceptions import OutOfSpaceError
from .exceptions import RemoteNotAvailableError
from .exceptions import BrokenExternalDependency
from .exceptions import OutdatedExternalDependency
from .exceptions import MissingExternalDependency
from .exceptions import IncompleteResultsError
from .exceptions import AccessDeniedError
from .exceptions import AccessFailedError
from .exceptions import InvalidAnnexRepositoryError

lgr = logging.getLogger('datalad.annex')

# Limit to # of CPUs and up to 8, but at least 3 to start with
N_AUTO_JOBS = min(8, max(3, cpu_count()))


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
    # End Flyweight:

    # Web remote has a hard-coded UUID we might (ab)use
    WEB_UUID = "00000000-0000-0000-0000-000000000001"

    # To be assigned and checked to be good enough upon first call to AnnexRepo
    # 6.20160923 -- --json-progress for get
    # 6.20161210 -- annex add  to add also changes (not only new files) to git
    # 6.20170220 -- annex status provides --ignore-submodules
    # 6.20180416 -- annex handles unicode filenames more uniformly
    # 6.20180913 -- annex fixes all known to us issues for v6
    GIT_ANNEX_MIN_VERSION = '6.20180913'
    git_annex_version = None

    # Class wide setting to allow insecure URLs. Used during testing, since
    # git annex 6.20180626 those will by default be not allowed for security
    # reasons
    _ALLOW_LOCAL_URLS = False

    def __init__(self, path, url=None, runner=None,
                 direct=None, backend=None, always_commit=True, create=True,
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
        url: str, optional
          url to the to-be-cloned repository. Requires valid git url
          according to
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .
        runner: Runner, optional
          Provide a Runner in case AnnexRepo shall not create it's own.
          This is especially needed in case of desired dry runs.
        direct: bool, optional
          If True, force git-annex to use direct mode
        backend: str, optional
          Set default backend used by this annex. This does NOT affect files,
          that are already annexed nor will it automatically migrate files,
          hat are 'getted' afterwards.
        create: bool, optional
          Create and initialize an annex repository at path, in case
          there is none. If set to False, and this repository is not an annex
          repository (initialized or not), an exception is raised.
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
        if self.git_annex_version is None:
            self._check_git_annex_version()

        # initialize
        self._uuid = None
        self._annex_common_options = []
        # Workaround for per-call config issue with git 2.11.0
        self.GIT_DIRECT_MODE_WRAPPER_ACTIVE = False
        self.GIT_DIRECT_MODE_PROXY = False

        if annex_opts or annex_init_opts:
            lgr.warning("TODO: options passed to git-annex and/or "
                        "git-annex-init are currently ignored.\n"
                        "options received:\n"
                        "git-annex: %s\ngit-annex-init: %s" %
                        (annex_opts, annex_init_opts))

        fix_it = False
        try:
            super(AnnexRepo, self).__init__(path, url, runner=runner,
                                            create=create, repo=repo,
                                            git_opts=git_opts,
                                            fake_dates=fake_dates)
        except GitCommandError as e:
            if create and "Clone succeeded, but checkout failed." in str(e):
                lgr.warning("Experienced issues while cloning. "
                            "Trying to fix it, using git-annex-fsck.")
                fix_it = True
            else:
                raise e

        # Below while setting for direct mode workaround, we change
        # _GIT_COMMON_OPTIONS.
        # But we should not pass workarounds such as --worktree=.
        # -c core.bare=False to git annex commands, so for their
        # invocation we will keep and use pristine version of the
        # common options
        self._ANNEX_GIT_COMMON_OPTIONS = self._GIT_COMMON_OPTIONS[:]

        # check for possible SSH URLs of the remotes in order to set up
        # shared connections:
        for r in self.get_remotes():
            for url in [self.get_remote_url(r),
                        self.get_remote_url(r, push=True)]:
                if url is not None:
                    self._set_shared_connection(r, url)

        self.always_commit = always_commit

        if version is None:
            version = self.config.get("datalad.repo.version", None)
            # we might get an empty string here
            # TODO: if we use obtain() instead, we get an error complaining
            # '' cannot be converted to int (via Constraint as defined for
            # "datalad.repo.version" in common_cfg
            # => Allow conversion to result in None?
            if not version:
                version = None

        if fix_it:
            self._init(version=version, description=description)
            self.fsck()

        # Check whether an annex already exists at destination
        # XXX this doesn't work for a submodule!

        # NOTE/TODO: following should be cheaper. We are in __init__ here and
        # already know that GitRepo.is_valid_repo is True, since super.__init__
        # was called. Calling AnnexRepo.is_valid will unnecessarily check that
        # again:
        if not AnnexRepo.is_valid_repo(self.path):
            # so either it is not annex at all or just was not yet initialized
            if self.is_with_annex():
                # it is an annex repository which was not initialized yet
                if create or init:
                    lgr.debug('Annex repository was not yet initialized at %s.'
                              ' Initializing ...' % self.path)
                    self._init(version=version, description=description)
            elif create:
                lgr.debug('Initializing annex repository at %s...' % self.path)
                self._init(version=version, description=description)
            else:
                raise InvalidAnnexRepositoryError("No annex found at %s." % self.path)

        self._direct_mode = None  # we don't know yet

        # If we are in direct mode already, we need to make
        # this instance aware of that. This especially means, that we need to
        # adapt self._GIT_COMMON_OPTIONS by calling set_direct_mode().
        # Could happen in case we didn't specify anything, but annex forced
        # direct mode due to FS or an already existing repo was in direct mode,
        if self._is_direct_mode_from_config():
            self.set_direct_mode()

        # - only force direct mode; don't force indirect mode
        # - parameter `direct` has priority over config
        if direct is None:
            direct = (create or init) and \
                     self.config.getbool("datalad", "repo.direct", default=False)
        self._direct_mode = None  # we don't know yet
        if direct and not self.is_direct_mode():
            # direct mode is available below version 6 repos only.
            # Note: If 'annex.version' is missing in .git/config for some
            # reason, we need to try to set direct mode:
            repo_version = self.config.getint("annex", "version")
            if (repo_version is None) or (repo_version < 6):
                lgr.debug("Switching to direct mode (%s)." % self)
                self.set_direct_mode()
            else:
                # TODO: This may change to either not being a warning and/or
                # to use 'git annex unlock' instead.
                lgr.warning("direct mode not available for %s. Ignored." % self)

        self._batched = BatchedAnnexes(
            batch_size=batch_size, git_options=self._ANNEX_GIT_COMMON_OPTIONS)

        # set default backend for future annex commands:
        # TODO: Should the backend option of __init__() also migrate
        # the annex, in case there are annexed files already?
        if backend:
            self.set_default_backend(backend, persistent=True)

        if self._ALLOW_LOCAL_URLS:
            self._allow_local_urls()

    def _allow_local_urls(self):
        """Allow URL schemes and addresses which potentially could be harmful.

        For now it is internal method used within tests only
        """
        # from annex 6.20180626 file:/// and http://localhost access isn't
        # allowed by default
        self.config.add(
            'annex.security.allowed-url-schemes', 'http https file',
            'local')
        self.config.add(
            'annex.security.allowed-http-addresses', 'all',
            'local')

    def set_default_backend(self, backend, persistent=True, commit=True):
        """Set default backend

        Parameters
        ----------
        backend : str
        persistent : bool, optional
          If persistent, would add/commit to .gitattributes. If not -- would
          set within .git/config
        """
        # TODO: 'annex.backends' actually is a space separated list.
        # Figure out, whether we want to allow for a list here or what to
        # do, if there is sth in that setting already
        if persistent:
            # could be set in .gitattributes or $GIT_DIR/info/attributes
            if 'annex.backend' in self.get_gitattributes('.')['.']:
                lgr.debug(
                    "Not (re)setting backend since seems already set in git attributes"
                )
            else:
                lgr.debug("Setting annex backend to %s (persistently)", backend)
                self.config.set('annex.backends', backend, where='local')
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
            self.config.set('annex.backends', backend, where='local')

    def __del__(self):

        def safe__del__debug(e):
            """We might be too late in the game and either .debug or exc_str
            are no longer bound"""
            try:
                return lgr.debug(exc_str(e))
            except (AttributeError, NameError):
                return

        try:
            if hasattr(self, '_batched') and self._batched is not None:
                self._batched.close()
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
        try:
            super(AnnexRepo, self).__del__()
        except TypeError as e:
            # see above
            safe__del__debug(e)

    def _set_shared_connection(self, remote_name, url):
        """Make sure a remote with SSH URL uses shared connections.

        Set ssh options for annex on a per call basis, using
        '-c remote.<name>.annex-ssh-options'.

        Note
        ----
        There's currently no solution for using these connections, if the SSH
        URL is just connected to a file instead of a remote
        (`annex addurl` for example).

        Parameters
        ----------
        remote_name: str
        url: str
        """
        from datalad.support.network import is_ssh
        # Note:
        #
        # before any possible invocation of git-annex
        # Temporary approach to ssh connection sharing:
        # Register every ssh remote with the corresponding control master.
        # Issues:
        # - currently overwrites existing ssh config of the remote
        # - request SSHConnection instance and write config even if no
        #   connection needed (but: connection is not actually created/opened)
        # - no solution for a ssh url of a file (annex addurl)

        if is_ssh(url):
            c = ssh_manager.get_connection(url)
            ssh_cfg_var = "remote.{0}.annex-ssh-options".format(remote_name)
            # options to add:
            # Note: must use -S to overload -S provided by annex itself
            # if we provide -o ControlPath=... it is not in effect
            # Note: ctrl_path must not contain spaces, since it seems to be
            # impossible to anyhow guard them here
            # http://git-annex.branchable.com/bugs/cannot___40__or_how__63____41___to_pass_socket_path_with_a_space_in_its_path_via_annex-ssh-options/
            cfg_string = "-o ControlMaster=auto -S %s" % c.ctrl_path
            # read user-defined options from .git/config:
            cfg_string_old = self.config.get(ssh_cfg_var, None)
            self._annex_common_options += \
                ['-c', 'remote.{0}.annex-ssh-options={1}{2}'
                       ''.format(remote_name,
                                 (cfg_string_old + " ") if cfg_string_old else "",
                                 cfg_string
                                 )]

    def is_managed_branch(self, branch=None):
        """Whether `branch` is managed by git-annex.

        ATM this returns true in direct mode (branch 'annex/direct/my_branch')
        and if on an adjusted branch (annex v6+ repository:
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
        if branch and \
            (branch.startswith('annex/direct/') or
             branch.startswith('adjusted/')):
            return True
        return False

    def get_corresponding_branch(self, branch=None):
        """In case of a managed branch, get the corresponding one.

        If `branch` is not a managed branch, return that branch without any
        changes.

        Note: Since default for `branch` is the active branch,
        `get_corresponding_branch()` is equivalent to `get_active_branch()` if
        the active branch is not a managed branch.

        Parameters
        ----------
        branch: str
          name of the branch; defaults to active branch

        Returns
        -------
        str
          name of the corresponding branch if there is any, name of the queried
          branch otherwise.
        """

        if branch is None:
            branch = self.get_active_branch()

        if self.is_managed_branch(branch):
            if branch.startswith('annex/direct/'):
                cor_branch = branch[13:]
            elif branch.startswith('adjusted/'):
                if branch.endswith('(unlocked)'):
                    cor_branch = branch[9:-10]
                elif branch.endswith('(fixed)'):
                    cor_branch = branch[9:-7]
                else:
                    cor_branch = branch[9:]
                    lgr.warning("Unexpected naming of adjusted branch '{}'.{}"
                                "Assuming '{}' to be the corresponding branch."
                                "".format(branch, linesep, cor_branch))
            else:
                raise NotImplementedError(
                    "Detection of annex-managed branch '{}' follows a pattern "
                    "not implemented herein.".format(branch))
            return cor_branch

        else:
            return branch

    def get_tracking_branch(self, branch=None, corresponding=True):
        """Get the tracking branch for `branch` if there is any.

        By default returns the tracking branch of the corresponding branch if
        `branch` is a managed branch.

        Parameters
        ----------
        branch: str
          local branch to look up. If none is given, active branch is used.
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
                        branch=self.get_corresponding_branch(branch)
                        if corresponding else branch)

    def _submodules_dirty_direct_mode(self,
            untracked=True, deleted=True, modified=True, added=True,
            type_changed=True, path=None):
        """Get modified submodules

        Workaround for http://git-annex.branchable.com/bugs/git_annex_status_fails_with_submodule_in_direct_mode/

        This is using git-annex-status with --ignore-submodules to not let
        git-status try to recurse into annex submodules without a working tree.
        Therefore we need to do the recursion on our own.

        Note, that added submodules will just be reported dirty. It's at very
        least difficult to distinguish whether a submodule in direct mode was
        just added or modified. ATM not worth the effort, I think.
        This is leads to a bit inconsistent reportings by AnnexRepo.status()
        whenever it needs to call this subroutine and there are added submodules.

        Intended to be used by AnnexRepo.status() internally.
        """

        # Note: We do a lazy recursion. The only thing we need to know is
        # whether or not a submodule is to be reported dirty. Once we already
        # know it is, there's no need to go any deeper in the hierarchy.
        # Apart from better performance, this also allows us to inspect each
        # submodule separately, and therefore be able to deal with mixed
        # hierarchies of git and annex submodules!

        modified_subs = []
        for sm in self.get_submodules():
            sm_dirty = False

            # First check for changes committed in the submodule, using
            # git submodule summary -- path,
            # since this can't be detected from within the submodule.
            if self.is_submodule_modified(sm.name):
                sm_dirty = True

            # check state of annex submodules, that might be in direct mode
            elif AnnexRepo.is_valid_repo(opj(self.path, sm.path),
                                         allow_noninitialized=False):

                sm_repo = AnnexRepo(opj(self.path, sm.path),
                                    create=False, init=False)

                sm_status = sm_repo.get_status(untracked=untracked, deleted=deleted,
                                               modified=modified, added=added,
                                               type_changed=type_changed,
                                               submodules=False, path=path)
                if any([bool(sm_status[i]) for i in sm_status]):
                    sm_dirty = True

            # check state of submodule, that is a plain git or not an
            # initialized annex, which we can safely treat as a plain git, too.
            elif GitRepo.is_valid_repo(opj(self.path, sm.path)):
                sm_repo = GitRepo(opj(self.path, sm.path))

                # TODO: Clarify issue: GitRepo.is_dirty() doesn't fit our parameters
                if sm_repo.is_dirty(index=deleted or modified or added or type_changed,
                                    working_tree=deleted or modified or added or type_changed,
                                    untracked_files=untracked,
                                    submodules=False, path=path):
                    sm_dirty = True
            else:
                # uninitialized submodule
                # it can't be dirty and we can't recurse any deeper:
                continue

            if sm_dirty:
                # the submodule itself is dirty
                modified_subs.append(sm.path)
            else:
                # the submodule itself is clean, recurse:
                # TODO: This fails ATM with AttributeError, if sm is a GitRepo.
                # we need get_status and this recursion method to be available
                # to both classes. Issue: We need to be able to come back to
                # AnnexRepo from GitRepo if there's again an annex beneath. But
                # we can't import AnnexRepo in gitrepo.py.
                modified_subs.extend(
                    sm_repo._submodules_dirty_direct_mode(
                        untracked=untracked, deleted=deleted,
                        modified=modified, added=added,
                        type_changed=type_changed, path=path
                    ))

        return modified_subs

    def get_status(self, untracked=True, deleted=True, modified=True, added=True,
                   type_changed=True, submodules=True, path=None):
        """Return various aspects of the status of the annex repository

        Note: Under certain circumstances newly added submodules might be
        reported as 'modified' rather tha 'added'.
        See `AnnexRepo._submodules_dirty_direct_mode` for details.

        Parameters
        ----------
        untracked
        deleted
        modified
        added
        type_changed
        submodules
        path

        Returns
        -------

        """

        self.precommit()

        options = assure_list(path) if path else []
        if not submodules:
            options.extend(to_options(ignore_submodules='all'))

        # BEGIN workaround bug (see self._submodules_dirty_direct_mode)
        # internal call to 'git status' by 'git annex status' will fail
        # in submodules without a working tree (direct mode)
        # How to catch this case depends on annex version, since annex
        # exits zero until version 6.20170307

        def _fake_exception_wrapper(self, options_):
            """generate a faked `CommandError` from logged stderr output"""

            # this is for use with older annex, which didn't exit non-zero
            # in case of the failure we are interested in

            # TODO: If we are to keep this workaround (we probably rely on a
            # newer annex anyway), we should not use swallow_logs, since we
            # actually don't want to swallow it, but inspect it. Use a proper
            # handler/filter for the logger instead to not create temp files via
            # swallow_logs

            old_log_state = self.cmd_call_wrapper.log_outputs
            self.cmd_call_wrapper._log_opts['outputs'] = True

            with swallow_logs(new_level=logging.ERROR) as cml:
                # Note, that _run_annex_command_json returns a generator
                json_list = \
                    list(self._run_annex_command_json(
                        'status', opts=options_, expect_stderr=False))
            self.cmd_call_wrapper._log_opts['outputs'] = old_log_state
            if "fatal:" in cml.out:
                raise CommandError(cmd="git annex status",
                                   msg=cml.out, stderr=cml.out)
            return json_list

        try:
            if self.git_annex_version < '6.20170307':
                json_list = _fake_exception_wrapper(self, options_=options)
            else:
                json_list = \
                    list(self._run_annex_command_json(
                        'status', opts=options, expect_stderr=False))
        except CommandError as e:
            if submodules and AnnexRepo._is_annex_work_tree_message(e.stderr):
                lgr.debug("git-annex-status failed probably due to submodule in"
                          " direct mode. Trying to workaround.")
                # try again, ignoring submodules:
                options = [path] if path else []
                options.extend(to_options(ignore_submodules='all'))
                json_list = list(
                    self._run_annex_command_json('status', opts=options)
                )
                # separately get modified submodules:
                m_subs = \
                    self._submodules_dirty_direct_mode(untracked=untracked,
                                                       deleted=deleted,
                                                       modified=modified,
                                                       added=added,
                                                       type_changed=type_changed,
                                                       path=path)
                json_list.extend({'file': p, 'status': 'M'} for p in m_subs)
            else:
                # not the known bug we want to catch
                raise e

        # END workaround

        key_mapping = [(untracked, 'untracked', '?'),
                       (deleted, 'deleted', 'D'),
                       (modified, 'modified', 'M'),
                       (added, 'added', 'A'),
                       (type_changed, 'type_changed', 'T')]
        from datalad.utils import with_pathsep
        return {key: [with_pathsep(i['file'])
                      if isdir(opj(self.path, i['file'])) else i['file']
                      # for consistency with 'git status' return directories
                      # with trailing path separator
                      for i in json_list if i['status'] == st]
                for cond, key, st in key_mapping if cond}

    @borrowdoc(GitRepo)
    def is_dirty(self, index=True, working_tree=False, untracked_files=True,
                 submodules=True, path=None):
        # TODO: Add doc on how this differs from GitRepo.is_dirty()
        # Parameter working_tree exists to meet the signature of GitRepo.is_dirty()

        if working_tree:
            # Note: annex repos don't always have a git working tree and the
            # behaviour in direct mode or V6+ repos is fundamentally different
            # from that concept. There are no unstaged changes in direct mode
            # for example. Therefore the need to call this method with
            # 'working_tree=True' indicates invalid assumptions in the
            # calling code.

            # TODO: Better exception. InvalidArgumentError or sth ...
            raise CommandNotAvailableError(
                "Querying a git-annex repository for a clean/dirty "
                "working tree is an invalid concept.")
        # Again note, that 'annex status' isn't distinguishing staged and
        # unstaged changes, since this makes little sense for an annex repo
        # in general. Therefore we use only 'index' and 'untracked_files' to
        # specify what kind of dirtyness we are interested in:
        status = self.get_status(untracked=untracked_files, deleted=index,
                                 modified=index, added=index,
                                 type_changed=index, submodules=submodules,
                                 path=path)
        return any([bool(status[i]) for i in status])

    @property
    def untracked_files(self):
        """Get a list of untracked files
        """
        return self.get_status(untracked=True, deleted=False, modified=False,
                               added=False, type_changed=False, submodules=False,
                               path=None)['untracked']

    @classmethod
    def _check_git_annex_version(cls):
        ver = external_versions['cmd:annex']
        # in case it is missing
        if linux_distribution_name in {'debian', 'ubuntu'}:
            msg = "Install  git-annex-standalone  from NeuroDebian " \
                  "(http://neuro.debian.net)"
        else:
            msg = "Visit http://git-annex.branchable.com/install/"
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

    @staticmethod
    def get_size_from_key(key):
        """A little helper to obtain size encoded in a key"""
        if not key:
            return None
        try:
            size_str = key.split('-', 2)[1].lstrip('s')
        except IndexError:
            # has no 2nd field in the key
            return None
        return int(size_str) if size_str.isdigit() else None

    @normalize_path
    def get_file_size(self, path):
        fpath = opj(self.path, path)
        return 0 if not exists(fpath) else os.stat(fpath).st_size

    # TODO: Once the PR containing super class 'Repo' was merged, move there and
    # melt with GitRepo.get_toppath including tests for both
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

        # first try plain git result:
        toppath = GitRepo.get_toppath(path=path, follow_up=follow_up,
                                      git_options=git_options)
        if toppath == '':
            # didn't fail, so git itself didn't come to the conclusion
            # there is no repo, but we have no actual result;
            # might be an annex in direct mode
            if git_options is None:
                git_options = []
            # TODO: Apparently doesn't work with git 2.11.0
            # Note: Since we are in a classmethod, GitRepo.get_toppath uses
            # Runner directly instead of _git_custom_command, which is why the
            # common mechanics for direct mode are not applied.
            # This is why there is no solution for git 2.11 yet

            # Note 2: Actually, the above issue is irrelevant. The git
            # executable has no repository it is bound to, since it's the
            # purpose of the call to find this repository. Therefore
            # core.bare=False has no effect at all.

            # Disabled. See notes.
            # git_options.extend(['-c', 'core.bare=False'])
            # toppath = GitRepo.get_toppath(path=path, follow_up=follow_up,
            #                               git_options=git_options)

            # basically a copy of code in GitRepo.get_toppath
            # except it uses 'git rev-parse --git-dir' as a workaround for
            # direct mode:

            from os.path import dirname
            from os import pardir

            cmd = ['git']
            if git_options:
                cmd.extend(git_options)

            cmd.append("rev-parse")
            if external_versions['cmd:git'] >= '2.13.0':
                cmd.append("--absolute-git-dir")
            else:
                cmd.append("--git-dir")

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
                toppath = AnnexRepo.get_toppath(dirname(path),
                                                follow_up=follow_up,
                                                git_options=git_options)

            if external_versions['cmd:git'] < '2.13.0':
                # we got a path relative to `path` instead of an absolute one
                toppath = opj(path, toppath)

            # we got the git-dir. Assuming the root dir we are looking for is
            # one level up:
            toppath = realpath(normpath(opj(toppath, pardir)))

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

    @classmethod
    def is_valid_repo(cls, path, allow_noninitialized=False):
        """Return True if given path points to an annex repository
        """
        # Note: default value for allow_noninitialized=False is important
        # for invalidating an instance via self._flyweight_invalid. If this is
        # changed, we also need to override _flyweight_invalid and explicitly
        # pass allow_noninitialized=False!

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
                return initialized_annex \
                    or GitRepo(path, create=False, init=False).is_with_annex()
            except (NoSuchPathError, InvalidGitRepositoryError):
                return False
        else:
            return initialized_annex

    def add_remote(self, name, url, options=None):
        """Overrides method from GitRepo in order to set
        remote.<name>.annex-ssh-options in case of a SSH remote."""
        super(AnnexRepo, self).add_remote(name, url, options if options else [])
        self._set_shared_connection(name, url)

    def set_remote_url(self, name, url, push=False):
        """Overrides method from GitRepo in order to set
        remote.<name>.annex-ssh-options in case of a SSH remote."""

        super(AnnexRepo, self).set_remote_url(name, url, push=push)
        self._set_shared_connection(name, url)

    def set_remote_dead(self, name):
        """Announce to annex that remote is "dead"
        """
        return self._annex_custom_command([], ["git", "annex", "dead", name])

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

    def get_special_remotes(self):
        """Get info about all known (not just enabled) special remotes.

        Returns
        -------
        dict
          Keys are special remote UUIDs, values are dicts with arguments
          for `git-annex enableremote`. This includes at least the 'type'
          and 'name' of a special remote. Each type of special remote
          may require addition arguments that will be available in the
          respective dictionary.
        """
        try:
            stdout, stderr = self._git_custom_command(
                None, ['git', 'cat-file', 'blob', 'git-annex:remote.log'],
                expect_fail=True)
        except CommandError as e:
            if 'Not a valid object name git-annex:remote.log' in e.stderr:
                # no special remotes configures
                return {}
            else:
                # some unforseen error
                raise e
        argspec = re.compile(r'^([^=]*)=(.*)$')
        srs = {}
        for line in stdout.splitlines():
            # be precise and split by spaces
            fields = line.split(' ')
            # special remote UUID
            sr_id = fields[0]
            # the rest are config args for enableremote
            sr_info = dict(argspec.match(arg).groups()[:2] for arg in fields[1:])
            srs[sr_id] = sr_info
        return srs

    def __repr__(self):
        return "<AnnexRepo path=%s (%s)>" % (self.path, type(self))

    def _run_annex_command(self, annex_cmd,
                           git_options=None, annex_options=None,
                           backend=None, jobs=None,
                           files=None,
                           merge_annex_branches=True,
                           **kwargs):
        """Helper to run actual git-annex calls

        Unifies annex command calls.

        Parameters
        ----------
        annex_cmd: str
            the actual git-annex command, like 'init' or 'add'
        git_options: list of str
            options to be passed to git
        annex_options: list of str
            options to be passed to the git-annex command
        backend: str
            backend to be used by this command; Currently this can also be
            achieved by having an item '--backend=XXX' in annex_options.
            This may change.
        jobs : int
        files: list, optional
            If command passes list of files. If list is too long
            (by number of files or overall size) it will be split, and multiple
            command invocations will follow
        merge_annex_branches: bool, optional
            If False, annex.merge-annex-branches=false config will be set for
            git-annex call.  Useful for operations which are not intended to
            benefit from updating information about remote git-annexes
        **kwargs
            these are passed as additional kwargs to datalad.cmd.Runner.run()

        Raises
        ------
        CommandNotAvailableError
            if an annex command call returns "unknown command"
        """
        debug = ['--debug'] if lgr.getEffectiveLevel() <= 8 else []
        backend = ['--backend=%s' % backend] if backend else []

        git_options = (git_options[:] if git_options else []) + self._ANNEX_GIT_COMMON_OPTIONS
        annex_options = annex_options[:] if annex_options else []
        if self._annex_common_options:
            annex_options = self._annex_common_options + annex_options

        if not self.always_commit:
            git_options += ['-c', 'annex.alwayscommit=false']

        if not merge_annex_branches:
            git_options += ['-c', 'annex.merge-annex-branches=false']

        if git_options:
            cmd_list = ['git'] + git_options + ['annex']
        else:
            cmd_list = ['git-annex']
        if jobs:
            annex_options += ['-J%d' % jobs]

        cmd_list += [annex_cmd] + backend + debug + annex_options

        env = kwargs.pop("env", None)
        if self.fake_dates_enabled:
            env = self.add_fake_dates(env)

        try:
            # TODO: RF to use --batch where possible instead of splitting
            # into multiple invocations
            return self._run_command_files_split(
                self.cmd_call_wrapper.run,
                cmd_list,
                files,
                env=env, **kwargs)
        except CommandError as e:
            if e.stderr and "git-annex: Unknown command '%s'" % annex_cmd in e.stderr:
                raise CommandNotAvailableError(str(cmd_list),
                                               "Unknown command:"
                                               " 'git-annex %s'" % annex_cmd,
                                               e.code, e.stdout, e.stderr)
            else:
                raise

    def _run_simple_annex_command(self, *args, **kwargs):
        """Run an annex command and return its output, of which expect 1 line

        Just a little helper to interact with basic annex commands and process
        their output while ignoring some messages

        Parameters
        ----------
        **kwargs: all passed into _run
        """
        out, err = self._run_annex_command(
            *args, **kwargs
        )
        lines = out.rstrip('\n').splitlines()
        # ignore some lines which might appear on a fresh clone
        # see https://git-annex.branchable.com/todo/output_of_wanted___40__and_possibly_group_etc__41___should_not_be_polluted_with___34__informational__34___messages/
        lines_ = [
            l for l in lines
            if not re.search(
                r'\((merging .* into git-annex|recording state ).*\.\.\.\)', l
            )
        ]
        assert(len(lines_) <= 1)
        return lines_[0] if lines_ else None

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
        # TEMP: Disable lazy loading and make sure to read from file every time
        # instead, since we might have several instances pointing to the very
        # same repo atm. TODO: We can remove that, right?
        self.repo.config_reader()._is_initialized = False
        self.repo.config_reader().read()
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
            # that unlocked pointers aren't supported.
            return False

    def set_direct_mode(self, enable_direct_mode=True):
        """Switch to direct or indirect mode

        Parameters
        ----------
        enable_direct_mode: bool
            True means switch to direct mode,
            False switches to indirect mode

        Raises
        ------
        CommandNotAvailableError
            in case you try to switch to indirect mode on a crippled filesystem
        """
        if self.is_crippled_fs() and not enable_direct_mode:
            raise CommandNotAvailableError(
                cmd="git-annex indirect",
                msg="Can't switch to indirect mode on that filesystem.")

        self._run_annex_command('direct' if enable_direct_mode else 'indirect',
                                expect_stderr=True)
        self.config.reload()

        # For paranoid we will just re-request
        self._direct_mode = None
        assert(self.is_direct_mode() == enable_direct_mode)

        if self.is_direct_mode():
            # adjust git options for plain git calls on this repo:
            # Note: Not sure yet, whether this solves the issue entirely or we
            # still need 'annex proxy' in some cases ...

            lgr.debug("detected git version: %s" % external_versions['cmd:git'])

            if external_versions['cmd:git'] >= '2.9.0':
                # workaround for git 2.9.0, which for some reason ignores the
                # per-call config "-c core.bare=False", but respects the value
                # if it is set in .git/config
                self.GIT_DIRECT_MODE_WRAPPER_ACTIVE = True

            # TEMP: nevertheless use this option to inject it into gitpython
            # TODO: Solve it and change to "elif"
            if 'core.bare=False' not in self._GIT_COMMON_OPTIONS:
                # standard direct mode procedure part I:
                self._GIT_COMMON_OPTIONS.extend(['-c', 'core.bare=False'])
            if '--work-tree=' not in self._GIT_COMMON_OPTIONS:
                # standard direct mode procedure part II:
                self._GIT_COMMON_OPTIONS.append('--work-tree=.')

    def _git_custom_command(self, *args, **kwargs):

        if self.GIT_DIRECT_MODE_PROXY:
            proxy_str = "git annex proxy -- "
            proxy_list = ['git', 'annex', 'proxy', '--']
            cmd = kwargs.pop("cmd_str", None)
            if not cmd:
                cmd = args[1]
            assert(cmd is not None)

            if isinstance(cmd, string_types):
                cmd = proxy_str + cmd
            else:
                cmd = proxy_list + cmd

            args = (args[0], cmd) + args[2:]
            return super(AnnexRepo, self)._git_custom_command(*args, **kwargs)

        elif self.GIT_DIRECT_MODE_WRAPPER_ACTIVE:
            old = self.config.get('core.bare')
            lgr.debug("old config: %s(%s)" % (old, type(old)))
            if old is not False:
                self.config.set('core.bare', 'False', where='local')

            try:
                out, err = super(AnnexRepo, self)._git_custom_command(
                    *args, **kwargs)
            finally:
                if old is None:
                    self.config.unset('core.bare', where='local')
                elif old:
                    self.config.set('core.bare', old, where='local')
            return out, err

        else:
            return super(AnnexRepo, self)._git_custom_command(*args, **kwargs)

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
        # TODO: Document (or implement respectively) behaviour in special cases
        # like direct mode (if it's different), not existing paths, etc.
        opts = []
        if description is not None:
            opts += [description]
        if version is not None:
            opts += ['--version', '{0}'.format(version)]
        if not len(opts):
            opts = None

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
            new_branch = self.get_corresponding_branch(orig_branch)
            new_section = "branch.{}".format(new_branch)
            for opt in self.config.options(sct):
                orig_value = self.config.get_value(sct, opt)
                new_value = orig_value.replace(orig_branch, new_branch)
                self.config.add(var=new_section + "." + opt,
                                value=new_value,
                                where='local',
                                reload=False)
        self._run_annex_command(
            'init',
            log_stderr=lambda s: lgr.info(s.rstrip()), log_online=True,
            annex_options=opts)
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

        if remote:
            if remote not in self.get_remotes():
                raise RemoteNotAvailableError(
                    remote=remote,
                    cmd="get",
                    msg="Remote is not known. Known are: %s"
                    % (self.get_remotes(),)
                )
            options += ['--from', remote]

        # analyze provided files to decide which actually are needed to be
        # fetched

        if not key:
            expected_downloads, fetch_files = self._get_expected_files(
                files, ['--not', '--in', 'here'],
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
            kwargs = {'opts': options + ['--key'] + files}
        else:
            kwargs = {'opts': options, 'files': files}
        results = self._run_annex_command_json(
            'get',
            # TODO: eventually make use of --batch mode
            jobs=jobs,
            expected_entries=expected_downloads,
            progress=True,
            **kwargs
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
        for j in self._run_annex_command_json(
                'find', opts=expr, files=files,
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
        list of dict
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
        # Note: As long as we support direct mode, one should not call
        # super().add() directly. Once direct mode is gone, we might remove
        # `git` parameter and call GitRepo's add() instead.

        def _get_to_be_added_recs(paths):
            """Try to collect what actually is going to be added

            This is used for progress information
            """

            if self.is_direct_mode():
                # we already know we can't use --dry-run
                for r in self._process_git_get_output(
                        linesep.join(["'{}'".format(p.encode('utf-8'))
                        for p in paths])):
                    yield r
                    return
            else:
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
                    if AnnexRepo._is_annex_work_tree_message(e.stderr):
                        lgr.warning(
                            "Known bug in direct mode."
                            "We can't use --dry-run when there are submodules in "
                            "direct mode, because the internal call to git status "
                            "fails. To be resolved by using (Dataset's) status "
                            "instead of a git-add --dry-run altogether.")
                        # fake the return for now
                        for r in self._process_git_get_output(
                                linesep.join(["'{}'".format(f)
                                for f in files])):
                            yield r
                            return
                    else:
                        # unexpected failure
                        raise e

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
        if git is not None:
            options += [
                '-c',
                'annex.largefiles=%s' % (('anything', 'nothing')[int(git)])
            ]
            if git:
                # to maintain behaviour similar to git
                options += ['--include-dotfiles']

        if git and update:
            # explicitly use git-add with --update instead of git-annex-add
            # TODO: This might still need some work, when --update AND files
            # are specified!
            if self.is_direct_mode() and not files:
                self.GIT_DIRECT_MODE_PROXY = True
            try:
                for r in super(AnnexRepo, self).add(
                        files,
                        git=True,
                        git_options=git_options,
                        update=update):
                    yield r
            finally:
                if self.is_direct_mode() and not files:
                    # don't accidentally cause other git calls to be done
                    # via annex-proxy
                    self.GIT_DIRECT_MODE_PROXY = False

        else:
            for r in self._run_annex_command_json(
                    'add',
                    opts=options,
                    files=files,
                    backend=backend,
                    expect_fail=True,
                    jobs=jobs,
                    expected_entries=expected_additions,
                    expect_stderr=True):
                yield r

    def proxy(self, git_cmd, **kwargs):
        """Use git-annex as a proxy to git

        This is needed in case we are in direct mode, since there's no git
        working tree, that git can handle.

        Parameters
        ----------
        git_cmd: list of str
            the actual git command
        `**kwargs`: dict, optional
            passed to _run_annex_command

        Returns
        -------
        (stdout, stderr)
            output of the command call
        """
        # TODO: We probably don't need it anymore

        if not self.is_direct_mode():
            lgr.warning("proxy() called in indirect mode: %s" % git_cmd)
            raise CommandNotAvailableError(cmd="git annex proxy",
                                           msg="Proxy doesn't make sense"
                                               " if not in direct mode.")
        return self._run_annex_command('proxy',
                                       annex_options=['--'] + git_cmd,
                                       **kwargs)

    @normalize_paths
    def get_file_key(self, files, batch=None):
        """Get key of an annexed file.

        Parameters
        ----------
        files: str or list
            file(s) to look up
        batch: None or bool, optional
            If True, `lookupkey --batch` process will be used, which would
            not crash even if provided file is not under annex (but directly
            under git), but rather just return an empty string. If False,
            invokes without --batch. If None, use batch mode if more than a
            single file is provided.

        Returns
        -------
        str or list
            keys used by git-annex for each of the files;
            in case of a list an empty string is returned if there was no key
            for that file

        Raises
        ------
        FileInGitError
             If running in non-batch mode and a file is under git, not annex
        FileNotInAnnexError
             If running in non-batch mode and a file is not under git at all
        """

        if batch or (batch is None and len(files) > 1):
            return self._batched.get('lookupkey', path=self.path)(files)
        else:
            files = files[0]
            # single file
            # keep current implementation
            # TODO: This should change, but involves more RF'ing and an
            # alternative regarding FileNotInAnnexError
            cmd_str = 'git annex lookupkey %s' % files  # have a string for messages

            try:
                out, err = self._run_annex_command(
                    'lookupkey',
                    files=[files],
                    expect_fail=True
                )
            except CommandError as e:
                if e.code == 1:
                    if not exists(opj(self.path, files)):
                        raise IOError(e.code, "File not found.", files)
                    # XXX you don't like me because I can be real slow!
                    elif files in self.get_indexed_files():
                        # if we got here, the file is present and in git,
                        # but not in the annex
                        raise FileInGitError(cmd=cmd_str,
                                             msg="File not in annex, but git: %s"
                                                 % files,
                                             filename=files)
                    else:
                        raise FileNotInAnnexError(cmd=cmd_str,
                                                  msg="File not in annex: %s"
                                                      % files,
                                                  filename=files)
                else:
                    # Not sure, whether or not this can actually happen
                    raise e

            entries = out.rstrip(linesep).splitlines()
            # filter out the ones which start with (: http://git-annex.branchable.com/bugs/lookupkey_started_to_spit_out___34__debug__34___messages_to_stdout/?updated
            entries = list(filter(lambda x: not x.startswith('('), entries))
            if len(entries) > 1:
                lgr.warning("Got multiple entries in reply asking for a key of a file: %s"
                            % (str(entries)))
            elif not entries:
                raise FileNotInAnnexError("Could not get a key for a file(s) %s -- empty output" % files)
            return entries[0]

    @normalize_paths
    def lock(self, files, options=None):
        """undo unlock

        Use  this to undo an unlock command if you don't want to modify the
        files any longer, or have made modifications you want to discard.

        Parameters
        ----------
        files: list of str
        options: list of str
        """

        options = options[:] if options else []
        self._run_annex_command('lock', annex_options=options, files=files)
        # note: there seems to be no output by annex if success.

    @normalize_paths
    def unlock(self, files, options=None):
        """unlock files for modification

        Parameters
        ----------
        files: list of str
        options: list of str

        Returns
        -------
        list of str
          successfully unlocked files
        """

        options = options[:] if options else []

        if self.is_direct_mode():

            # TODO:
            # If anything there should be a CommandNotAvailableError now:
            lgr.debug("'%s' is in direct mode, "
                      "'annex unlock' not available", self)
            lgr.warning("In direct mode there is no 'unlock'. However if "
                        "the file's content is present, it is kind of "
                        "unlocked. Therefore just checking whether this is "
                        "the case.")
            # TODO/FIXME:
            # Note: the following isn't exactly nice, if `files` is a dir.
            # For a "correct" result we would need to report all files within
            # potential dir(s) in `files`, that are annexed and have content.
            # Also note, that even now files in git might be reported "unlocked",
            # since they have content. This might be a confusing result.
            # On the other hand, this is solved on the level of Dataset.unlock
            # by annotating those paths 'notneeded' beforehand.
            return [f for f in files if self.file_has_content(f)]

        else:

            # TODO: catch and parse output if failed (missing content ...)
            std_out, std_err = \
                self._run_annex_command(
                    'unlock', annex_options=options, files=files
                )

            return [line.split()[1]
                    for line in std_out.splitlines()
                    if line.split()[0] == 'unlock' and line.split()[-1] == 'ok']

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
        self._run_annex_command('adjust', annex_options=options)

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

        std_out, std_err = self._run_annex_command(
            'unannex', annex_options=options, files=files
        )
        return [line.split()[1] for line in std_out.splitlines()
                if line.split()[0] == 'unannex' and line.split()[-1] == 'ok']

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
                    obj, er = self._run_annex_command(
                        'find', files=[f],
                        annex_options=["--print0"],
                        expect_fail=True,
                        merge_annex_branches=False
                    )
                    items = obj.rstrip("\0").split("\0")
                    objects[f] = items[0] if len(items) == 1 else items
                except CommandError:
                    objects[f] = ''

        return objects

    def _check_files(self, fn, quick_fn, files, allow_quick, batch):
        # Helper that isolates the common logic in `file_has_content` and
        # `is_under_annex`. `fn` is the annex command used to do the check, and
        # `quick_fn` is the non-annex variant.
        pointers = self.supports_unlocked_pointers
        if pointers or self.is_direct_mode() or batch or not allow_quick:
            # We're only concerned about modified files in V6+ mode. In V5
            # `find` returns an empty string for unlocked files, and in direct
            # mode everything looks modified, so we don't even bother.
            modified = self.get_changed_files() if pointers else []
            annex_res = fn(files, normalize_paths=False, batch=batch)
            return [bool(annex_res.get(f) and
                         not (pointers and normpath(f) in modified))
                    for f in files]
        else:  # ad-hoc check which should be faster than call into annex
            return [quick_fn(f) for f in files]

    @normalize_paths
    def file_has_content(self, files, allow_quick=True, batch=False):
        """Check whether files have their content present under annex.

        Parameters
        ----------
        files: list of str
            file(s) to check for being actually present.
        allow_quick: bool, optional
            allow quick check, based on having a symlink into .git/annex/objects.
            Works only in non-direct mode (TODO: thin mode)

        Returns
        -------
        list of bool
            For each input file states whether file has content locally
        """
        # TODO: Also provide option to look for key instead of path

        def quick_check(filename):
            filepath = opj(self.path, filename)
            if islink(filepath):                    # if symlink
                # find abspath of node pointed to by symlink
                target_path = realpath(filepath)  # realpath OK
                # TODO: checks for being not outside of this repository
                # Note: ben removed '.git/' from '.git/annex/objects',
                # since it is not true for submodules, whose '.git' is a
                # symlink and being resolved to some
                # '.git/modules/.../annex/objects'
                return exists(target_path) and 'annex/objects' in str(target_path)
            return False

        return self._check_files(self.find, quick_check,
                                 files, allow_quick, batch)

    @normalize_paths
    def is_under_annex(self, files, allow_quick=True, batch=False):
        """Check whether files are under annex control

        Parameters
        ----------
        files: list of str
            file(s) to check for being under annex
        allow_quick: bool, optional
            allow quick check, based on having a symlink into .git/annex/objects.
            Works only in non-direct mode (TODO: thin mode)

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

        def quick_check(filename):
            filepath = opj(self.path, filename)
            # todo checks for being not outside of this repository
            # Note: ben removed '.git/' from '.git/annex/objects',
            # since it is not true for submodules, whose '.git' is a
            # symlink and being resolved to some
            # '.git/modules/.../annex/objects'
            return (
                islink(filepath)
                and 'annex/objects' in str(realpath(filepath))  # realpath OK
            )

        return self._check_files(check, quick_check,
                                 files, allow_quick, batch)

    def init_remote(self, name, options):
        """Creates a new special remote

        Parameters
        ----------
        name: str
            name of the special remote
        """
        # TODO: figure out consistent way for passing options + document

        self._run_annex_command('initremote', annex_options=[name] + options)
        self.config.reload()

    def enable_remote(self, name, env=None):
        """Enables use of an existing special remote

        Parameters
        ----------
        name: str
            name, the special remote was created with
        """

        try:
            self._run_annex_command(
                'enableremote',
                annex_options=[name],
                expect_fail=True,
                log_stderr=True,
                env=env)
        except CommandError as e:
            if re.match(r'.*StatusCodeException.*statusCode = 401', e.stderr):
                raise AccessDeniedError(e.stderr)
            elif 'FailedConnectionException' in e.stderr:
                raise AccessFailedError(e.stderr)
            else:
                raise e
        self.config.reload()

    def merge_annex(self, remote=None):
        """Merge git-annex branch

        Merely calls `sync` with the appropriate arguments.

        Parameters
        ----------
        remote: str, optional
          Name of a remote to be "merged".
        """
        self.sync(
            remotes=remote, push=False, pull=False, commit=False, content=False,
            all=False)

    def sync(self, remotes=None, push=True, pull=True, commit=True,
             content=False, all=False, fast=False):
        """Synchronize local repository with remotes

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
        # In direct mode annex-sync fails, if commit=True
        # apparently sync is calling git status internally, which then fails
        # in the submodule. (As we already know)
        # stdout:
        # commit  add second ok
        # (recording state in git...)
        #
        # failed
        # (recording state in git...)
        #
        # stderr:
        # fatal: This operation must be run in a work tree
        # fatal: 'git status --porcelain' failed in submodule submod
        # git-annex: user error (xargs ["-0","git","--git-dir=.git","--work-tree=.","--literal-pathspecs","add","-f"] exited 123)
        # fatal: This operation must be run in a work tree
        # fatal: 'git status --porcelain' failed in submodule submod
        # git-annex: user error (xargs ["-0","git","--git-dir=.git","--work-tree=.","--literal-pathspecs","add","-f"] exited 123)

        # TODO: Workaround

        args = []
        args.extend(to_options(push=push, no_push=not push,
                               # means: '--push' if push else '--no-push'
                               pull=pull, no_pull=not pull,
                               commit=commit, no_commit=not commit,
                               content=content, no_content=not content,
                               all=all,
                               fast=fast))
        args.extend(assure_list(remotes))
        self._run_annex_command('sync', annex_options=args)

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
        git_options = []
        kwargs = dict(backend=backend)
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
            if PY2:
                files_opt = assure_bytes(files_opt)
            out_json = self._run_annex_command_json(
                'addurl',
                opts=options + [files_opt] + [url],
                progress=True,
                expected_entries={file_: None},
                **kwargs
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
                    msg="Adding url %s to file %s failed due to %s" % (url, file_, exc_str(exc)))
            assert(out_json['command'] == 'addurl')
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

        Parameters
        ----------
        urls: list of str

        options: list, optional
            options to the annex command

        cwd: string, optional
            working directory from within which to invoke git-annex
        """

        if git_options:
            lgr.warning("add_urls: git_options not yet implemented. Ignored.")

        if annex_options:
            lgr.warning("annex_options not yet implemented. Ignored.")

        options = options[:] if options else []

        self._run_annex_command('addurl', annex_options=options + urls,
                                backend=backend, log_online=True,
                                log_stderr=False, cwd=cwd)
        # Don't capture stderr, since download progress provided by wget uses
        # stderr.

        # currently simulating similar return value, assuming success
        # for all files:
        # TODO: Make return values consistent across both *Repo classes!
        return [{u'file': f, u'success': True} for f in urls]

    @normalize_path
    def rm_url(self, file_, url):
        """Record that the file is no longer available at the url.

        Parameters
        ----------
        file_: str

        url: str
        """

        self._run_annex_command('rmurl', files=[file_, url])

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
        return locations.get(AnnexRepo.WEB_UUID, {}).get('urls', [])

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

        options = assure_list(options)

        if key:
            # we can't drop multiple in 1 line, and there is no --batch yet, so
            # one at a time
            files = assure_list(files)
            options = options + ['--key']
            res = [
                self._run_annex_command_json(
                    'drop',
                    opts=options + [k],
                    jobs=jobs)
                for k in files
            ]
            # `normalize_paths` ... magic, useful?
            if len(files) == 1:
                return res[0]
            else:
                return res
        else:
            return self._run_annex_command_json(
                'drop',
                opts=options,
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
        keys = [keys] if isinstance(keys, string_types) else keys

        options = options[:] if options else []
        options += ['--force']
        if not batch or self.fake_dates_enabled:
            if batch:
                lgr.debug("Not batching drop_key call "
                          "because fake dates are enabled")
            json_objects = self._run_annex_command_json(
                'dropkey', opts=options, files=keys, expect_stderr=True
            )
        else:
            json_objects = self._batched.get(
                'dropkey',
                annex_options=options, json=True, path=self.path
            )(keys)
        for j in json_objects:
            assert j.get('success', True)

    # TODO: a dedicated unit-test
    def _whereis_json_to_dict(self, j):
        """Convert json record returned by annex whereis --json to our dict representation for it
        """
        assert (j.get('success', True) is True)
        # process 'whereis' containing list of remotes
        remotes = {remote['uuid']: {x: remote.get(x, None)
                                    for x in ('description', 'here', 'urls')
                                    }
                   for remote in j.get('whereis')}
        if self.WEB_UUID in remotes:
            assert(remotes[self.WEB_UUID]['description'] == 'web')
        return remotes

    def _run_annex_command_json(self, command,
                                opts=None,
                                jobs=None,
                                files=None,
                                expected_entries=None,
                                progress=False,
                                **kwargs):
        """Run an annex command with --json and load output results into a tuple of dicts

        Parameters
        ----------
        expected_entries : dict, optional
          If provided `filename/key: size` dictionary, will be used to create
          ProcessAnnexProgressIndicators to display progress
        progress: bool, optional
          Whether to request/handle --json-progress
        **kwargs
          Passed to ._run_annex_command
        """
        progress_indicators = None
        if expected_entries:
            progress_indicators = ProcessAnnexProgressIndicators(
                expected=expected_entries
            )
            kwargs = kwargs.copy()
            kwargs.update(dict(
                log_stdout=progress_indicators,
                log_stderr='offline',  # False, # to avoid lock down
                log_online=True
            ))
        # TODO: refactor to account for possible --batch ones
        annex_options = ['--json']
        if progress:
            annex_options += ['--json-progress']

        if jobs == 'auto':
            jobs = N_AUTO_JOBS
        if jobs and jobs != 1:
            annex_options += ['-J%d' % jobs]
        if opts:
            # opts might be the '--key' which should go last
            annex_options += opts

        interrupted = True
        try:
            out, err = self._run_annex_command(
                    command,
                    files=files,
                    annex_options=annex_options,
                    **kwargs)
            interrupted = False
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
                raise OutOfSpaceError(cmd="annex %s" % command,
                                      sizemore_msg=out_of_space_re.groups()[0])

            # RemoteNotAvailableError:
            remote_na_re = re.search(
                "there is no available git remote named \"(.*)\"", e.stderr
            )
            if remote_na_re:
                raise RemoteNotAvailableError(cmd="annex %s" % command,
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

            # Note: try to approach the covering of potential annex failures
            # in a more general way:
            # first check stdout:
            if all([line.startswith('{') and line.endswith('}')
                    for line in e.stdout.splitlines()]):
                # we have the usual json output on stdout. Therefore we can
                # probably return and don't need to raise; so get stdout
                # for json loading:
                out = e.stdout
            else:
                out = None

            # Note: Workaround for not existing files as long as annex doesn't
            # report it within JSON response:
            # see http://git-annex.branchable.com/bugs/copy_does_not_reflect_some_failed_copies_in_--json_output/
            not_existing = [
                # cut the file path from the middle, no useful delimiter
                # need to deal with spaces too!
                line[11:-10] for line in e.stderr.splitlines()
                if line.startswith('git-annex:') and
                line.endswith(' not found')
            ]
            if not_existing:
                if out is None:
                    # we create the error reporting herein. If all files were
                    # not found, there is nothing on stdout and we don't need
                    # anything
                    out = ""
                if not out.endswith(linesep):
                    out += linesep
                out += linesep.join(
                    ['{{"command": "{cmd}", "file": "{path}", '
                     '"note": "{note}",'
                     '"success": false}}'.format(
                         cmd=command,
                         # gotta quote backslashes that have taken over...
                         # ... or the outcome is not valid JSON
                         path=f.replace('\\', '\\\\'),
                         note="not found")
                     for f in not_existing])

            # Note: insert additional code here to analyse failure and possibly
            # raise a custom exception

            # if we didn't raise before, just depend on whether or not we seem
            # to have some json to return. It should contain information on
            # failure in keys 'success' and 'note'
            # TODO: This is not entirely true. 'annex status' may return empty,
            # while there was a 'fatal:...' in stderr, which should be a
            # failure/exception
            # Or if we had empty stdout but there was stderr
            if out is None or (not out and e.stderr):
                raise e
            if e.stderr:
                # else just warn about present errors
                shorten = lambda x: x[:1000] + '...' if len(x) > 1000 else x
                lgr.warning(
                    "Running %s resulted in stderr output: %s",
                    command, shorten(e.stderr)
                )
        finally:
            if progress_indicators:
                progress_indicators.finish(partial=interrupted)

        others, json_strs = partition((ln for ln in out.splitlines()),
                                      lambda ln: ln.startswith('{'))

        json_objects = (json_loads(line) for line in json_strs)
        # protect against progress leakage
        json_objects = [j for j in json_objects if 'byte-progress' not in j]

        others = [ln for ln in others if ln.strip()]
        if others:
            if json_objects:
                # We at least received some valid json output, so warn about
                # non-json output and continue.
                lgr.warning("Received non-json lines for --json command: %s",
                            others)
            else:
                annex_ver = external_versions['cmd:annex']
                if annex_ver == "7.20190626" and command == "find":
                    # TODO: Drop this once GIT_ANNEX_MIN_VERSION is over
                    # 7.20190626.
                    exc = BrokenExternalDependency(
                        "find --json output is broken on git-annex 7.20190626")
                else:
                    exc = RuntimeError(
                        "Received no json output for --json command, only:\n{}"
                        .format("  ".join(others)))
                raise exc
        return json_objects

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
        if batch:
            lgr.warning("TODO: --batch mode for whereis.  Operating serially")

        OUTPUTS = {'descriptions', 'uuids', 'full'}
        if output not in OUTPUTS:
            raise ValueError(
                "Unknown value output=%r. Known are %s"
                % (output, ', '.join(map(repr, OUTPUTS)))
            )

        options = assure_list(options, copy=True)
        if key:
            kwargs = {'opts': options + ["--key"] + files}
        else:
            kwargs = {'files': files}

        json_objects = self._run_annex_command_json('whereis', **kwargs)
        if output in {'descriptions', 'uuids'}:
            return [
                [remote.get(output[:-1]) for remote in j.get('whereis')]
                if j.get('success') else []
                for j in json_objects
            ]
        elif output == 'full':
            # TODO: we might want to optimize storage since many remotes entries will be the
            # same so we could just reuse them instead of brewing copies
            return {
                j['key' if (key or '--all' in options) else 'file']
                : self._whereis_json_to_dict(j)
                for j in json_objects
                if not j.get('key').endswith('.this-is-a-test-key')
            }

    # TODO:
    # I think we should make interface cleaner and less ambigious for those annex
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
            json_objects = self._run_annex_command_json(
                'info', opts=options, files=files, merge_annex_branches=False)
        else:
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
            assert(j.pop('file') == f)
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

        Returns
        -------
        dict
          Info for the repository, with keys matching the ones returned by annex
        merge_annex_branches: bool, optional
          Either to allow git-annex if needed to merge annex branches, e.g. to
          make sure up to date descriptions for git annex remotes
        """

        options = ['--bytes', '--fast'] if fast else ['--bytes']

        json_records = list(self._run_annex_command_json(
            'info', opts=options, merge_annex_branches=merge_annex_branches)
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
        A list of file names
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
                args.extend(['--in', 'here'])
        out, err = self._run_annex_command(
            'find', annex_options=args, merge_annex_branches=False
        )
        # TODO: JSON
        return out.splitlines()

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
          Whether the setting is returned, or an empty string if there
          is none.

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
        return self._run_simple_annex_command(
            property,
            annex_options=[remote or '.'])

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
        return self._run_simple_annex_command(
            property,
            annex_options=[remote or '.', expr])

    def get_groupwanted(self, name):
        """Get `groupwanted` expression for a group `name`

        Parameters
        ----------
        name : str
           Name of the groupwanted group
        """
        return self._run_simple_annex_command(
            'groupwanted', annex_options=[name]
        )

    def set_groupwanted(self, name, expr):
        """Set `expr` for the `name` groupwanted"""
        return self._run_simple_annex_command(
            'groupwanted', annex_options=[name, expr]
        )

    def precommit(self):
        """Perform pre-commit maintenance tasks, such as closing all batched annexes
        since they might still need to flush their changes into index
        """
        if self._batched is not None:
            self._batched.close()
        super(AnnexRepo, self).precommit()

    @borrowdoc(GitRepo)
    def commit(self, msg=None, options=None, _datalad_msg=False,
               careless=True, files=None, proxy=False):
        self.precommit()

        if files:
            files = assure_list(files)

        # Note: `proxy` is for explicitly enforcing the use of git-annex-proxy
        #       in direct mode. This is needed in very special cases, which
        #       might go away once we figured out a better way. In any case, it
        #       should turn into something that is automatically considered and
        #       not done by the caller of this method.

        if proxy:
            if not self.is_direct_mode():
                raise CommandNotAvailableError(
                    cmd="git-annex-proxy",
                    msg="git-annex-proxy is available in direct mode only")
            else:
                if _datalad_msg:
                    msg = self._get_prefixed_commit_msg(msg)
                if not msg:
                    if options:
                        if "--allow-empty-message" not in options:
                            options.append("--allow-empty-message")
                    else:
                        options = ["--allow-empty-message"]

                # committing explicitly given paths in direct mode via proxy
                # used to fail, because absolute paths are used. Using annex
                # proxy this leads to an error (path outside repository)
                if files:
                    if options is None:
                        options = []
                    for i in range(len(files)):
                        if isabs(files[i]):
                            options.append(normpath(relpath(files[i],
                                                            start=self.path)))
                        else:
                            options.append(files[i])
                try:
                    self.proxy(['git', 'commit'] + (['-m', msg] if msg else []) +
                               (options if options else []),
                               expect_stderr=True, expect_fail=True)
                except CommandError as e:
                    if 'nothing to commit' in e.stdout:
                        if careless:
                            lgr.debug("nothing to commit in {}. "
                                      "Ignored.".format(self))
                        else:
                            raise
                    elif 'no changes added to commit' in e.stdout or \
                            'nothing added to commit' in e.stdout:
                        if careless:
                            lgr.debug("no changes added to commit in {}. "
                                      "Ignored.".format(self))
                        else:
                            raise
                    elif "did not match any file(s) known to git." in e.stderr:
                        # TODO:
                        # Improve FileNotInXXXXError classes to better deal with
                        # multiple files; Also consider PathOutsideRepositoryError
                        raise FileNotInRepositoryError(cmd=e.cmd,
                                                       msg="File(s) unknown to git",
                                                       code=e.code,
                                                       filename=linesep.join(
                                                    [l for l in e.stderr.splitlines()
                                                     if l.startswith("pathspec")]))
                    else:
                        raise
        else:

            # Note: See the note on `proxy` parameter at the top of this method.
            #       Trying to automatically use git-annex-proxy, whenever we
            #       fail to commit the usual way via options to git in direct
            #       mode. In particular this can happen if sth was staged via
            #       git-annex-proxy, which is needed for --update option for
            #       example.

            if files:
                # Raise FileNotInRepositoryError if `files` aren't tracked.
                try:
                    super(AnnexRepo, self).commit(
                        "dryrun", options=["--dry-run", "--no-status"],
                        files=files)
                except CommandError as e:
                    if not (self.is_direct_mode() and
                            AnnexRepo._is_annex_work_tree_message(e.stderr)):
                        raise
                    # The git call may fail with
                    #   fatal: this operation must be run in a work tree
                    #   fatal: 'git status --porcelain=2' failed in submodule ...
                    # But that error message doesn't matter for the purpose of
                    # the "file is tracked" check. It won't be shown if there
                    # is a pathspec error.
                    lgr.debug("Ignoring commit --dry-run failure")
            try:
                alt_index_file = None

                direct_mode = self.is_direct_mode()
                # we might need to avoid explicit paths
                files_to_commit = None if direct_mode else files
                if files:
                    # In direct mode, if we commit file(s) they would get
                    # committed directly into git ignoring possibly being
                    # staged by annex.  So, if not all files are committed, and
                    # assuming that what is to be committed is staged (!could be
                    # wrong assumption), we need to prepare a custom index, and
                    # commit without specifying any paths.
                    # In indirect mode, "git commit files" might fail if some
                    # files "jumped" between git/annex.  Then also preparing a
                    # custom index and calling "commit" without files resolves
                    # the issue
                    all_changed_staged = \
                        set(self.get_changed_files(staged=True))

                    files_normalized = [
                        _normalize_path(self.path, f) if isabs(f) else f
                        for f in files
                    ]

                    files_changed_staged = \
                        set(self.get_changed_files(staged=True, files=files_normalized))
                    files_changed_notstaged = \
                        set() \
                        if direct_mode \
                        else set(self.get_changed_files(staged=False, files=files_normalized))

                    # Files which were staged but not among files
                    staged_not_to_commit = all_changed_staged.difference(files_changed_staged)

                    if files_changed_notstaged:
                        self.add(files=list(files_changed_notstaged))

                    if staged_not_to_commit:
                        # Need an alternative index_file
                        with make_tempfile(dir=opj(self.path,
                                                   GitRepo.get_git_dir(self)),
                                           prefix="datalad-",
                                           suffix=".index") as index_file:

                            alt_index_file = index_file
                            index_tree = self.repo.git.write_tree()
                            self.repo.git.read_tree(index_tree,
                                                    index_output=index_file)
                            # Reset the files we are not to be committed
                            if staged_not_to_commit:
                                self._git_custom_command(
                                    list(staged_not_to_commit),
                                    ['git', 'reset'],
                                    index_file=alt_index_file)

                            super(AnnexRepo, self).commit(
                                msg, options,
                                _datalad_msg=_datalad_msg,
                                careless=careless,
                                index_file=alt_index_file)

                            # reset current index to reflect the changes annex might have done
                            self._git_custom_command(
                                list(files_changed_notstaged |
                                     files_changed_staged),
                                ['git', 'reset']
                            )

                    # in any case we will not specify files explicitly
                    files_to_commit = None
                if not alt_index_file:
                    super(AnnexRepo, self).commit(msg, options,
                                                  _datalad_msg=_datalad_msg,
                                                  careless=careless,
                                                  files=files_to_commit)
            except CommandError as e:
                # TODO: just remove this???
                if self.is_direct_mode() and \
                    AnnexRepo._is_annex_work_tree_message(e.stderr):
                    lgr.debug("Commit failed. "
                              "Trying to commit via git-annex-proxy.")
                    self.commit(msg, options, _datalad_msg=_datalad_msg,
                                careless=careless, files=files, proxy=True)
                else:
                    raise
            finally:
                if alt_index_file and os.path.exists(alt_index_file):
                    unlink(alt_index_file)

    @normalize_paths(match_return_type=False)
    def remove(self, files, force=False, **kwargs):
        """Remove files from git/annex (works in direct mode as well)

        Parameters
        ----------
        files
        force: bool, optional
        """

        # TODO: parameter 'force' unnecessary => kwargs / to_options
        self.precommit()  # since might interfere

        return super(AnnexRepo, self).remove(files, force=force,
                                             normalize_paths=False,
                                             **kwargs)

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
                out, err = self._run_annex_command('contentlocation',
                                                   annex_options=[key],
                                                   expect_fail=True)
                return out.rstrip(linesep).splitlines()[0]
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
            key_ = self.get_file_key(file_)  # ?, batch=batch

        annex_input = (key_,) if not remote else (key_, remote)

        if not batch:
            try:
                out, err = self._run_annex_command('checkpresentkey',
                                                   annex_options=list(annex_input),
                                                   expect_fail=True)
                assert(not out)
                return True
            except CommandError:
                return False
        else:
            annex_cmd = ["checkpresentkey"] + ([remote] if remote else [])
            out = self._batched.get(
                ':'.join(annex_cmd), annex_cmd,
                path=self.path)(key_)
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

    @normalize_paths(match_return_type=False)
    def _annex_custom_command(
            self, files, cmd_str, log_stdout=True, log_stderr=True,
            log_online=False, expect_stderr=False, cwd=None, env=None,
            shell=None, expect_fail=False):
        """Allows for calling arbitrary commands.

        Helper for developing purposes, i.e. to quickly implement git-annex
        commands for proof of concept.

        Parameters
        ----------
        files: list of files
        cmd_str: str
            arbitrary command str. `files` is appended to that string.

        Returns
        -------
        stdout, stderr
        """
        cmd = shlex.split(cmd_str + " " + " ".join(files), posix=not on_windows) \
            if isinstance(cmd_str, string_types) \
            else cmd_str + files

        if self.fake_dates_enabled:
            env = self.add_fake_dates(env)

        return self.cmd_call_wrapper.run(
            cmd,
            log_stderr=log_stderr, log_stdout=log_stdout, log_online=log_online,
            expect_stderr=expect_stderr,
            cwd=cwd, env=env, shell=shell, expect_fail=expect_fail)

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
        self._run_annex_command('migrate',
                                annex_options=files,
                                backend=backend)

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
            self.get_key_backend(self.get_file_key(f))
            for f in files
        ]

    @property
    def default_backends(self):
        self.config.reload()
        backends = self.config.get("annex.backends", default=None)
        if backends:
            return backends.split()
        else:
            return None

    def fsck(self):
        self._run_annex_command('fsck')

    # TODO: we probably need to override get_file_content, since it returns the
    # symlink's target instead of the actual content.

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
            if not isdir(files[0]):
                self.get_file_key(files[0])

        # TODO: RF -- logic is duplicated with get() -- the only difference
        # is the verb (copy, copy) or (get, put) and remote ('here', remote)?
        if '--key' not in options:
            expected_copys, copy_files = self._get_expected_files(
                files, ['--in', 'here', '--not', '--in', remote])
        else:
            copy_files = files
            assert(len(files) == 1)
            expected_copys = {files[0]: AnnexRepo.get_size_from_key(files[0])}

        if not copy_files:
            lgr.debug("No files found needing copying.")
            return []

        if len(copy_files) != len(files):
            lgr.debug("Actually copying %d files", len(copy_files))

        annex_options = ['--to=%s' % remote]
        if options:
            annex_options.extend(shlex.split(options))

        # TODO: provide more meaningful message (possibly aggregating 'note'
        #  from annex failed ones
        results = self._run_annex_command_json(
            'copy',
            opts=annex_options,
            files=files,  # copy_files,
            jobs=jobs,
            expected_entries=expected_copys,
            progress=True
            #log_stdout=True, log_stderr=not log_online,
            #log_online=log_online, expect_stderr=True
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
            if not self.repo:
                return None
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
                for k, remotes in iteritems(info)
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
            self.config.set(var, url, where='local', reload=True)
        super(AnnexRepo, self).set_remote_url(name, url, push)

    def get_metadata(self, files, timestamps=False):
        """Query git-annex file metadata

        Parameters
        ----------
        files : str or list(str)
          One or more paths for which metadata is to be queried.
        timestamps: bool, optional
          If True, the output contains a '<metadatakey>-lastchanged'
          key for every metadata item, reflecting the modification
          time, as well as a 'lastchanged' key with the most recent
          modification time of any metadata item.

        Returns
        -------
        generator
          One tuple per file (could be more items than input arguments
          when directories are given). First tuple item is the filename,
          second item is a dictionary with metadata key/value pairs. Note that annex
          metadata tags are stored under the key 'tag', which is a
          regular metadata item that can be manipulated like any other.
        """
        if not files:
            return
        files = assure_list(files)
        opts = ['--json']
        for res in self._run_annex_command_json(
                'metadata', opts=opts, files=files):
            yield (
                res['file'],
                res['fields'] if timestamps else \
                {k: v for k, v in res['fields'].items()
                 if not k.endswith('lastchanged')})

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
        generator
          JSON obj per modified file
        """

        def _genspec(expr, d):
            return [expr.format(k, v) for k, vs in d.items() for v in assure_list(vs)]

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

        for jsn in self._run_annex_command_json(
                'metadata',
                args,
                files=files):
            yield jsn

    @staticmethod
    def _is_annex_work_tree_message(out):
        return re.match(
            r'.*This operation must be run in a work tree.*'
            r'git status.*failed in submodule',
            out,
            re.MULTILINE | re.DOTALL | re.IGNORECASE)

# TODO: Why was this commented out?
# @auto_repr
class BatchedAnnexes(dict):
    """Class to contain the registry of active batch'ed instances of annex for
    a repository
    """
    def __init__(self, batch_size=0, git_options=None):
        self.batch_size = batch_size
        self.git_options = git_options or []
        super(BatchedAnnexes, self).__init__()

    def get(self, codename, annex_cmd=None, **kwargs):
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

    def __del__(self):
        self.close()


def readline_rstripped(stdout):
    #return iter(stdout.readline, b'').next().rstrip()
    return stdout.readline().rstrip()


def readlines_until_ok_or_failed(stdout, maxlines=100):
    """Read stdout until line ends with ok or failed"""
    out = ''
    i = 0
    lgr.log(3, "Trying to receive from %s" % stdout)
    while not stdout.closed:
        i += 1
        if maxlines > 0 and i > maxlines:
            raise IOError("Expected no more than %d lines. So far received: %r" % (maxlines, out))
        lgr.log(2, "Expecting a line")
        line = stdout.readline()
        lgr.log(2, "Received line %r" % line)
        out += line
        if re.match(r'^.*\b(failed|ok)$', line.rstrip()):
            break
    return out.rstrip()


def readline_json(stdout):
    toload = stdout.readline().strip()
    return json_loads(toload) if toload else {}


@auto_repr
class BatchedAnnex(object):
    """Container for an annex process which would allow for persistent communication
    """

    def __init__(self, annex_cmd, git_options=None, annex_options=None, path=None,
                 json=False,
                 output_proc=None):
        if not isinstance(annex_cmd, list):
            annex_cmd = [annex_cmd]
        self.annex_cmd = annex_cmd
        self.git_options = git_options if git_options else []
        annex_options = annex_options if annex_options else []
        self.annex_options = annex_options + (['--json'] if json else [])
        self.path = path
        if output_proc is None:
            output_proc = readline_json if json else readline_rstripped
        self.output_proc = output_proc
        self._process = None
        self._stderr_out = None
        self._stderr_out_fname = None

    def _initialize(self):
        # TODO -- should get all those options about --debug and --backend which are used/composed
        # in AnnexRepo class
        lgr.debug("Initiating a new process for %s" % repr(self))
        cmd = ['git'] + self.git_options + \
              ['annex'] + self.annex_cmd + self.annex_options + ['--batch']  # , '--debug']
        lgr.log(5, "Command: %s" % cmd)
        # TODO: look into _run_annex_command  to support default options such as --debug
        #
        # according to the internet wisdom there is no easy way with subprocess
        # while avoid deadlocks etc.  We would need to start a thread/subprocess
        # to timeout etc
        # kwargs = dict(bufsize=1, universal_newlines=True) if PY3 else {}
        self._stderr_out, self._stderr_out_fname = tempfile.mkstemp()
        self._process = Popen(
            cmd, stdin=PIPE, stdout=PIPE,  stderr=self._stderr_out,
            env=GitRunner.get_git_environ_adjusted(),
            cwd=self.path,
            bufsize=1,
            universal_newlines=True  # **kwargs
        )

    def _check_process(self, restart=False):
        """Check if the process was terminated and restart if restart

        Returns
        -------
        bool
          True if process was alive.
        str
          stderr if any recorded if was terminated
        """
        process = self._process
        ret = True
        ret_stderr = None
        if process and process.poll():
            lgr.warning("Process %s was terminated with returncode %s" % (process, process.returncode))
            ret_stderr = self.close(return_stderr=True)
            ret = False
        if self._process is None and restart:
            lgr.warning("Restarting the process due to previous failure")
            self._initialize()
        return ret, ret_stderr

    def __call__(self, cmds):
        """

        Parameters
        ----------
        cmds : str or tuple or list of (str or tuple)

        Returns
        -------
        str or list
          Output received from annex.  list in case if cmds was a list
        """
        # TODO: add checks -- may be process died off and needs to be reinitiated
        if not self._process:
            self._initialize()

        input_multiple = isinstance(cmds, list)
        if not input_multiple:
            cmds = [cmds]

        output = []

        for entry in cmds:
            if not isinstance(entry, string_types):
                entry = ' '.join(entry)
            entry = entry + '\n'
            lgr.log(5, "Sending %r to batched annex %s" % (entry, self))
            # apparently communicate is just a one time show
            # stdout, stderr = self._process.communicate(entry)
            # according to the internet wisdom there is no easy way with subprocess
            self._check_process(restart=True)
            process = self._process  # _check_process might have restarted it
            process.stdin.write(assure_bytes(entry) if PY2 else entry)
            process.stdin.flush()
            lgr.log(5, "Done sending.")
            still_alive, stderr = self._check_process(restart=False)
            # TODO: we might want to handle still_alive, e.g. to allow for
            #       a number of restarts/resends, but it should be per command
            #       since for some we cannot just resend the same query. But if
            #       it is just a "get"er - we could resend it few times
            # We are expecting a single line output
            # TODO: timeouts etc
            stdout = assure_unicode(self.output_proc(process.stdout)) \
                if not process.stdout.closed else None
            if stderr:
                lgr.warning("Received output in stderr: %r", stderr)
            lgr.log(5, "Received output: %r" % stdout)
            output.append(stdout)

        return output if input_multiple else output[0]

    def __del__(self):
        self.close()

    def close(self, return_stderr=False):
        """Close communication and wait for process to terminate

        Returns
        -------
        str
          stderr output if return_stderr and stderr file was there.
          None otherwise
        """
        ret = None
        if self._stderr_out:
            # close possibly still open fd
            os.fdopen(self._stderr_out).close()
            self._stderr_out = None
        if self._process:
            process = self._process
            lgr.debug(
                "Closing stdin of %s and waiting process to finish", process)
            process.stdin.close()
            process.stdout.close()
            process.wait()
            self._process = None
            lgr.debug("Process %s has finished", process)
        if self._stderr_out_fname and os.path.exists(self._stderr_out_fname):
            if return_stderr:
                with open(self._stderr_out_fname, 'r') as f:
                    ret = f.read()
            # remove the file where we kept dumping stderr
            unlink(self._stderr_out_fname)
            self._stderr_out_fname = None
        return ret


def _get_size_from_perc_complete(count, perc):
    """A helper to get full size if know % and corresponding size"""

    try:
        portion = (float(perc) / 100.)
    except ValueError:
        portion = None
    return int(math.ceil(int(count) / portion)) \
        if portion else 0


class ProcessAnnexProgressIndicators(object):
    """'Filter' for annex --json output to react to progress indicators

    Instance of this beast should be passed into log_stdout option
    for git-annex commands runner
    """

    def __init__(self, expected=None):
        """

        Parameters
        ----------
        expected: dict, optional
           key -> size, expected entries (e.g. downloads)
        """
        # looking forward for multiple downloads at the same time
        self.pbars = {}
        self.total_pbar = None
        self.expected = expected
        self.only_one_expected = expected and len(self.expected) == 1
        self._failed = 0
        self._succeeded = 0
        self.start()

    def start(self):
        if self.expected:
            from datalad.ui import ui
            total = sum(filter(bool, self.expected.values()))
            if len(self.expected) > 1:
                self.total_pbar = ui.get_progressbar(
                    label="Total", total=total)
                self.total_pbar.start()

    def __getitem__(self, id_):
        if self.pbars == 1:
            # regardless what it is, it is the one!
            # will happen e.g. in case of add_url_to_file since filename
            # is not even reported in the status and final msg just
            # reports the key which is not known before
            return self.pbars.items()[0]
        return self.pbars[id_]

    def _update_pbar(self, pbar, new_value):
        """Updates pbar while also updating possibly total pbar"""
        old_value = getattr(pbar, '_old_value', 0)
        # due to http://git-annex.branchable.com/bugs/__34__byte-progress__34___could_jump_down_upon_initiating_re-download_--_report_actual_one_first__63__/?updated
        # we will just skip the first update to avoid possible incorrect
        # reporting
        if not getattr(pbar, '_first_skipped', False):
            setattr(pbar, '_first_skipped', True)
            lgr.log(1, "Skipped first update of pbar %s", pbar)
            return
        setattr(pbar, '_old_value', new_value)
        diff = new_value - old_value
        if diff < 0:
            # so above didn't help!
            # use warnings not lgr.warn since we apparently swallow stuff
            # upstairs!  Also it would take care about issuing it only once
            lgr.debug(
                "Got negative diff for progressbar. old_value=%r, new_value=%r",
                old_value, new_value)
            return
        if self.total_pbar:
            self.total_pbar.update(diff, increment=True)
        pbar.update(new_value)

    def _log_info(self, msg):
        """Helper to log a message, so we need to clear up the pbars first"""
        if self.total_pbar:
            self.total_pbar.clear()
        for pbar in self.pbars.values():
            pbar.clear()
        lgr.info(msg)

    def __call__(self, line):
        try:
            j = json.loads(line)
        except:
            # if we fail to parse, just return this precious thing for
            # possibly further processing
            return line
        # Process some messages which remotes etc might push to us
        if list(j) == ['info']:
            # Just INFO was received without anything else -- we log it at INFO
            info = j['info']
            if info.startswith('PROGRESS-JSON: '):
                j_ = json_loads(info[len('PROGRESS-JSON: '):])
                if ('command' in j_ and 'key' in j_) or 'byte-progress' in j_:
                    j = j_
                else:
                    self._log_info(info)
            else:
                self._log_info(info)
                return

        target_size = None
        if 'command' in j and ('key' in j or 'file' in j):
            # might be the finish line message
            action_item = j.get('key') or j.get('file')
            j_action_id = (j['command'], action_item)
            pbar = self.pbars.pop(j_action_id, None)
            if pbar is None and len(self.pbars) == 1 and self.only_one_expected:
                # it is the only one left - take it!
                pbar = self.pbars.popitem()[1]
            if j.get('success') in {True, 'true'}:
                self._succeeded += 1
                if pbar:
                    self._update_pbar(pbar, pbar.total)
                elif self.total_pbar:
                    # we didn't have a pbar for this download, so total should
                    # get it all at once
                    try:
                        target_size = self.expected[action_item]
                    except:
                        target_size = None
                    if not target_size and 'key' in j:
                        target_size = AnnexRepo.get_size_from_key(j['key'])
                    self.total_pbar.update(target_size, increment=True)
            else:
                lgr.log(5, "Message with failed status: %s" % str(j))
                self._failed += 1

            if self.total_pbar:
                failed_str = (
                    ", " + ansi_colors.color_word("%d failed" % self._failed,
                                                  ansi_colors.RED)) \
                    if self._failed else ''

                self.total_pbar.set_desc(
                    "Total (%d ok%s out of %d)" % (
                        self._succeeded,
                        failed_str,
                        len(self.expected)
                        if self.expected
                        else self._succeeded + self._failed))
                # seems to be of no effect to force it repaint
                self.total_pbar.refresh()

            if pbar:
                pbar.finish()

        if 'byte-progress' not in j:
            # some other thing than progress
            return line

        # so we have a progress indicator, let's deal with it
        action = j['action']
        action_item = action.get('key') or action.get('file')
        action_id = (action['command'], action_item)
        if action_id not in self.pbars:
            # New download!
            from datalad.ui import ui
            from datalad.ui import utils as ui_utils
            # TODO: whenever target size gets reported -- used it!
            # http://git-annex.branchable.com/todo/interface_to_the___34__progress__34___of_annex_operations/#comment-6bbc26aae9867603863050ddcb09a9a0
            # for now deduce from key or approx from '%'
            # TODO: unittest etc to check when we have a relaxed
            # URL without any size known in advance
            if not target_size:
                target_size = \
                    AnnexRepo.get_size_from_key(action.get('key')) or \
                    _get_size_from_perc_complete(
                        j['byte-progress'],
                        j.get('percent-progress', '').rstrip('%')
                    ) or \
                    0
            w = ui_utils.get_console_width()

            if not action_item and self.only_one_expected:
                # must be the one!
                action_item = list(self.expected)[0]

            title = str(action.get('file') or action_item)

            pbar_right = 50
            title_len = w - pbar_right - 4  # (4 for reserve)
            if len(title) > title_len:
                half = title_len//2 - 2
                title = '%s .. %s' % (title[:half], title[-half:])
            pbar = self.pbars[action_id] = ui.get_progressbar(
                label=title, total=target_size)
            pbar.start()

        lgr.log(1, "Updating pbar for action_id=%s. annex: %s.\n",
                action_id, j)
        self._update_pbar(
            self[action_id],
            int(j.get('byte-progress'))
        )

    def finish(self, partial=False):
        if self.pbars:
            lgr.warning("Still have %d active progress bars when stopping",
                        len(self.pbars))
        if self.total_pbar:
            self.total_pbar.finish(partial=partial)
            self.total_pbar = None
        for pbar in self.pbars.values():
            pbar.finish(partial=partial)
        self.pbars = {}
        self._failed = 0
        self._succeeded = 0
