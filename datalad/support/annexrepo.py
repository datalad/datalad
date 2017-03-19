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

from itertools import chain
from os import linesep
from os import unlink
from os.path import join as opj
from os.path import exists
from os.path import islink
from os.path import realpath
from os.path import lexists
from os.path import isdir
from subprocess import Popen, PIPE
from weakref import WeakValueDictionary

from six import string_types
from six import iteritems
from six.moves import filter
from git import InvalidGitRepositoryError

from datalad import ssh_manager
from datalad.dochelpers import exc_str
from datalad.dochelpers import borrowkwargs
from datalad.utils import linux_distribution_name
from datalad.utils import nothing_cm
from datalad.utils import auto_repr
from datalad.utils import on_windows
from datalad.utils import swallow_logs
from datalad.utils import assure_list
from datalad.cmd import GitRunner

# imports from same module:
from .repo import RepoInterface
from .gitrepo import GitRepo
from .gitrepo import NoSuchPathError
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
from .exceptions import AnnexBatchCommandError
from .exceptions import InsufficientArgumentsError
from .exceptions import OutOfSpaceError
from .exceptions import RemoteNotAvailableError
from .exceptions import OutdatedExternalDependency
from .exceptions import MissingExternalDependency
from .exceptions import IncompleteResultsError

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
    # End Flyweight:

    # Web remote has a hard-coded UUID we might (ab)use
    WEB_UUID = "00000000-0000-0000-0000-000000000001"

    # To be assigned and checked to be good enough upon first call to AnnexRepo
    # 6.20161210 -- annex add  to add also changes (not only new files) to git
    GIT_ANNEX_MIN_VERSION = '6.20161210'
    git_annex_version = None

    # Workaround for per-call config issue with git 2.11.0
    GIT_DIRECT_MODE_WRAPPER_ACTIVE = False

    def __init__(self, path, url=None, runner=None,
                 direct=None, backend=None, always_commit=True, create=True,
                 init=False, batch_size=None, version=None, description=None,
                 git_opts=None, annex_opts=None, annex_init_opts=None,
                 repo=None):
        """Creates representation of git-annex repository at `path`.

        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        Parameters
        ----------
        path: str
          path to git-annex repository. In case it's not an absolute path, it's
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
          Create and initializes an annex repository at path, in case
          there is none. If set to False, and this repository is not an annex
          repository (initialized or not), an exception is raised.
        init: bool, optional
          Initialize git-annex repository (run "git annex init") if path is an
          annex repository which just was not yet initialized by annex (e.g. a
          fresh git clone). Note that if `create=True`, then initialization
          would happen
        batch_size: int, optional
          if specified and >0, instructs annex to batch this many commands before
          annex adds acts on git repository (e.g. adds them them to index for addurl).
        version: int, optional
          if given, pass as --version to `git annex init`
        description: str, optional
          short description that humans can use to identify the
          repository/location, e.g. "Precious data on my laptop"
        """
        if self.git_annex_version is None:
            self._check_git_annex_version()

        # initialize
        self._uuid = None
        self._annex_common_options = []

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
                                            git_opts=git_opts)
        except GitCommandError as e:
            if create and "Clone succeeded, but checkout failed." in str(e):
                lgr.warning("Experienced issues while cloning. "
                            "Trying to fix it, using git-annex-fsck.")
                fix_it = True
            else:
                raise e

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

        if fix_it:
            self._init(version=version, description=description)
            self.fsck()

        # Check whether an annex already exists at destination
        # XXX this doesn't work for a submodule!
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
                raise RuntimeError("No annex found at %s." % self.path)

        self._direct_mode = None  # we don't know yet

        # If we are in direct mode already, we need to make
        # this instance aware of that. This especially means, that we need to
        # adapt self._GIT_COMMON_OPTIONS by calling set_direct_mode().
        # Could happen in case we didn't specify anything, but annex forced
        # direct mode due to FS or an already existing repo was in direct mode,
        if self.is_direct_mode():
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

        # set default backend for future annex commands:
        # TODO: Should the backend option of __init__() also migrate
        # the annex, in case there are annexed files already?
        if backend:
            lgr.debug("Setting annex backend to %s", backend)
            # Must be done with explicit release, otherwise on Python3 would end up
            # with .git/config wiped out
            # see https://github.com/gitpython-developers/GitPython/issues/333#issuecomment-126633757

            # TODO: 'annex.backends' actually is a space separated list.
            # Figure out, whether we want to allow for a list here or what to
            # do, if there is sth in that setting already
            self.config.set('annex.backends', backend, where='local')

        self._batched = BatchedAnnexes(batch_size=batch_size)

    def __del__(self):
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
            lgr.debug(exc_str(e))
        try:
            super(AnnexRepo, self).__del__()
        except TypeError as e:
            # see above
            lgr.debug(exc_str(e))

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
            cfg_string = "-o ControlMaster=auto -S %s" % c.ctrl_path
            # read user-defined options from .git/config:
            cfg_string_old = self.config.get(ssh_cfg_var, None)
            self._annex_common_options += \
                ['-c', 'remote.{0}.annex-ssh-options={1}{2}'
                       ''.format(remote_name,
                                 (cfg_string_old + " ") if cfg_string_old else "",
                                 cfg_string)]

    @property
    def dirty(self):
        """Returns true if there are uncommitted changes or files not known to
        index"""
        # flush pending changes, especially close batched annex processes to
        # make sure their changes are registered
        self.precommit()

        if self.is_direct_mode():
            result = self._run_annex_command_json('status')
            # JSON result for 'git annex status'
            # {"status":"?","file":"filename"}
            # ? -- untracked
            # D -- deleted
            # M -- modified
            # A -- staged
            # T -- type changed/unlocked
            return any(result)
        else:
            return super(AnnexRepo, self).dirty

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
            git_options.extend(['-c', 'core.bare=False'])
            # TODO: Apparently doesn't work with git 2.11.0
            toppath = GitRepo.get_toppath(path=path, follow_up=follow_up,
                                          git_options=git_options)

        return toppath

    @classmethod
    def is_valid_repo(cls, path, allow_noninitialized=False):
        """Return True if given path points to an annex repository"""
        initialized_annex = GitRepo.is_valid_repo(path) and \
            exists(opj(path, '.git', 'annex'))
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

    @borrowkwargs(GitRepo)
    def get_remotes(self, with_refs_only=False, with_urls_only=False,
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
        remotes = super(AnnexRepo, self).get_remotes(
            with_refs_only=with_refs_only, with_urls_only=with_urls_only)

        if exclude_special_remotes:
            return [remote for remote in remotes
                    if not self.config.has_option('remote.{}'.format(remote),
                                                  'annex-externaltype')]
        else:
            return remotes

    def __repr__(self):
        return "<AnnexRepo path=%s (%s)>" % (self.path, type(self))

    def _run_annex_command(self, annex_cmd, git_options=None, annex_options=None,
                           backend=None, jobs=None, **kwargs):
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
        **kwargs
            these are passed as additional kwargs to datalad.cmd.Runner.run()

        Raises
        ------
        CommandNotAvailableError
            if an annex command call returns "unknown command"
        """
        debug = ['--debug'] if lgr.getEffectiveLevel() <= logging.DEBUG else []
        backend = ['--backend=%s' % backend] if backend else []

        git_options = (git_options[:] if git_options else []) + self._GIT_COMMON_OPTIONS
        annex_options = annex_options[:] if annex_options else []
        if self._annex_common_options:
            annex_options = self._annex_common_options + annex_options

        if not self.always_commit:
            git_options += ['-c', 'annex.alwayscommit=false']

        if git_options:
            cmd_list = ['git'] + git_options + ['annex']
        else:
            cmd_list = ['git-annex']
        if jobs:
            annex_options += ['-J%d' % jobs]

        cmd_list += [annex_cmd] + backend + debug + annex_options

        try:
            return self.cmd_call_wrapper.run(cmd_list, **kwargs)
        except CommandError as e:
            if e.stderr and "git-annex: Unknown command '%s'" % annex_cmd in e.stderr:
                raise CommandNotAvailableError(str(cmd_list),
                                               "Unknown command:"
                                               " 'git-annex %s'" % annex_cmd,
                                               e.code, e.stdout, e.stderr)
            else:
                raise e

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
                '\((merging .* into git-annex|recording state ).*\.\.\.\)', l
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
        # same repo atm.
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

            if external_versions['cmd:git'] >= '2.11.0':
                # workaround for git 2.11.0, which for some reason ignores the
                # per-call config "-c core.bare=False", but respects the value
                # if it is set in .git/config
                self.GIT_DIRECT_MODE_WRAPPER_ACTIVE = True

            elif 'core.bare=False' not in self._GIT_COMMON_OPTIONS:
                # standard procedure:
                self._GIT_COMMON_OPTIONS.extend(['-c', 'core.bare=False'])

    def _git_custom_command(self, *args, **kwargs):

        if self.GIT_DIRECT_MODE_WRAPPER_ACTIVE:
            old = self.config.get('core.bare')
            lgr.debug("old config: %s(%s)" % (old, type(old)))
            if old is not False:
                self.config.set('core.bare', 'False', where='local')

            out, err = super(AnnexRepo, self)._git_custom_command(*args, **kwargs)

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
        self._run_annex_command('init', annex_options=opts)
        # TODO: When to expect stderr?
        # on crippled filesystem for example (think so)?
        self.config.reload()

    @normalize_paths
    def get(self, files, options=None, jobs=None):
        """Get the actual content of files

        Parameters
        ----------
        files : list of str
            paths to get
        options : list of str, optional
            commandline options for the git annex get command
        jobs : int, optional
            how many jobs to run in parallel (passed to git-annex call)

        Returns
        -------
        files : list of dict
        """
        options = options[:] if options else []

        # analyze provided files to decide which actually are needed to be
        # fetched

        if '--key' not in options:
            expected_downloads, fetch_files = self._get_expected_downloads(
                files)
        else:
            fetch_files = files
            assert(len(files) == 1)
            expected_downloads = {files[0]: AnnexRepo.get_size_from_key(files[0])}

        if not fetch_files:
            lgr.debug("No files found needing fetching.")
            return []

        if len(fetch_files) != len(files):
            lgr.info("Actually getting %d files", len(fetch_files))

        # TODO:  check annex version and issue a one time warning if not
        # old enough for --json-progress

        # Without up to date annex, we would still report total! ;)
        if self.git_annex_version >= '6.20160923':
            # options  might be the '--key' which should go last
            options = ['--json-progress'] + options

        # Note: Currently swallowing logs, due to the workaround to report files
        # not found, but don't fail and report about other files and use JSON,
        # which are contradicting conditions atm. (See _run_annex_command_json)

        # YOH:  oh -- this puts quite a bit of stress on the pipe since now
        # annex runs in --debug mode spitting out shits load of information.
        # Since nothing was hardcoded in tests, have no clue what was expected
        # effect.  I will swallow the logs so they don't scare the user, but only
        # in non debugging level of logging
        cm = swallow_logs() \
            if lgr.getEffectiveLevel() > logging.DEBUG \
            else nothing_cm()
        # TODO: provide more meaningful message (possibly aggregating 'note'
        #  from annex failed ones
        # TODO: fail api.get -- must exit in cmdline with non-0 if anything
        # failed to download
        with cm:
            results = self._run_annex_command_json(
                'get', args=options + fetch_files,
                jobs=jobs,
                expected_entries=expected_downloads)
        results_list = list(results)
        # TODO:  should we here compare fetch_files against result_list
        # and womit an exception of incomplete download????
        return results_list

    def _get_expected_downloads(self, files):
        """Given a list of files, figure out what to be downloaded

        Parameters
        ----------
        files

        Returns
        -------
        expected_downloads : dict
          key -> size
        fetch_files : list
          files to be fetched
        """
        lgr.debug("Determine what files need to be obtained")
        # Let's figure out first which files/keys and of what size to download
        expected_downloads = {}
        fetch_files = []
        keys_seen = set()
        unknown_sizes = []  # unused atm
        # for now just record total size, and
        for j in self._run_annex_command_json(
                'find', args=['--json', '--not', '--in', 'here'] + files
        ):
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
                expected_downloads[key] = int(size)
            else:
                expected_downloads[key] = None
                unknown_sizes.append(j['file'])
        return expected_downloads, fetch_files

    @normalize_paths
    def add(self, files, git=None, backend=None, options=None, commit=False,
            msg=None, dry_run=False,
            jobs=None,
            git_options=None, annex_options=None, _datalad_msg=False):
        """Add file(s) to the repository.

        Parameters
        ----------
        files: list of str
          list of paths to add to the annex
        git: bool
          if True, add to git instead of annex.
        commit: bool
          whether or not to directly commit
        msg: str
          commit message in case `commit=True`. A default message, containing
          the list of files that were added, is created by default.
        backend:
        options:
        dry_run : bool, optional
          Calls git add with --dry-run -N --ignore-missing, to just output list
          of files to be added

        Returns
        -------
        list of dict
        """

        if git_options:
            # TODO: note that below we would use 'add with --dry-run
            # so passed here options might need to be passed into it??
            lgr.warning("git_options not yet implemented. Ignored.")

        if annex_options:
            lgr.warning("annex_options not yet implemented. Ignored.")

        options = options[:] if options else []
        # Note: As long as we support direct mode, one should not call
        # super().add() directly. Once direct mode is gone, we might remove
        # `git` parameter and call GitRepo's add() instead.
        if dry_run:
            git_options = ['--dry-run', '-N', '--ignore-missing']

            # add to git instead of annex
            if self.is_direct_mode():
                # TODO:  may be there should be a generic decorator to avoid
                # duplication and just augment how git commands are called (i.e.
                # with proxy
                add_out = self.proxy(['git', 'add'] + options + git_options + files)
                return_list = self._process_git_get_output(*add_out)

                # Note/TODO:
                # There was a reason to use the following instead of self.proxy:
                #cmd_list = ['git', '-c', 'core.bare=false', 'add'] + options + \
                #           files
                #self.cmd_call_wrapper.run(cmd_list, expect_stderr=True)
            else:
                return_list = super(AnnexRepo, self).add(files, git_options=git_options)
        else:
            # Theoretically we could have done for git as well, if it could have
            # been batched
            # Call git annex add for any to have full control of either to go
            # to git or to anex
            # 1. Figure out what actually will be added
            to_be_added_recs = self.add(files, git=True, dry_run=True)
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

            return_list = list(self._run_annex_command_json(
                'add',
                args=options + files,
                backend=backend,
                expect_fail=True,
                jobs=jobs,
                expected_entries=expected_additions,
                expect_stderr=True
            ))

        if commit:
            if msg is None:
                # TODO: centralize JSON handling
                if isinstance(return_list, list):
                    file_list = [d['file'] for d in return_list if d['success']]
                elif isinstance(return_list, dict):
                    file_list = [return_list['file']] \
                        if return_list['success'] else []
                else:
                    raise ValueError("Unexpected return type: %s" %
                                     type(return_list))
                msg = self._get_added_files_commit_msg(file_list)
            self.commit(msg, _datalad_msg=_datalad_msg)  # TODO: For consisteny: Also json return value (success)?
        return return_list

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
    def get_file_key(self, files):
        """Get key of an annexed file.

        Parameters
        ----------
        files: str or list
            file(s) to look up

        Returns
        -------
        str or list
            keys used by git-annex for each of the files;
            in case of a list an empty string is returned if there was no key
            for that file
        """

        if len(files) > 1:
            return self._batched.get('lookupkey',
                                     git_options=self._GIT_COMMON_OPTIONS,
                                     path=self.path)(files)
        else:
            files = files[0]
            # single file
            # keep current implementation
            # TODO: This should change, but involves more RF'ing and an
            # alternative regarding FileNotInAnnexError
            cmd_str = 'git annex lookupkey %s' % files  # have a string for messages

            try:
                out, err = self._run_annex_command('lookupkey',
                                                   annex_options=[files],
                                                   expect_fail=True)
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

    @normalize_paths(map_filenames_back=True)
    def find(self, files, batch=False):
        """Provide annex info for file(s).

        Parameters
        ----------
        files: list of str
            files to find under annex
        batch: bool, optional
            initiate or continue with a batched run of annex find, instead of just
            calling a single git annex find command

        Returns
        -------
        list
          list with filename if file found else empty string
        """
        objects = []
        if batch:
            objects = self._batched.get('find', git_options=self._GIT_COMMON_OPTIONS, path=self.path)(files)
        else:
            for f in files:
                try:
                    obj, er = self._run_annex_command('find', annex_options=[f], expect_fail=True)
                    objects.append(obj)
                except CommandError:
                    objects.append('')

        return objects

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
            For each input file states either file has content locally
        """
        # TODO: Also provide option to look for key instead of path

        if self.is_direct_mode() or batch or not allow_quick:  # TODO: thin mode
            # TODO: Also provide option to look for key instead of path
            find = self.find(files, normalize_paths=False, batch=batch)
            return [bool(filename) for filename in find]
        else:  # ad-hoc check which should be faster than call into annex
            out = []
            for f in files:
                filepath = opj(self.path, f)
                if islink(filepath):                    # if symlink
                    # find abspath of node pointed to by symlink
                    target_path = realpath(filepath)  # realpath OK
                    # TODO: checks for being not outside of this repository
                    # Note: ben removed '.git/' from '.git/annex/objects',
                    # since it is not true for submodules, whose '.git' is a
                    # symlink and being resolved to some
                    # '.git/modules/.../annex/objects'
                    out.append(exists(target_path) and 'annex/objects' in target_path)
                else:
                    out.append(False)
            return out

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
            For each input file states either file is under annex
        """
        # theoretically in direct mode files without content would also be
        # broken symlinks on the FSs which support it, but that would complicate
        # the matters
        if self.is_direct_mode() or batch or not allow_quick:  # TODO: thin mode
            # no other way but to call whereis and if anything returned for it
            info = self.info(files, normalize_paths=False, batch=batch)
            # info is a dict... khe khe -- "thanks" Yarik! ;)
            return [bool(info[f]) for f in files]
        else:  # ad-hoc check which should be faster than call into annex
            out = []
            for f in files:
                filepath = opj(self.path, f)
                # todo checks for being not outside of this repository
                # Note: ben removed '.git/' from '.git/annex/objects',
                # since it is not true for submodules, whose '.git' is a
                # symlink and being resolved to some
                # '.git/modules/.../annex/objects'
                out.append(
                    islink(filepath)
                    and 'annex/objects' in realpath(filepath)  # realpath OK
                )
            return out

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

    def enable_remote(self, name):
        """Enables use of an existing special remote

        Parameters
        ----------
        name: str
            name, the special remote was created with
        """

        self._run_annex_command('enableremote', annex_options=[name])
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
                        batch=False, git_options=None, annex_options=None):
        """Add file from url to the annex.

        Downloads `file` from `url` and add it to the annex.
        If annex knows `file` already,
        records that it can be downloaded from `url`.

        Parameters
        ----------
        file_: str

        url: str

        options: list
            options to the annex command

        batch: bool, optional
            initiate or continue with a batched run of annex addurl, instead of just
            calling a single git annex addurl command

        Returns
        -------
        dict
          In batch mode only ATM returns dict representation of json output returned
          by annex
        """

        if git_options:
            lgr.warning("git_options not yet implemented. Ignored.")

        if annex_options:
            lgr.warning("annex_options not yet implemented. Ignored.")

        options = options[:] if options else []
        git_options = []
        kwargs = dict(backend=backend)
        if not batch:
            self._run_annex_command('addurl',
                                    annex_options=options + ['--file=%s' % file_] + [url],
                                    log_online=True, log_stderr=False,
                                    **kwargs)
            # Don't capture stderr, since download progress provided by wget uses
            # stderr.
        else:
            options += ['--with-files']
            if backend:
                options += ['--backend=%s' % backend]
            # Initializes (if necessary) and obtains the batch process
            bcmd = self._batched.get(
                # Since backend will be critical for non-existing files
                'addurl_to_file_backend:%s' % backend,
                annex_cmd='addurl',
                git_options=self._GIT_COMMON_OPTIONS + git_options,
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
                raise AnnexBatchCommandError(
                    cmd="addurl",
                    msg="Error, annex reported failure for addurl: %s"
                    % str(out_json))
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
            lgr.warning("git_options not yet implemented. Ignored.")

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

        self._run_annex_command('rmurl', annex_options=[file_] + [url])

    @normalize_path
    def get_urls(self, file_, key=False, batch=False):
        """Get URLs for a file/key

        Parameters
        ----------
        file_: str
        key: bool, optional
            Either provided files are actually annex keys
        """
        return self.whereis(file_, output='full', batch=batch)[AnnexRepo.WEB_UUID]['urls']

    @normalize_paths
    def drop(self, files, options=None, key=False):
        """Drops the content of annexed files from this repository.

        Drops only if possible with respect to required minimal number of
        available copies.

        Parameters
        ----------
        files: list of str
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

        options = options[:] if options else []
        files = files[:] if files else []

        output_lines = []
        if key:
            # we can't drop multiple in 1 line, and there is no --batch yet, so
            # one at a time
            options = options + ['--key']
            for k in files:
                std_out, std_err = \
                    self._run_annex_command('drop', annex_options=options + [k])
                output_lines.extend(std_out.splitlines())
        else:
            std_out, std_err = \
                self._run_annex_command('drop', annex_options=options + files)
            output_lines.extend(std_out.splitlines())

        return [line.split()[1] for line in output_lines
                if line.startswith('drop') and line.endswith('ok')]

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
        if not batch:
            json_objects = self._run_annex_command_json('dropkey', args=options + keys, expect_stderr=True)
        else:
            json_objects = self._batched.get('dropkey', git_options=self._GIT_COMMON_OPTIONS, annex_options=options, json=True, path=self.path)(keys)
        for j in json_objects:
            assert j.get('success', True)

    # TODO: a dedicated unit-test
    def _whereis_json_to_dict(self, j):
        """Convert json record returned by annex whereis --json to our dict representation for it
        """
        assert (j.get('success', True) is True)
        # process 'whereis' containing list of remotes
        remotes = {remote['uuid']: {x: remote.get(x, None) for x in ('description', 'here', 'urls')}
                   for remote in j.get('whereis')}
        if self.WEB_UUID in remotes:
            assert(remotes[self.WEB_UUID]['description'] == 'web')
        return remotes

    def _run_annex_command_json(self, command, args=None, jobs=None,
                                expected_entries=None, **kwargs):
        """Run an annex command with --json and load output results into a tuple of dicts

        Parameters
        ----------
        expected_entries : dict, optional
          If provided `filename/key: size` dictionary, will be used to create
          ProcessAnnexProgressIndicators to display progress
        """
        progress_indicators = None
        try:
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
            if jobs:
                annex_options += ['-J%d' % jobs]
            if args:
                annex_options += args
            out, err = self._run_annex_command(
                command,
                annex_options=annex_options,
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
                line.split()[1] for line in e.stderr.splitlines()
                if line.startswith('git-annex:') and
                   line.endswith('not found')
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
                     '"success":false}}'.format(
                         cmd=command, path=f, note="not found")
                     for f in not_existing])

            # Note: insert additional code here to analyse failure and possibly
            # raise a custom exception

            # if we didn't raise before, just depend on whether or not we seem
            # to have some json to return. It should contain information on
            # failure in keys 'success' and 'note'
            # Or if we had empty stdout but there was stderr
            if out is None or (not out and e.stderr):
                raise e
        finally:
            if progress_indicators:
                progress_indicators.finish()

        json_objects = (json.loads(line)
                        for line in out.splitlines() if line.startswith('{'))
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
            Either provided files are actually annex keys
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

        options = assure_list(options, copy=True)
        options += ["--key"] if key else []

        json_objects = self._run_annex_command_json('whereis', args=options + files)

        if output in {'descriptions', 'uuids'}:
            return [
                [remote.get(output[:-1]) for remote in j.get('whereis')]
                if j.get('success') else []
                for j in json_objects]
        elif output == 'full':
            # TODO: we might want to optimize storage since many remotes entries will be the
            # same so we could just reuse them instead of brewing copies
            return {j['key' if (key or '--all' in options) else 'file']:
                        self._whereis_json_to_dict(j)
                    for j in json_objects}
        else:
            raise ValueError("Unknown value output=%r. Known are remotes and full" % output)

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
            json_objects = self._run_annex_command_json('info', args=options + files)
        else:
            json_objects = self._batched.get(
                'info',
                git_options=self._GIT_COMMON_OPTIONS,
                annex_options=options, json=True, path=self.path
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

    def repo_info(self, fast=False):
        """Provide annex info for the entire repository.

        Returns
        -------
        dict
          Info for the repository, with keys matching the ones returned by annex
        """

        options = ['--bytes', '--fast'] if fast else ['--bytes']

        json_records = list(self._run_annex_command_json('info', args=options))
        assert(len(json_records) == 1)

        # TODO: we need to abstract/centralize conversion from annex fields
        # For now just tune up few for immediate usability
        info = json_records[0]
        for k in info:
            if k.endswith(' size') or k.endswith(' disk space') or k.startswith('size of '):
                info[k] = int(info[k].split()[0])
        assert(info.pop('success'))
        assert(info.pop('command') == 'info')
        return info  # just as is for now

    def get_annexed_files(self, with_content_only=False):
        """Get a list of files in annex
        """
        # TODO: Review!!
        args = [] if with_content_only else ['--include', "*"]
        out, err = self._run_annex_command('find', annex_options=args)
        # TODO: JSON
        return out.splitlines()

    def get_wanted(self, remote=None):
        """Get `wanted` for the remote.  "" corresponds to none set

        Parameters
        ----------
        remote : str, optional
           If not specified (None), returns `wanted` for current repository
        """
        return self._run_simple_annex_command(
            'wanted',
            annex_options=[remote or '.']
        )

    def set_wanted(self, remote=None, expr=None):
        """Set `wanted` `expr` for the remote."""
        return self._run_simple_annex_command(
            'wanted',
            annex_options=[remote or '.', expr]
        )

    def get_group(self, remote=None):
        """Get `group` for the remote.  "" corresponds to none set

        Parameters
        ----------
        remote : str, optional
           If not specified (None), returns `group` for current repository
        """
        return self._run_simple_annex_command(
            'group',
            annex_options=[remote or '.']
        )

    def set_group(self, remote=None, group=None):
        """Set `group` of the remote."""
        return self._run_simple_annex_command(
            'group',
            annex_options=[remote or '.', group]
        )

    def get_groupwanted(self, name=None):
        """Get `groupwanted` expression for a group `name`

        Parameters
        ----------
        name : str, optional
           Name of the groupwanted group
        """
        return self._run_simple_annex_command(
            'groupwanted', annex_options=[name]
        )

    def set_groupwanted(self, name=None, expr=None):
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

    def commit(self, msg=None, options=None, _datalad_msg=False):
        """

        Parameters
        ----------
        msg: str
        options: list of str
          cmdline options for git-commit
        """
        self.precommit()
        if self.is_direct_mode():
            # committing explicitly given paths in direct mode via proxy used to
            # fail, because absolute paths are used. Using annex proxy this
            # leads to an error (path outside repository)
            if options:
                for i in range(len(options)):
                    if not options[i].startswith('-'):
                        # an option, that is not an option => it's a path
                        # TODO: comprehensive + have dedicated parameter 'files'
                        from os.path import isabs, relpath, normpath
                        if isabs(options[i]):
                            options[i] = normpath(relpath(options[i], start=self.path))

            if _datalad_msg:
                msg = self._get_prefixed_commit_msg(msg)
            if not msg:
                if options:
                    if "--allow-empty-message" not in options:
                        options.append("--allow-empty-message")
                else:
                    options = ["--allow-empty-message"]

            self.proxy(['git', 'commit'] + (['-m', msg] if msg else []) +
                       (options if options else []), expect_stderr=True)
        else:
            super(AnnexRepo, self).commit(msg, options, _datalad_msg=_datalad_msg)

    @normalize_paths(match_return_type=False)
    def remove(self, files, force=False, **kwargs):
        """Remove files from git/annex (works in direct mode as well)

        Parameters
        ----------
        files
        force: bool, optional
        """

        self.precommit()  # since might interfere
        if self.is_direct_mode():
            stdout, stderr = self.proxy(['git', 'rm'] +
                                        to_options(**kwargs) +
                                        (['--force'] if force else []) +
                                        files)
            # output per removed file is expected to be "rm 'PATH'":
            r_list = [line.strip()[4:-1] for line in stdout.splitlines()]

            # yoh gives up -- for some reason sometimes it remains,
            # so if we force -- we mean it!
            if force:
                for f in files:
                    filepath = opj(self.path, f)
                    if lexists(filepath):
                        unlink(filepath)
                        r_list.append(f)
            return r_list
        else:
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
            return self._batched.get('contentlocation', git_options=self._GIT_COMMON_OPTIONS, path=self.path)(key)

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
            Either provided files are actually annex keys
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
            out = self._batched.get(':'.join(annex_cmd), annex_cmd, git_options=self._GIT_COMMON_OPTIONS, path=self.path)(key_)
            try:
                return {
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

        return [self.get_file_key(f).split('-')[0] for f in files]

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

    @normalize_paths(match_return_type=False)  # get a list even in case of a single item
    def copy_to(self, files, remote, options=None, log_online=True):
        """Copy the actual content of `files` to `remote`

        Parameters
        ----------
        files: str or list of str
            path(s) to copy
        remote: str
            name of remote to copy `files` to
        log_online: bool
            see get()

        Returns
        -------
        list of str
           files successfully copied
        """

        # TODO: full support of annex copy options would lead to `files` being
        # optional. This means to check for whether files or certain options are
        # given and fail or just pass everything as is and try to figure out,
        # what was going on when catching CommandError

        if remote not in self.get_remotes():
            raise ValueError("Unknown remote '{0}'.".format(remote))

        # In case of single path, 'annex copy' will fail, if it cannot copy it.
        # With multiple files, annex will just skip the ones, it cannot deal
        # with. We'll do the same and report back what was successful
        # (see return value).
        # Therefore raise telling exceptions before even calling annex:
        if len(files) == 1:
            if not isdir(files[0]):
                self.get_file_key(files[0])

        # Note:
        # - annex copy fails, if `files` was a single item, that doesn't exist
        # - files not in annex or not even in git don't yield a non-zero exit,
        #   but are ignored
        # - in case of multiple items, annex would silently skip those files

        annex_options = files + ['--to=%s' % remote]
        if options:
            annex_options.extend(shlex.split(options))
        # Note:
        # As of now, there is no --json option for annex copy. Use it once this
        # changed.
        results = self._run_annex_command_json(
            'copy',
            args=annex_options,
            #log_stdout=True, log_stderr=not log_online,
            #log_online=log_online, expect_stderr=True
        )
        results = list(results)
        # check if any transfer failed since then we should just raise an Exception
        # for now to guarantee consistent behavior with non--json output
        # see https://github.com/datalad/datalad/pull/1349#discussion_r103639456
        from operator import itemgetter
        failed_copies = [e['file'] for e in results if not e['success']]
        good_copies = [
            e['file'] for e in results
            if e['success'] and
               e.get('note', '').startswith('to ')  # transfer did happen
        ]
        if failed_copies:
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
        dict
          One item per file (could be more items than input arguments
          when directories are given). Keys are filenames, values are
          dictionaries with metadata key/value pairs. Note that annex
          metadata tags are stored under the key 'tag', which is a
          regular metadata item that can be manipulated like any other.
        """
        if not files:
            return {}
        files = assure_list(files)
        args = ['--json']
        args.extend(files)
        return {res['file']:
                res['fields'] if timestamps else \
                {k: v for k, v in res['fields'].items()
                 if not k.endswith('lastchanged')}
                for res in self._run_annex_command_json('metadata', args)}

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
        None
        """

        def _genspec(expr, d):
            return [expr.format(k, v) for k, v in d.items()]

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
        # append actual file path arguments
        args.extend(assure_list(files))

        # XXX do we need the return values for anything?
        self._run_annex_command_json(
            'metadata',
            args)


# TODO: Why was this commented out?
# @auto_repr
class BatchedAnnexes(dict):
    """Class to contain the registry of active batch'ed instances of annex for
    a repository
    """
    def __init__(self, batch_size=0):
        self.batch_size = batch_size
        super(BatchedAnnexes, self).__init__()

    def get(self, codename, annex_cmd=None, **kwargs):
        if annex_cmd is None:
            annex_cmd = codename

        git_options = kwargs.pop('git_options', [])
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
    return json.loads(stdout.readline().strip())


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

        """
        process = self._process
        if process and process.poll():
            lgr.warning("Process %s was terminated with returncode %s" % (process, process.returncode))
            self.close()
        if self._process is None and restart:
            lgr.warning("Restarting the process due to previous failure")
            self._initialize()

    def __call__(self, cmds):
        """

        Parameters
        ----------
        cmds : str or tuple or list of (str or tuple)
        output_proc : callable
          To provide handling

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
            process.stdin.write(entry)  # .encode())
            process.stdin.flush()
            lgr.log(5, "Done sending.")
            # TODO: somehow do catch stderr which might be there or not
            #stderr = str(process.stderr) if process.stderr.closed else None
            self._check_process(restart=False)
            # We are expecting a single line output
            # TODO: timeouts etc
            #import pdb; pdb.set_trace()
            stdout = self.output_proc(process.stdout) if not process.stdout.closed else None
            #if stderr:
            #    lgr.warning("Received output in stderr: %r" % stderr)
            lgr.log(5, "Received output: %r" % stdout)
            output.append(stdout)

        return output if input_multiple else output[0]

    def __del__(self):
        self.close()

    def close(self):
        """Close communication and wait for process to terminate"""
        if self._stderr_out:
            # close possibly still open fd
            os.fdopen(self._stderr_out).close()
            self._stderr_out = None
        if self._stderr_out_fname and os.path.exists(self._stderr_out_fname):
            # remove the file where we kept dumping stderr
            os.unlink(self._stderr_out_fname)
            self._stderr_out_fname = None
        if self._process:
            process = self._process
            lgr.debug("Closing stdin of %s and waiting process to finish", process)
            process.stdin.close()
            process.wait()
            self._process = None
            lgr.debug("Process %s has finished", process)


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
        self._failed = 0
        self._succeeded = 0
        self.start()

    def start(self):
        if self.expected:
            from datalad.ui import ui
            total = sum(filter(bool, self.expected.values()))
            self.total_pbar = ui.get_progressbar(
                label="Total", total=total)
            self.total_pbar.start()

    def _update_pbar(self, pbar, new_value):
        """Updates pbar while also updating possibly total pbar"""
        diff = new_value - getattr(pbar, '_old_value', 0)
        setattr(pbar, '_old_value', new_value)
        if self.total_pbar:
            self.total_pbar.update(diff, increment=True)
        pbar.update(new_value)

    def __call__(self, line):
        try:
            j = json.loads(line)
        except:
            # if we fail to parse, just return this precious thing for
            # possibly further processing
            return line

        if 'command' in j and 'key' in j:
            # might be the finish line message
            j_download_id = (j['command'], j['key'])
            pbar = self.pbars.pop(j_download_id, None)
            if j.get('success') in {True, 'true'}:
                self._succeeded += 1
                if pbar:
                    self._update_pbar(pbar, pbar.total)
                elif self.total_pbar:
                    # we didn't have a pbar for this download, so total should
                    # get it all at once
                    try:
                        size_j = self.expected[j['key']]
                    except:
                        size_j = None
                    size = size_j or AnnexRepo.get_size_from_key(j['key'])
                    self.total_pbar.update(size, increment=True)
            else:
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

        def get_size_from_perc_complete(count, perc):
            return int(math.ceil(int(count) / (float(perc) / 100.)))

        # so we have a progress indicator, let's dead with it
        action = j['action']
        download_item = action.get('file') or action.get('key')
        download_id = (action['command'], action['key'])
        if download_id not in self.pbars:
            # New download!
            from datalad.ui import ui
            from datalad.ui import utils as ui_utils
            # TODO: whenever target size gets reported -- used it!
            # http://git-annex.branchable.com/todo/interface_to_the___34__progress__34___of_annex_operations/#comment-6bbc26aae9867603863050ddcb09a9a0
            # for now deduce from key or approx from '%'
            # TODO: unittest etc to check when we have a relaxed
            # URL without any size known in advance
            target_size = \
                AnnexRepo.get_size_from_key(action.get('key')) or \
                get_size_from_perc_complete(
                    j['byte-progress'],
                    j['percent-progress'].rstrip('%')
                )
            w, h = ui_utils.get_terminal_size()
            w = w or 80  # default to 80
            title = str(download_item)
            pbar_right = 50
            title_len = w - pbar_right - 4  # (4 for reserve)
            if len(title) > title_len:
                half = title_len//2 - 2
                title = '%s .. %s' % (title[:half], title[-half:])
            pbar = self.pbars[download_id] = ui.get_progressbar(
                label=title, total=target_size)
            pbar.start()

        self._update_pbar(
            self.pbars[download_id],
            int(j.get('byte-progress'))
        )

    def finish(self):
        if self.total_pbar:
            self.total_pbar.finish()
            self.total_pbar = None
        if self.pbars:
            lgr.warning("Still have %d active progress bars when stopping",
                        len(self.pbars))
        for pbar in self.pbars.values():
            pbar.finish()
        self.pbars = {}
        self._failed = 0
        self._succeeded = 0
