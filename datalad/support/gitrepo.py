# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Internal low-level interface to Git repositories

"""

import logging
import os
import os.path as op
import posixpath
import re
import warnings
from collections import OrderedDict
from collections.abc import Mapping
from functools import wraps
from itertools import chain
from os import linesep
from os.path import (
    commonprefix,
    curdir,
    dirname,
    exists,
    isabs,
)
from os.path import join as opj
from os.path import (
    pardir,
    relpath,
    sep,
)

import datalad.utils as ut
from datalad import ssh_manager
from datalad.cmd import (
    BatchedCommand,
    GitWitlessRunner,
    NoCapture,
    StdOutErrCapture,
    WitlessProtocol,
)
from datalad.config import (
    parse_gitconfig_dump,
    write_config_section,
)
from datalad.consts import (
    ILLEGAL_CHARS_WIN,
    RESERVED_NAMES_WIN,
)
from datalad.core.local.repo import repo_from_path
from datalad.dataset.gitrepo import GitRepo as CoreGitRepo
from datalad.dataset.gitrepo import (
    _get_dot_git,
    path_based_str_repr,
)
from datalad.log import log_progress
from datalad.support.due import (
    Doi,
    due,
)
from datalad.utils import (
    Path,
    PurePosixPath,
    ensure_dir,
    ensure_list,
    ensure_unicode,
    generate_file_chunks,
    getpwd,
    is_interactive,
    on_windows,
    optional_args,
    path_is_subpath,
    posix_relpath,
)

from .exceptions import (
    CapturedException,
    CommandError,
    FileNotInRepositoryError,
    InvalidGitReferenceError,
    InvalidGitRepositoryError,
    NoSuchPathError,
)
# imports from same module:
from .external_versions import external_versions
from .network import (
    RI,
    PathRI,
    is_ssh,
)
from .path import get_parent_paths

# shortcuts
_curdirsep = curdir + sep
_pardirsep = pardir + sep


lgr = logging.getLogger('datalad.gitrepo')


# outside the repo base classes only used in ConfigManager
def to_options(split_single_char_options=True, **kwargs):
    """Transform keyword arguments into a list of cmdline options

    Imported from GitPython.

    Original copyright:
        Copyright (C) 2008, 2009 Michael Trier and contributors
    Original license:
        BSD 3-Clause "New" or "Revised" License

    Parameters
    ----------
    split_single_char_options: bool

    kwargs:

    Returns
    -------
    list
    """
    def dashify(string):
        return string.replace('_', '-')

    def transform_kwarg(name, value, split_single_char_options):
        if len(name) == 1:
            if value is True:
                return ["-%s" % name]
            elif value not in (False, None):
                if split_single_char_options:
                    return ["-%s" % name, "%s" % value]
                else:
                    return ["-%s%s" % (name, value)]
        else:
            if value is True:
                return ["--%s" % dashify(name)]
            elif value is not False and value is not None:
                return ["--%s=%s" % (dashify(name), value)]
        return []

    args = []
    kwargs = OrderedDict(sorted(kwargs.items(), key=lambda x: x[0]))
    for k, v in kwargs.items():
        if isinstance(v, (list, tuple)):
            for value in v:
                args += transform_kwarg(k, value, split_single_char_options)
        else:
            args += transform_kwarg(k, v, split_single_char_options)
    return args


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
    pathobj = Path(path)

    # do absolute() in addition to always get an absolute path
    # even with non-existing base_dirs on windows
    base_dir = str(Path(base_dir).resolve().absolute())  # realpath OK

    # path = normpath(path)
    # Note: disabled normpath, because it may break paths containing symlinks;
    # But we don't want to realpath relative paths, in case cwd isn't the
    # correct base.

    if pathobj.is_absolute():
        # path might already be a symlink pointing to annex etc,
        # so realpath only its directory, to get "inline" with
        # realpath(base_dir) above
        path = str(pathobj.parent.resolve() / pathobj.name)  # realpath OK
    # Executive decision was made to not do this kind of magic!
    #
    # elif commonprefix([realpath(getpwd()), base_dir]) == base_dir:
    #     # If we are inside repository, rebuilt relative paths.
    #     path = opj(realpath(getpwd()), path)
    #
    # BUT with relative curdir/pardir start it would assume relative to curdir
    #
    elif path.startswith(_curdirsep) or path.startswith(_pardirsep):
        path = str(Path(getpwd()).resolve() / pathobj)  # realpath OK
    else:
        # We were called from outside the repo. Therefore relative paths
        # are interpreted as being relative to self.path already.
        return path

    if commonprefix([path, base_dir]) != base_dir:
        raise FileNotInRepositoryError(msg="Path outside repository: %s"
                                           % base_dir, filename=path)

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
    def  _wrap_normalize_path(self, file_, *args, **kwargs):
        file_new = _normalize_path(self.path, file_)
        return func(self, file_new, *args, **kwargs)

    return  _wrap_normalize_path


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
    def  _wrap_normalize_paths(self, files, *args, **kwargs):

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

    return  _wrap_normalize_paths


if "2.24.0" <= external_versions["cmd:git"] < "2.25.0":
    # An unintentional change in Git 2.24.0 led to `ls-files -o` traversing
    # into untracked submodules when multiple pathspecs are given, returning
    # repositories that are deeper than the first level. This helper filters
    # these deeper levels out so that save_() doesn't fail trying to add them.
    #
    # This regression fixed with upstream's 072a231016 (2019-12-10).
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


class GitProgress(WitlessProtocol):
    """Reduced variant of GitPython's RemoteProgress class

    Original copyright:
        Copyright (C) 2008, 2009 Michael Trier and contributors
    Original license:
        BSD 3-Clause "New" or "Revised" License
    """
    # inform super-class to capture stderr
    proc_err = True

    _num_op_codes = 10
    BEGIN, END, COUNTING, COMPRESSING, WRITING, RECEIVING, RESOLVING, FINDING_SOURCES, CHECKING_OUT, ENUMERATING = \
        [1 << x for x in range(_num_op_codes)]
    STAGE_MASK = BEGIN | END
    OP_MASK = ~STAGE_MASK

    DONE_TOKEN = 'done.'
    TOKEN_SEPARATOR = ', '

    _known_ops = {
        COUNTING: ("Counting", "Objects"),
        ENUMERATING: ("Enumerating", "Objects"),
        COMPRESSING: ("Compressing", "Objects"),
        WRITING: ("Writing", "Objects"),
        RECEIVING: ("Receiving", "Objects"),
        RESOLVING: ("Resolving", "Deltas"),
        FINDING_SOURCES: ("Finding", "Sources"),
        CHECKING_OUT: ("Check out", "Things"),
    }

    __slots__ = ('_seen_ops', '_pbars', '_encoding')

    re_op_absolute = re.compile(r"(remote: )?([\w\s]+):\s+()(\d+)()(.*)")
    re_op_relative = re.compile(r"(remote: )?([\w\s]+):\s+(\d+)% \((\d+)/(\d+)\)(.*)")

    def __init__(self, *args):
        super().__init__(*args)
        self._unprocessed = None

    def connection_made(self, transport):
        super().connection_made(transport)
        self._seen_ops = []
        self._pbars = set()

    def process_exited(self):
        # take down any progress bars that were not closed orderly
        for pbar_id in self._pbars:
            log_progress(
                lgr.info,
                pbar_id,
                'Finished',
            )
        super().process_exited()

    def pipe_data_received(self, fd, byts):
        # progress reports only come from stderr
        if fd != 2:
            # let the base class decide what to do with it
            super().pipe_data_received(fd, byts)
            return
        for line in byts.splitlines(keepends=True):
            # put any unprocessed content back in front
            line = self._unprocessed + line if self._unprocessed else line
            self._unprocessed = None
            if not self._parse_progress_line(line):
                # anything that doesn't look like a progress report
                # is retained and returned
                # in case of partial progress lines, this can lead to
                # leakage of progress info into the output, but
                # it is better to enable better (maybe more expensive)
                # subsequent filtering than hiding lines with
                # unknown, potentially important info
                lgr.debug('Non-progress stderr: %s', line)
                if line.endswith((b'\r', b'\n')):
                    # complete non-progress line, pass on
                    super().pipe_data_received(fd, line)
                else:
                    # an incomplete line, maybe the next batch completes
                    # it to become a recognizable progress report
                    self._unprocessed = line

    def _parse_progress_line(self, line):
        """Process a single line

        Parameters
        ----------
        line : bytes

        Returns
        -------
        bool
          Flag whether the line was recognized as a Git progress report.
        """
        # handle
        # Counting objects: 4, done.
        # Compressing objects:  50% (1/2)
        # Compressing objects: 100% (2/2)
        # Compressing objects: 100% (2/2), done.
        line = line.decode(self.encoding) if isinstance(line, bytes) else line
        if line.startswith(('warning:', 'error:', 'fatal:')):
            return False

        # find escape characters and cut them away - regex will not work with
        # them as they are non-ascii. As git might expect a tty, it will send them
        last_valid_index = None
        for i, c in enumerate(reversed(line)):
            if ord(c) < 32:
                # its a slice index
                last_valid_index = -i - 1
            # END character was non-ascii
        # END for each character in line
        if last_valid_index is not None:
            line = line[:last_valid_index]
        # END cut away invalid part
        line = line.rstrip()

        cur_count, max_count = None, None
        match = self.re_op_relative.match(line)
        if match is None:
            match = self.re_op_absolute.match(line)

        if not match:
            return False
        # END could not get match

        op_code = 0
        _remote, op_name, _percent, cur_count, max_count, message = match.groups()

        # get operation id
        if op_name == "Counting objects":
            op_code |= self.COUNTING
        elif op_name == "Compressing objects":
            op_code |= self.COMPRESSING
        elif op_name == "Writing objects":
            op_code |= self.WRITING
        elif op_name == 'Receiving objects':
            op_code |= self.RECEIVING
        elif op_name == 'Resolving deltas':
            op_code |= self.RESOLVING
        elif op_name == 'Finding sources':
            op_code |= self.FINDING_SOURCES
        elif op_name == 'Checking out files':
            op_code |= self.CHECKING_OUT
        elif op_name == 'Enumerating objects':
            op_code |= self.ENUMERATING
        else:
            # Note: On windows it can happen that partial lines are sent
            # Hence we get something like "CompreReceiving objects", which is
            # a blend of "Compressing objects" and "Receiving objects".
            # This can't really be prevented.
            lgr.debug(
                'Output line matched a progress report of an unknown type: %s',
                line)
            # TODO investigate if there is any chance that we might swallow
            # important info -- until them do not flag this line
            # as progress
            return False
        # END handle op code

        pbar_id = 'gitprogress-{}-{}'.format(id(self), op_code)

        op_props = self._known_ops[op_code]

        # figure out stage
        if op_code not in self._seen_ops:
            self._seen_ops.append(op_code)
            op_code |= self.BEGIN
            log_progress(
                lgr.info,
                pbar_id,
                'Start {} {}'.format(
                    op_props[0].lower(),
                    op_props[1].lower(),
                ),
                label=op_props[0],
                unit=' {}'.format(op_props[1]),
                total=float(max_count) if max_count else None,
            )
            self._pbars.add(pbar_id)
        # END begin opcode

        if message is None:
            message = ''
        # END message handling

        done_progress = False
        message = message.strip()
        if message.endswith(self.DONE_TOKEN):
            op_code |= self.END
            message = message[:-len(self.DONE_TOKEN)]
            done_progress = True
        # END end message handling
        message = message.strip(self.TOKEN_SEPARATOR)

        if cur_count and max_count:
            log_progress(
                lgr.info,
                pbar_id,
                line,
                update=float(cur_count),
                noninteractive_level=logging.DEBUG,
            )

        if done_progress:
            log_progress(
                lgr.info,
                pbar_id,
                'Finished {} {}'.format(
                    op_props[0].lower(),
                    op_props[1].lower(),
                ),
                noninteractive_level=logging.DEBUG,
            )
            self._pbars.discard(pbar_id)
        return True


class StdOutCaptureWithGitProgress(GitProgress):
    proc_out = True


class FetchInfo(dict):
    """
    dict that carries results of a fetch operation of a single head

    Reduced variant of GitPython's RemoteProgress class

    Original copyright:
        Copyright (C) 2008, 2009 Michael Trier and contributors
    Original license:
        BSD 3-Clause "New" or "Revised" License
    """

    NEW_TAG, NEW_HEAD, HEAD_UPTODATE, TAG_UPDATE, REJECTED, FORCED_UPDATE, \
        FAST_FORWARD, ERROR = [1 << x for x in range(8)]

    _re_fetch_result = re.compile(r'^\s*(.) (\[?[\w\s\.$@]+\]?)\s+(.+) [-> ]+ ([^\s]+)(    \(.*\)?$)?')

    _flag_map = {
        '!': ERROR,
        '+': FORCED_UPDATE,
        '*': 0,
        '=': HEAD_UPTODATE,
        ' ': FAST_FORWARD,
        '-': TAG_UPDATE,
    }
    _operation_map = {
        NEW_TAG: 'new-tag',
        NEW_HEAD: 'new-branch',
        HEAD_UPTODATE: 'uptodate',
        TAG_UPDATE: 'tag-update',
        REJECTED: 'rejected',
        FORCED_UPDATE: 'forced-update',
        FAST_FORWARD: 'fast-forward',
        ERROR: 'error',
    }

    @classmethod
    def _from_line(cls, line):
        """Parse information from the given line as returned by git-fetch -v
        and return a new FetchInfo object representing this information.
        """
        match = cls._re_fetch_result.match(line)
        if match is None:
            raise ValueError("Failed to parse line: %r" % line)

        # parse lines
        control_character, operation, local_remote_ref, remote_local_ref, note = \
            match.groups()

        # parse flags from control_character
        flags = 0
        try:
            flags |= cls._flag_map[control_character]
        except KeyError:
            raise ValueError(
                "Control character %r unknown as parsed from line %r"
                % (control_character, line))
        # END control char exception handling

        # parse operation string for more info - makes no sense for symbolic refs,
        # but we parse it anyway
        old_commit = None
        if 'rejected' in operation:
            flags |= cls.REJECTED
        if 'new tag' in operation:
            flags |= cls.NEW_TAG
        if 'tag update' in operation:
            flags |= cls.TAG_UPDATE
        if 'new branch' in operation:
            flags |= cls.NEW_HEAD
        if '...' in operation or '..' in operation:
            split_token = '...'
            if control_character == ' ':
                split_token = split_token[:-1]
            old_commit = operation.split(split_token)[0]
        # END handle refspec

        return cls(
            ref=remote_local_ref.strip(),
            local_ref=local_remote_ref.strip(),
            # convert flag int into a list of operation labels
            operations=[
                cls._operation_map[o]
                for o in cls._operation_map.keys()
                if flags & o
            ],
            note=note,
            old_commit=old_commit,
        )


class PushInfo(dict):
    """dict that carries results of a push operation of a single head

    Reduced variant of GitPython's RemoteProgress class

    Original copyright:
        Copyright (C) 2008, 2009 Michael Trier and contributors
    Original license:
        BSD 3-Clause "New" or "Revised" License
    """
    NEW_TAG, NEW_HEAD, NO_MATCH, REJECTED, REMOTE_REJECTED, REMOTE_FAILURE, DELETED, \
        FORCED_UPDATE, FAST_FORWARD, UP_TO_DATE, ERROR = [1 << x for x in range(11)]

    _flag_map = {'X': NO_MATCH,
                 '-': DELETED,
                 '*': 0,
                 '+': FORCED_UPDATE,
                 ' ': FAST_FORWARD,
                 '=': UP_TO_DATE,
                 '!': ERROR}

    _operation_map = {
        NEW_TAG: 'new-tag',
        NEW_HEAD: 'new-branch',
        NO_MATCH: 'no-match',
        REJECTED: 'rejected',
        REMOTE_REJECTED: 'remote-rejected',
        REMOTE_FAILURE: 'remote-failure',
        DELETED: 'deleted',
        FORCED_UPDATE: 'forced-update',
        FAST_FORWARD: 'fast-forward',
        UP_TO_DATE: 'uptodate',
        ERROR: 'error',
    }

    @classmethod
    def _from_line(cls, line):
        """Create a new PushInfo instance as parsed from line which is expected to be like
            refs/heads/master:refs/heads/master 05d2687..1d0568e as bytes"""
        control_character, from_to, summary = line.split('\t', 3)
        flags = 0

        # control character handling
        try:
            flags |= cls._flag_map[control_character]
        except KeyError:
            raise ValueError("Control character %r unknown as parsed from line %r" % (control_character, line))
        # END handle control character

        # from_to handling
        from_ref_string, to_ref_string = from_to.split(':')

        # commit handling, could be message or commit info
        old_commit = None
        if summary.startswith('['):
            if "[rejected]" in summary:
                flags |= cls.REJECTED
            elif "[remote rejected]" in summary:
                flags |= cls.REMOTE_REJECTED
            elif "[remote failure]" in summary:
                flags |= cls.REMOTE_FAILURE
            elif "[no match]" in summary:
                flags |= cls.ERROR
            elif "[new tag]" in summary:
                flags |= cls.NEW_TAG
            elif "[new branch]" in summary:
                flags |= cls.NEW_HEAD
            # up-to-date encoded in control character
        else:
            # fast-forward or forced update - was encoded in control character,
            # but we parse the old and new commit
            split_token = "..."
            if control_character == " ":
                split_token = ".."
            old_sha, _new_sha = summary.split(' ')[0].split(split_token)
            # have to use constructor here as the sha usually is abbreviated
            old_commit = old_sha
        # END message handling

        return cls(
            from_ref=from_ref_string.strip(),
            to_ref=to_ref_string.strip(),
            # convert flag int into a list of operation labels
            operations=[
                cls._operation_map[o]
                for o in cls._operation_map.keys()
                if flags & o
            ],
            note=summary.strip(),
            old_commit=old_commit,
        )


@path_based_str_repr
class GitRepo(CoreGitRepo):
    """Representation of a git repository

    """
    # We must check git config to have name and email set, but
    # should do it once
    _config_checked = False

    GIT_MIN_VERSION = "2.19.1"
    git_version = None

    @classmethod
    def _check_git_version(cls):
        external_versions.check("cmd:git", min_version=cls.GIT_MIN_VERSION)
        cls.git_version = external_versions['cmd:git']

    # This is the least common denominator to claim that a user
    # used DataLad.
    # Citing JOSS publication https://joss.theoj.org/papers/10.21105/joss.03262
    @due.dcite(Doi("10.21105/joss.03262"),
               # override path since there is no need ATM for such details
               path="datalad",
               description="DataLad - Data management and distribution platform")
    def __init__(self, path, runner=None, create=True,
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
        create: bool, optional
          if true, creates a git repository at `path` if there is none. Also
          creates `path`, if it doesn't exist.
          If set to false, an exception is raised in case `path` doesn't exist
          or doesn't contain a git repository.
        repo: git.Repo, optional
          This argument is ignored.
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
        # this will set up .pathobj and .dot_git
        super().__init__(path)

        if self.git_version is None:
            self._check_git_version()

        # BEGIN Repo validity test
        # We want to fail early for tests, that would be performed a lot. In
        # particular this is about GitRepo.is_valid_repo. We would use the
        # latter to decide whether or not to call GitRepo() only for __init__ to
        # then test the same things again. If we fail early we can save the
        # additional test from outer scope.
        self.path = path

        # Note, that the following three path objects are used often and
        # therefore are stored for performance. Path object creation comes with
        # a cost. Most notably, this is used for validity checking of the
        # repository.
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

        # So that we "share" control paths with git/git-annex
        if ssh_manager:
            ssh_manager.ensure_initialized()

        # note: we may also want to distinguish between a path to the worktree
        # and the actual repository

        if git_opts is None:
            git_opts = {}
        if kwargs:
            git_opts.update(kwargs)

        self._cfg = None

        if do_create:  # we figured it out earlier
            from_cmdline = git_opts.pop('_from_cmdline_', [])
            self.init(
                sanity_checks=create_sanity_checks,
                init_options=from_cmdline + to_options(**git_opts),
            )

        # with DryRunProtocol path might still not exist
        if exists(self.path):
            self.inode = os.stat(self.path).st_ino
        else:
            self.inode = None

        if fake_dates:
            self.configure_fake_dates()

    @property
    def bare(self):
        """Returns a bool indicating whether the repository is bare

        Importantly, this is not reporting the configuration value
        of 'core.bare', in order to be usable at a stage where a
        Repo instance is not yet equipped with a ConfigManager.
        Instead, it is testing whether the repository path and its
        "dot_git" are identical. The value of 'core.bare' can be query
        from the ConfigManager in a fully initialized instance.
        """
        return self.pathobj == self.dot_git

    @classmethod
    def clone(cls, url, path, *args, clone_options=None, **kwargs):
        """Clone url into path

        Provides workarounds for known issues (e.g.
        https://github.com/datalad/datalad/issues/785)

        Parameters
        ----------
        url : str
        path : str
        clone_options : dict or list
          Arbitrary options that will be passed on to the underlying call to
          `git-clone`. This may be a list of plain options or key-value pairs
          that will be converted to a list of plain options with `to_options`.
        expect_fail : bool
          Whether expect that command might fail, so error should be logged then
          at DEBUG level instead of ERROR
        kwargs:
          Passed to the Repo class constructor.
        """

        if 'repo' in kwargs:
            raise TypeError("argument 'repo' conflicts with cloning")
            # TODO: what about 'create'?

        expect_fail = kwargs.pop('expect_fail', False)
        # fail early on non-empty target:
        from os import listdir
        if exists(path) and listdir(path):
            raise ValueError(
                "destination path '%s' already exists and is not an "
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
        else:
            if isinstance(url_ri, PathRI):
                # expand user, because execution not going through a shell
                # doesn't work well otherwise
                new_url = os.path.expanduser(url)
                if url != new_url:
                    lgr.info("Expanded source path to %s from %s", new_url, url)
                    url = new_url

        cmd = cls._git_cmd_prefix + ['clone', '--progress']
        if clone_options:
            if isinstance(clone_options, Mapping):
                clone_options = to_options(**clone_options)
            cmd.extend(clone_options)
        cmd.extend([url, path])

        fix_annex = None
        ntries = 5  # 3 is not enough for robust workaround
        for trial in range(ntries):
            try:
                lgr.debug("Git clone from {0} to {1}".format(url, path))

                res = GitWitlessRunner().run(cmd, protocol=GitProgress)
                # fish out non-critical warnings by git-clone
                # (empty repo clone, etc.), all other content is logged
                # by the progress helper to 'debug'
                for errline in res['stderr'].splitlines():
                    if errline.startswith('warning:'):
                        lgr.warning(errline[8:].strip())
                lgr.debug("Git clone completed")
                break
            except CommandError as e:
                # log here but let caller decide what to do
                ce = CapturedException(e)
                str_e = str(e)
                # see https://github.com/datalad/datalad/issues/785
                if re.search("Request for .*aborted.*Unable to find", str_e,
                             re.DOTALL) \
                        and trial < ntries - 1:
                    lgr.info(
                        "Hit a known issue with Git (see GH#785). Trial #%d, "
                        "retrying",
                        trial)
                    continue
                    #(lgr.debug if expect_fail else lgr.error)(e_str)

                if "Clone succeeded, but checkout failed." in str_e:
                    fix_annex = ce
                    break

                raise

        # get ourselves a repository instance
        gr = cls(path, *args, **kwargs)
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
                lgr.warning("Experienced issues while cloning: %s", fix_annex)
        return gr

    # Note: __del__ shouldn't be needed anymore as we switched to
    #       `weakref.finalize`.
    #       https://docs.python.org/3/library/weakref.html#comparing-finalizers-with-del-methods
    #
    #       Keeping both methods and this comment around as a reminder to not
    #       use __del__, if we figure there's a need for cleanup in the future.
    #
    # def __del__(self):
    #     # unbind possibly bound ConfigManager, to prevent all kinds of weird
    #     # stalls etc
    #     self._cfg = None

    def is_valid_git(self):
        """Returns whether the underlying repository appears to be still valid

        Note, that this almost identical to the classmethod is_valid_repo().
        However, if we are testing an existing instance, we can save Path object
        creations. Since this testing is done a lot, this is relevant. Creation
        of the Path objects in is_valid_repo() takes nearly half the time of the
        entire function.

        Also note, that this method is bound to an instance but still
        class-dependent, meaning that a subclass cannot simply overwrite it.
        This is particularly important for the call from within __init__(),
        which in turn is called by the subclasses' __init__. Using an overwrite
        would lead to the wrong thing being called.
        """
        return self.is_valid()

    @classmethod
    def is_valid_repo(cls, path):
        """Returns if a given path points to a git repository"""
        return cls.is_valid(path)

    @staticmethod
    def get_git_dir(repo):
        """figure out a repo's gitdir

        '.git' might be a  directory, a symlink or a file

        Note
        ----
        This method is likely to get deprecated, please use GitRepo.dot_git instead!
        That one's not static, but it's cheaper and you should avoid
        not having an instance of a repo you're working on anyway.
        Note, that the property in opposition to this method returns an absolute path.


        Parameters
        ----------
        repo: path or Repo instance
          currently expected to be the repos base dir

        Returns
        -------
        str
          relative path to the repo's git dir; So, default would be ".git"
        """
        if isinstance(repo, GitRepo):
            return str(repo.dot_git)
        pathobj = Path(repo)
        dot_git = _get_dot_git(pathobj, ok_missing=False)
        try:
            dot_git = dot_git.relative_to(pathobj)
        except ValueError:
            # is not a subpath, return as is
            lgr.debug("Path %r is not subpath of %r", dot_git, pathobj)
        return str(dot_git)

    @property
    def config(self):
        # just proxy the core repo APIs property for backward-compatibility
        return self.cfg

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
            out = GitWitlessRunner(cwd=path).run(
                cmd, protocol=StdOutErrCapture)
            toppath = out['stdout'].rstrip('\n\r')
        except CommandError:
            return None
        except OSError:
            toppath = GitRepo.get_toppath(dirname(path), follow_up=follow_up,
                                          git_options=git_options)

        # normalize the report, because, e.g. on windows it can come out
        # with improper directory separators (C:/Users/datalad)
        toppath = str(Path(toppath))

        if follow_up:
            path_ = path
            path_prev = ""
            while path_ and path_ != path_prev:  # on top /.. = /
                if str(Path(path_).resolve()) == toppath:
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
        files = [_normalize_path(self.path, f) for f in ensure_list(files) if f]

        if not (files or git_options or update):
            # wondering why just a warning? in cmdline this is also not an error
            lgr.warning("add was called with empty file list and no options.")
            return

        try:
            # without --verbose git 2.9.3  add does not return anything
            add_out = self._call_git(
                # Set annex.gitaddtoannex to prevent storing files in
                # annex with a v6+ annex repo.
                ['-c', 'annex.gitaddtoannex=false', 'add'] +
                ensure_list(git_options) +
                to_options(update=update) + ['--verbose'],
                files=files,
                read_only=False,
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
            lgr.error("add: %s", e)
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
                for f in re.findall("'(.*)'[\n$]", ensure_unicode(stdout))]

    @normalize_paths(match_return_type=False)
    def remove(self, files, recursive=False, **kwargs):
        """Remove files.

        Calls git-rm.

        Parameters
        ----------
        files: list of str
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
        if recursive:
            kwargs['r'] = True

        # the name is chosen badly, but the purpose is to make sure that
        # any pending operations actually manifest themselves in the Git repo
        # on disk (in case of an AnnexRepo, it could be pending batch
        # processes that need closing)
        self.precommit()

        # output per removed file is expected to be "rm 'PATH'":
        return [
            line.strip()[4:-1]
            for line in self.call_git_items_(
                ['rm'] + to_options(**kwargs), files=files)
        ]

    def precommit(self):
        """Perform pre-commit maintenance tasks
        """
        # we used to clean up GitPython here
        pass

    @staticmethod
    def _get_prefixed_commit_msg(msg):
        DATALAD_PREFIX = "[DATALAD]"
        return DATALAD_PREFIX if not msg else "%s %s" % (DATALAD_PREFIX, msg)

    def configure_fake_dates(self):
        """Configure repository to use fake dates.
        """
        lgr.debug("Enabling fake dates")
        self.config.set("datalad.fake-dates", "true")

    @property
    def fake_dates_enabled(self):
        """Is the repository configured to use fake dates?
        """
        # this turned into a private property of the CoreGitRepo
        return self._fake_dates_enabled

    def add_fake_dates(self, env):
        # was renamed in CoreGitRepo
        return self.add_fake_dates_to_env(env)

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

        # assemble commandline
        cmd = self._git_cmd_prefix + ['commit']
        options = ensure_list(options)

        if date:
            options += ["--date", date]

        orig_msg = msg
        if not msg:
            if '--amend' in options:
                if '--no-edit' not in options:
                    # don't overwrite old commit message with our default
                    # message by default, but re-use old one. In other words:
                    # Make --no-edit the default:
                    options += ["--no-edit"]
            else:
                msg = 'Recorded changes'
                _datalad_msg = True

        if _datalad_msg:
            msg = self._get_prefixed_commit_msg(msg)

        if msg:
            options += ["-m", msg]
        cmd.extend(options)

        # set up env for commit
        env = self.add_fake_dates(None) \
            if self.fake_dates_enabled else os.environ.copy()
        if index_file:
            env['GIT_INDEX_FILE'] = index_file

        lgr.debug("Committing via direct call of git: %s", cmd)

        file_chunks = generate_file_chunks(files, cmd) if files else [[]]

        # store pre-commit state to be able to check if anything was committed
        prev_sha = self.get_hexsha()

        try:
            for i, chunk in enumerate(file_chunks):
                cur_cmd = cmd.copy()
                # if this is an explicit dry-run, there is no point in
                # amending, because no commit was ever made
                # otherwise, amend the first commit, and prevent
                # leaving multiple commits behind
                if i > 0 and '--dry-run' not in cmd:
                    if '--amend' not in cmd:
                        cur_cmd.append('--amend')
                    if '--no-edit' not in cmd:
                        cur_cmd.append('--no-edit')
                cur_cmd += ['--'] + chunk
                self._git_runner.run(
                    cur_cmd,
                    protocol=StdOutErrCapture,
                    stdin=None,
                    env=env,
                )
        except CommandError as e:
            # real errors first
            if "did not match any file(s) known to git" in e.stderr:
                raise FileNotInRepositoryError(
                    cmd=e.cmd,
                    msg="File(s) unknown to git",
                    code=e.code,
                    filename=linesep.join([
                        l for l in e.stderr.splitlines()
                        if l.startswith("error: pathspec")
                    ])
                )
            # behavior choices now
            elif not careless:
                # not willing to compromise at all
                raise
            elif 'nothing to commit' in e.stdout:
                lgr.debug("nothing to commit in %s. Ignored.", self)
            elif 'no changes added to commit' in e.stdout or \
                    'nothing added to commit' in e.stdout:
                lgr.debug("no changes added to commit in %s. Ignored.", self)
            else:
                raise

        if orig_msg \
                or '--dry-run' in cmd \
                or prev_sha == self.get_hexsha() \
                or ('--amend' in cmd and '--no-edit' in cmd) \
                or (not is_interactive()) \
                or self.config.obtain('datalad.save.no-message') != 'interactive':
            # we had a message given, or nothing was committed, or prev. commit
            # was amended, or we are not connected to a terminal, or no
            # interactive message input is desired:
            # we can go home
            return

        # handle interactive message entry by running another `git-commit`
        self._git_runner.run(
            cmd + ['--amend', '--edit'],
            protocol=NoCapture,
            stdin=None,
            env=env,
        )

    # TODO usage is only in the tests, consider making a test helper and
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
                paths=None, ref=None, untracked='no')
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

    @normalize_paths(match_return_type=False)
    def get_last_commit_hexsha(self, files):
        """Return the hash of the last commit the modified any of the given
        paths"""
        try:
            commit = self.call_git(
                ['rev-list', '-n1', 'HEAD'],
                files=files,
                expect_fail=True,
                read_only=True,
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

        cmd = ["log", "--format={}".format(fmt)]
        cmd.extend((options or []) + revrange + ["--"])
        try:
            stdout = self.call_git(cmd, expect_fail=True, read_only=True)
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
            ["rev-parse", "--verify", commitish + "^{commit}"],
            read_only=True,
        )

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
            base = self.call_git_oneline(['merge-base'] + commitishes,
                                         read_only=True)
        except CommandError as exc:
            if exc.code == 1 and not (exc.stdout or exc.stderr):
                # No merge base was found (unrelated commits).
                return None
            if "fatal: Not a valid object name" in exc.stderr:
                return None
            raise

        return base

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
            ["merge-base", "--is-ancestor", reva, revb],
            read_only=True)

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
                paths=None, ref=branch, untracked='no')
            ]

    def add_remote(self, name, url, options=None):
        """Register remote pointing to a url
        """
        cmd = ['remote', 'add']
        if options:
            cmd += options
        cmd += [name, url]

        # for historical reasons this method returns stdout and
        # stderr, keeping that for now
        result = self._call_git(cmd)
        self.config.reload()
        return result

    def remove_remote(self, name):
        """Remove existing remote
        """

        # TODO: testing and error handling!
        from .exceptions import RemoteNotAvailableError
        try:
            self.call_git(['remote', 'remove', name])
        except CommandError as e:
            if 'No such remote' in e.stderr:
                raise RemoteNotAvailableError(name,
                                              cmd="git remote remove",
                                              msg="No such remote",
                                              stdout=e.stdout,
                                              stderr=e.stderr)
            else:
                raise e

        # config.reload necessary, because the associated remote config
        # will vanish
        self.config.reload()
        return

    def _maybe_open_ssh_connection(self, remote, prefer_push=True):
        """Open connection if `remote` has an SSH URL.

        Doing so enables SSH caching, preventing datalad-sshrun subprocesses
        from opening (and then closing) their own.

        Parameters
        ----------
        remote : str
        prefer_push : bool, optional
            Use `remote.<remote>.pushurl` if there is one, falling back to
            `remote.<remote>.url`.
        """
        if remote:
            url = None
            if prefer_push:
                url = self.get_remote_url(remote, push=True)
            url = url or self.get_remote_url(remote)
            if url and is_ssh(url):
                ssh_manager.get_connection(url).open()

    def update_remote(self, name=None, verbose=False):
        """
        """
        options = ["-v"] if verbose else []
        self._maybe_open_ssh_connection(name)
        name = [name] if name else []
        self.call_git(
            ['remote'] + name + ['update'] + options,
            expect_stderr=True
        )

    def fetch(self, remote=None, refspec=None, all_=False, git_options=None,
              **kwargs):
        """Fetches changes from a remote (or all remotes).

        Parameters
        ----------
        remote : str, optional
          name of the remote to fetch from. If no remote is given and
          `all_` is not set, the tracking branch is fetched.
        refspec : str or list, optional
          refspec(s) to fetch.
        all_ : bool, optional
          fetch all remotes (and all of their branches).
          Fails if `remote` was given.
        git_options : list, optional
          Additional command line options for git-fetch.
        kwargs :
          Deprecated. GitPython-style keyword argument for git-fetch.
          Will be appended to any git_options.
        """
        git_options = ensure_list(git_options)
        if kwargs:
            git_options.extend(to_options(**kwargs))
        return list(
            self.fetch_(
                remote=remote,
                refspec=refspec,
                all_=all_,
                git_options=git_options,
            )
        )

    def fetch_(self, remote=None, refspec=None, all_=False, git_options=None):
        """Like `fetch`, but returns a generator"""
        yield from self._fetch_push_helper(
            base_cmd=self._git_cmd_prefix + ['fetch', '--verbose', '--progress'],
            action='fetch',
            urlvars=('remote.{}.url', 'remote.{}.url'),
            protocol=GitProgress,
            info_cls=FetchInfo,
            info_from='stderr',
            add_remote=False,
            remote=remote,
            refspec=refspec,
            all_=all_,
            git_options=git_options)

    def push(self, remote=None, refspec=None, all_remotes=False,
             all_=False, git_options=None, **kwargs):
        """Push changes to a remote (or all remotes).

        If remote and refspec are specified, and remote has
        `remote.{remote}.datalad-push-default-first` configuration variable
        set (e.g. by `create-sibling-github`), we will first push the first
        refspec separately to possibly ensure that the first refspec is chosen
        by remote as the "default branch".
        See https://github.com/datalad/datalad/issues/4997
        Upon successful push if this variable was set in the local git config,
        we unset it, so subsequent pushes would proceed normally.

        Parameters
        ----------
        remote : str, optional
          name of the remote to push to. If no remote is given and
          `all_` is not set, the tracking branch is pushed.
        refspec : str or list, optional
          refspec(s) to push.
        all_ : bool, optional
          push to all remotes. Fails if `remote` was given.
        git_options : list, optional
          Additional command line options for git-push.
        kwargs :
          Deprecated. GitPython-style keyword argument for git-push.
          Will be appended to any git_options.
        """
        git_options = ensure_list(git_options)
        if kwargs:
            git_options.extend(to_options(**kwargs))
        if all_remotes:
            # be nice to the elderly
            all_ = True

        push_refspecs = [refspec]
        cfg = self.config  # shortcut
        cfg_push_var = "remote.{}.datalad-push-default-first".format(remote)
        if remote and refspec and cfg.obtain(cfg_push_var, default=False, valtype=bool):
            refspec = ensure_list(refspec)
            lgr.debug("As indicated by %s pushing first refspec %s separately first",
                      cfg_push_var, refspec[0])
            push_refspecs = [[refspec[0]], refspec[1:]]

        push_res = []
        for refspecs in push_refspecs:
            push_res.extend(
                self.push_(
                    remote=remote,
                    refspec=refspecs,
                    all_=all_,
                    git_options=git_options,
                )
            )
        # note: above push_ should raise exception if errors out
        if '--dry-run' not in git_options \
            and cfg.get_from_source('local', cfg_push_var) is not None:
            lgr.debug("Removing %s variable from local git config after successful push", cfg_push_var)
            cfg.unset(cfg_push_var, 'local')
        return push_res

    def push_(self, remote=None, refspec=None, all_=False, git_options=None):
        """Like `push`, but returns a generator"""
        yield from self._fetch_push_helper(
            base_cmd=self._git_cmd_prefix + ['push', '--progress', '--porcelain'],
            action='push',
            urlvars=('remote.{}.pushurl', 'remote.{}.url'),
            protocol=StdOutCaptureWithGitProgress,
            info_cls=PushInfo,
            info_from='stdout',
            add_remote=True,
            remote=remote,
            refspec=refspec,
            all_=all_,
            git_options=git_options)

    def _fetch_push_helper(
            self,
            base_cmd,     # arg list
            action,       # label fetch|push
            urlvars,      # variables to query for URLs
            protocol,     # processor for output
            info_cls,     # Push|FetchInfo
            info_from,    # stdout, stderr
            add_remote,   # whether to add a 'remote' field to the info dict
            remote=None, refspec=None, all_=False, git_options=None):

        git_options = ensure_list(git_options)

        cmd = base_cmd + git_options

        if remote is None:
            if refspec:
                # conflicts with using tracking branch or push all remotes
                # For now: Just fail.
                # TODO: May be check whether it fits to tracking branch
                raise ValueError(
                    "refspec specified without a remote. ({})".format(refspec))
            if all_:
                remotes_to_process = self.get_remotes(with_urls_only=True)
            else:
                # No explicit remote to fetch.
                # => get tracking branch:
                tb_remote, refspec = self.get_tracking_branch()
                if tb_remote is not None:
                    remotes_to_process = [tb_remote]
                else:
                    # No remote, no tracking branch
                    # => fail
                    raise ValueError(
                        "Neither a remote is specified to {} "
                        "from nor a tracking branch is set up.".format(action))
        else:
            if all_:
                raise ValueError(
                    "Option 'all_' conflicts with specified remote "
                    "'{}'.".format(remote))
            remotes_to_process = [remote]

        if refspec:
            # prep for appending to cmd
            refspec = ensure_list(refspec)

        # no need for progress report, when there is just one remote
        log_remote_progress = len(remotes_to_process) > 1
        if log_remote_progress:
            pbar_id = '{}remotes-{}'.format(action, id(self))
            log_progress(
                lgr.info,
                pbar_id,
                'Start %sing remotes for %s', action, self,
                total=len(remotes_to_process),
                label=action.capitalize(),
                unit=' Remotes',
            )
        try:
            for remote in remotes_to_process:
                r_cmd = cmd + [remote]
                if refspec:
                    r_cmd += refspec

                if log_remote_progress:
                    log_progress(
                        lgr.info,
                        pbar_id,
                        '{}ing remote %s'.format(action.capitalize()),
                        remote,
                        update=1,
                        increment=True,
                    )
                # best effort to enable SSH connection caching
                url = self.config.get(
                    # make two attempts to get a URL
                    urlvars[0].format(remote),
                    self.config.get(
                        urlvars[1].format(remote),
                        None)
                )
                if url and is_ssh(url):
                    ssh_manager.get_connection(url).open()
                try:
                    out = self._git_runner.run(
                        r_cmd,
                        protocol=protocol,
                    )
                    output = out[info_from] or ''
                except CommandError as e:
                    output = None
                    # intercept some errors that we express as an error report
                    # in the info dicts
                    if re.match(
                            '.*^error: failed to (push|fetch) some refs',
                            e.stderr,
                            re.DOTALL | re.MULTILINE):
                        output = getattr(e, info_from)
                        hints = ' '.join([l[6:] for l in e.stderr.splitlines()
                                          if l.startswith('hint: ')])
                        if output is None:
                            output = ''
                    if not output:
                        raise

                for line in output.splitlines():
                    try:
                        # push info doesn't identify a remote, add it here
                        pi = info_cls._from_line(line)
                        if add_remote:
                            pi['remote'] = remote
                        # There were errors, but Git provided hints
                        if 'error' in pi['operations']:
                            pi['hints'] = hints or None
                        yield pi
                    except Exception:
                        # it is not progress and no push info
                        # don't hide it completely
                        lgr.debug('git-%s reported: %s', action, line)
        finally:
            if log_remote_progress:
                log_progress(
                    lgr.info,
                    pbar_id,
                    'Finished %sing remotes for %s', action, self,
                )

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
        self.config.set(var, url, scope='local', reload=True)

    def get_branch_commits_(self, branch=None, limit=None, stop=None):
        """Return commit hexshas for a branch

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

        Yields
        ------
        str
        """
        cmd = ['rev-list']
        if limit == 'left-only':
            cmd.append('--left-only')
        if not branch:
            branch = self.get_active_branch()
        cmd.append(branch)
        # and trailing -- marker to make sure that Git never confused the branch
        # with a potentially existing directory of the same name
        cmd.append('--')
        for r in self.call_git_items_(cmd):
            if stop and stop == r:
                return
            yield r

    def checkout(self, name, options=None):
        """
        """
        # TODO: May be check for the need of -b options herein?
        cmd = ['checkout']
        if options:
            cmd += options
        cmd += [str(name)]

        self.call_git(cmd, expect_stderr=True)
        # checkout can change committed config, or create branch config
        self.config.reload()

    # TODO: Before implementing annex merge, find usages and check for a needed
    # change to call super().merge
    def merge(self, name, options=None, msg=None, allow_unrelated=False, **kwargs):
        if options is None:
            options = []
        if msg:
            options = options + ["-m", msg]
        options += ['--allow-unrelated-histories']
        self.call_git(
            ['merge'] + options + [name],
            **kwargs
        )

    def remove_branch(self, branch):
        self.call_git(['branch', '-D', branch])

    def cherry_pick(self, commit):
        """Cherry pick `commit` to the current branch.

        Parameters
        ----------
        commit : str
            A single commit.
        """
        self.call_git(["cherry-pick", commit])

    @property
    def dirty(self):
        """Is the repository dirty?

        Note: This provides a quick answer when you simply want to know if
        there are any untracked changes or modifications in this repository or
        its submodules. For finer-grained control and more detailed reporting,
        use status() instead.
        """
        stdout = self.call_git(
            ["status", "--porcelain",
             # Ensure the result isn't influenced by status.showUntrackedFiles.
             "--untracked-files=normal",
             # Ensure the result isn't influenced by diff.ignoreSubmodules.
             "--ignore-submodules=none"])
        if bool(stdout.strip()):
            # The quick `git status`-based check can give a different answer
            # than `datalad status` for submodules on an adjusted branch.
            st = self.diffstatus(fr="HEAD" if self.get_hexsha() else None,
                                 to=None, untracked="normal")
            return any(r.get("state") != "clean" for r in st.values())
        return False

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
        cmd_options = []
        if not allow_background:
            cmd_options += ['-c', 'gc.autodetach=0']
        cmd_options += ['gc', '--aggressive']
        if auto:
            cmd_options += ['--auto']
        self.call_git(cmd_options)

    def _parse_gitmodules(self):
        # TODO read .gitconfig from Git blob?
        gitmodules = self.pathobj / '.gitmodules'
        if not gitmodules.exists():
            return {}
        # pull out file content
        out = self.call_git(
            ['config', '-z', '-l', '--file', '.gitmodules'],
            read_only=True)
        # abuse our config parser
        # disable multi-value report, because we could not deal with them
        # anyways, and they should not appear in a normal .gitmodules file
        # but could easily appear when duplicates are included. In this case,
        # we better not crash
        db, _ = parse_gitconfig_dump(out, cwd=self.path, multi_value=False)
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
                untracked='no').items():
            if props.get('type', None) != 'dataset':
                # make sure this method never talks about non-dataset
                # content
                continue
            props["path"] = path
            props.update(modinfo.get(path, {}))
            yield props

    def get_submodules(self, sorted_=True, paths=None):
        """Return list of submodules.

        Parameters
        ----------
        sorted_ : bool, optional
            Sort submodules by path name.
        paths : list(pathlib.PurePath), optional
            Restrict submodules to those under `paths`.

        Returns
        -------
        List of submodule namedtuples if `compat` is true or otherwise a list
        of dictionaries as returned by `get_submodules_`.
        """
        xs = self.get_submodules_(paths=paths)

        if sorted_:
            xs = sorted(xs, key=lambda x: x["path"])
        return list(xs)

    def update_ref(self, ref, value, oldvalue=None, symbolic=False):
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
        oldvalue: str
          Value to update from. Safeguard to be verified by git. This is only
          valid if `symbolic` is not True.
        symbolic : None
          To instruct if ref is symbolic, e.g. should be used in case of
          ref=HEAD
        """
        if symbolic:
            if oldvalue:
                raise ValueError("oldvalue and symbolic must not be given both")
            cmd = ['symbolic-ref', ref, value]
        else:
            cmd = ['update-ref', ref, value] + ([oldvalue] if oldvalue else [])
        self.call_git(cmd)

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
        cmd = ['describe'] + to_options(**kwargs)
        if commitish is not None:
            cmd.append(commitish)
        try:
            describe = self.call_git(cmd, expect_fail=True)
            return describe.strip()
        # TODO: WTF "catch everything"?
        except:
            return None

    def get_tracking_branch(self, branch=None, remote_only=False):
        """Get the tracking branch for `branch` if there is any.

        Parameters
        ----------
        branch: str
            local branch to look up. If none is given, active branch is used.
        remote_only : bool
            Don't return a value if the upstream remote is set to "." (meaning
            this repository).

        Returns
        -------
        tuple
            (remote or None, refspec or None) of the tracking branch
        """
        if branch is None:
            branch = self.get_corresponding_branch() or self.get_active_branch()
            if branch is None:
                return None, None

        track_remote = self.config.get('branch.{0}.remote'.format(branch), None)
        if remote_only and track_remote == ".":
            return None, None
        track_branch = self.config.get('branch.{0}.merge'.format(branch), None)
        return track_remote, track_branch

    @property
    def count_objects(self):
        """return dictionary with count, size(in KiB) information of git objects
        """

        count_cmd = ['count-objects', '-v']
        count_str = self.call_git(count_cmd)
        count = {key: int(value)
                 for key, value in [item.split(': ')
                                    for item in count_str.split('\n')
                                    if len(item.split(': ')) == 2]}
        return count

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
          Each key is a queried path (always relative to the repository root),
          each value is a dictionary with attribute
          name and value items. Attribute values are either True or False,
          for set and unset attributes, or are the literal attribute value.
        """
        path = ensure_list(path)
        cmd = ["check-attr", "-z", "--all"]
        if index_only:
            cmd.append('--cached')
        # make sure we have one entry for each query path to
        # simplify work with the result
        attributes = {p: {} for p in path}
        attr = []
        for item in self.call_git_items_(cmd, files=path, sep='\0',
                                         read_only=True):
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
        return {relpath(k, self.path) if isabs(k) else k: v
                for k, v in attributes.items()}

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

        with open(git_attributes_file, mode + '+') as f:
            # for append, fix existing files that do not end with \n
            if mode == 'a' and f.tell():
                f.seek(max(0, f.tell() - len(os.linesep)))
                if not f.read().endswith('\n'):
                    f.write('\n')

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
                f.write('{}\n'.format(attrline))

    def get_content_info(self, paths=None, ref=None, untracked='all'):
        """Get identifier and type information from repository content.

        This is simplified front-end for `git ls-files/tree`.

        Both commands differ in their behavior when queried about subdataset
        paths. ls-files will not report anything, ls-tree will report on the
        subdataset record. This function uniformly follows the behavior of
        ls-tree (report on the respective subdataset mount).

        Parameters
        ----------
        paths : list(pathlib.PurePath) or None
          Specific paths, relative to the resolved repository root, to query
          info for. Paths must be normed to match the reporting done by Git,
          i.e. no parent dir components (ala "some/../this").
          If `None`, info is reported for all content.
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

        Returns
        -------
        dict
          Each content item has an entry under a pathlib `Path` object instance
          pointing to its absolute path inside the repository (this path is
          guaranteed to be underneath `Repo.path`).
          Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'

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

        if paths:  # is not None separate after
            # path matching will happen against what Git reports
            # and Git always reports POSIX paths
            # any incoming path has to be relative already, so we can simply
            # convert unconditionally
            # note: will be list-ified below
            posix_paths = [ut.PurePath(p).as_posix() for p in paths]
        elif paths is not None:
            return info
        else:
            posix_paths = None

        if posix_paths and (not ref or external_versions["cmd:git"] >= "2.29.0"):
            # If a path points within a submodule, we need to map it to the
            # containing submodule before feeding it to ls-files or ls-tree.
            #
            # Before Git 2.29.0, ls-tree and ls-files differed in how they
            # reported paths within submodules: ls-files provided no output,
            # and ls-tree listed the submodule. Now they both return no output.
            submodules = [s["path"].relative_to(self.pathobj).as_posix()
                          for s in self.get_submodules_()]
            # `paths` get normalized into PurePosixPath above, submodules are POSIX as well
            posix_paths = get_parent_paths(posix_paths, submodules)

        # this will not work in direct mode, but everything else should be
        # just fine
        if not ref:
            # make sure no operations are pending before we figure things
            # out in the worktree
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
                files=posix_paths,
                expect_fail=True,
                read_only=True)
        except CommandError as exc:
            if "fatal: Not a valid object name" in exc.stderr:
                raise InvalidGitReferenceError(ref)
            raise
        lgr.debug('Done query repo: %s', cmd)

        self._get_content_info_line_helper(
            ref,
            info,
            stdout.split('\0'),
            props_re)

        lgr.debug('Done %s.get_content_info(...)', self)
        return info

    def _get_content_info_line_helper(self, ref, info, lines, props_re):
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
                # Kludge: Filter out paths starting with .git/ to work around
                # an `ls-files -o` bug that was fixed in Git 2.25.
                #
                # TODO: Drop this condition when GIT_MIN_VERSION is at least
                # 2.25.
                if line.startswith(".git/"):
                    lgr.debug("Filtering out .git/ file: %s", line)
                    continue
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
                  self, len(paths) if paths is not None else 'all')
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
                   eval_submodule_state='full', _cache=None):
        """Like diff(), but reports the status of 'clean' content too.

        It supports an additional submodule evaluation state 'global'.
        If given, it will return a single 'modified'
        (vs. 'clean') state label for the entire repository, as soon as
        it can.
        """
        def _get_cache_key(label, paths, ref, untracked=None):
            return self.path, label, tuple(paths) if paths else None, \
                ref, untracked

        if _cache is None:
            _cache = {}

        if paths is not None:
            # at this point we must normalize paths to the form that
            # Git would report them, to easy matching later on
            paths = map(ut.Path, paths)
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
                    paths=paths, ref=None, untracked=untracked)
                _cache[key] = to_state
            # we want Git to tell us what it considers modified and avoid
            # reimplementing logic ourselves
            key = _get_cache_key('mod', paths, None)
            if key in _cache:
                modified = _cache[key]
            else:
                # from Git 2.31.0 onwards ls-files has --deduplicate
                # by for backward compatibility keep doing deduplication here
                modified = set(
                    self.pathobj.joinpath(ut.PurePosixPath(p))
                    for p in self.call_git_items_(
                        # we must also look for deleted files, for the logic
                        # below to work. Only from Git 2.31.0 would they be
                        # included with `-m` alone
                        ['ls-files', '-z', '-m', '-d'],
                        # low-level code cannot handle pathobjs
                        files=[str(p) for p in paths] if paths is not None else None,
                        sep='\0',
                        read_only=True)
                    if p)
                _cache[key] = modified
        else:
            key = _get_cache_key('ci', paths, to)
            if key in _cache:
                to_state = _cache[key]
            else:
                to_state = self.get_content_info(paths=paths, ref=to)
                _cache[key] = to_state
            # we do not need worktree modification detection in this case
            modified = None
        # origin state
        key = _get_cache_key('ci', paths, fr)
        if key in _cache:
            from_state = _cache[key]
        else:
            if fr:
                from_state = self.get_content_info(paths=paths, ref=fr)
            else:
                # no ref means from nothing
                from_state = {}
            _cache[key] = from_state

        status = OrderedDict()
        for f, to_state_r in to_state.items():
            props = self._diffstatus_get_state_props(
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
            if not GitRepo.is_valid_repo(f):
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
            st['state'] = subrepo.diffstatus(
                # we can use 'HEAD' because we know that the commit
                # did not change. using 'HEAD' will facilitate
                # caching the result
                fr='HEAD',
                to=None,
                paths=None,
                untracked=untracked,
                eval_submodule_state='global',
                _cache=_cache) if st['state'] == 'clean' else 'modified'
            if eval_submodule_state == 'global' and st['state'] == 'modified':
                return 'modified'

        if eval_submodule_state == 'global':
            return 'clean'
        else:
            return status

    def _diffstatus_get_state_props(self, f, from_state, to_state,
                                    against_commit,
                                    modified_in_worktree,
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
        return status

    def get_staged_paths(self):
        """Returns a list of any stage repository path(s)

        This is a rather fast call, as it will not depend on what is going on
        in the worktree.
        """
        try:
            return list(self.call_git_items_(
                ['diff', '--name-only', '--staged'],
                expect_stderr=True))
        except CommandError as e:
            lgr.debug(CapturedException(e))
            return []

    def _save_post(self, message, files, partial_commit, amend=False,
                   allow_empty=False):
        # helper to commit changes reported in status

        # TODO remove pathobj stringification when commit() can
        # handle it
        to_commit = [str(f.relative_to(self.pathobj))
                     for f in files] \
                    if partial_commit else None
        if not partial_commit or to_commit or allow_empty or \
                (amend and message):
            # we directly call GitRepo.commit() to avoid a whole slew
            # if direct-mode safeguards and workarounds in the AnnexRepo
            # implementation (which also run an additional dry-run commit
            GitRepo.commit(
                self,
                files=to_commit,
                msg=message,
                options=to_options(amend=amend, allow_empty=allow_empty),
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
          - untracked : {'no', 'normal', 'all'} - passed to Repo.status()
          - amend : bool (passed to GitRepo.commit)
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

        status = self._save_pre(paths, _status, **kwargs) or {}
        amend = kwargs.get('amend', False)

        # Sort status into status by state with explicit list of states
        # (excluding clean we do not care about) we expect to be present
        # and which we know of (unless None), and modified_or_untracked hybrid
        # since it is used below
        status_state = {
            k: {}
            for k in (None,  # not cared of explicitly here
                      'added',  # not cared of explicitly here
                      # 'clean'  # not even wanted since nothing to do about those
                      'deleted',
                      'modified',
                      'untracked',
                      'modified_or_untracked',  # hybrid group created here
                      )}
        for f, props in status.items():
            state = props.get('state', None)
            if state == 'clean':
                # we don't care about clean
                continue
            if state == 'modified' and props.get('gitshasum') \
                    and props.get('gitshasum') == props.get('prev_gitshasum'):
                # reported as modified, but with identical shasums -> typechange
                # a subdataset maybe? do increasingly expensive tests for
                # speed reasons
                if props.get('type') != 'dataset' and f.is_dir() \
                        and GitRepo.is_valid_repo(f):
                    # it was not a dataset, but now there is one.
                    # we declare it untracked to engage the discovery tooling.
                    state = 'untracked'
                    props = dict(type='dataset', state='untracked')
            status_state[state][f] = props
            # The hybrid one to retain the same order as in original status
            if state in ('modified', 'untracked'):
                status_state['modified_or_untracked'][f] = props
        del status  # to ensure it is no longer used

        # TODO: check on those None's -- may be those are also "nothing to worry about"
        # and we could just return?
        if not any(status_state.values()) and not (message and amend):
            # all clean, nothing todo
            lgr.debug('Nothing to save in %r, exiting early', self)
            return

        # three things are to be done:
        # - remove (deleted if not already staged)
        # - add (modified/untracked)
        # - commit (with all paths that have been touched, to bypass
        #   potential pre-staged bits)

        staged_paths = self.get_staged_paths()
        need_partial_commit = bool(staged_paths)
        if need_partial_commit and hasattr(self, "call_annex"):
            # so we have some staged content. let's check which ones
            # are symlinks -- those could be annex key links that
            # are broken after a `git-mv` operation
            # https://github.com/datalad/datalad/issues/4967
            # call `git-annex pre-commit` on them to rectify this before
            # saving the wrong symlinks
            added = status_state['added']
            tofix = [
                sp for sp in staged_paths
                if added.get(self.pathobj / sp, {}).get("type") == "symlink"
            ]
            if tofix:
                self.call_annex(['pre-commit'], files=tofix)

        # remove first, because removal of a subds would cause a
        # modification of .gitmodules to be added to the todo list
        to_remove = [
            # TODO remove pathobj stringification when delete() can
            # handle it
            str(f.relative_to(self.pathobj))
            for f, props in status_state['deleted'].items()
            # staged deletions have a gitshasum reported for them
            # those should not be processed as git rm will error
            # due to them being properly gone already
            if not props.get('gitshasum', None)]
        vanished_subds = any(
            props.get('type', None) == 'dataset'
            for props in status_state['deleted'].values())
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

        # TODO this additional query should not be, based on status as given
        # if anyhow possible, however, when paths are given, status may
        # not contain all required information. In case of path=None AND
        # _status=None, we should be able to avoid this, because
        # status should have the full info already
        # looks for contained repositories
        submodule_change = False
        untracked_dirs = [
            f.relative_to(self.pathobj)
            for f, props in status_state['untracked'].items()
            if props.get('type', None) == 'directory']
        to_add_submodules = []
        if untracked_dirs:
            to_add_submodules = [
                sm for sm, sm_props in
                self.get_content_info(
                    untracked_dirs,
                    ref=None,
                    # request exhaustive list, so that everything that is
                    # still reported as a directory must be its own repository
                    untracked='all').items()
                if sm_props.get('type', None) == 'directory']
            to_add_submodules = _prune_deeper_repos(to_add_submodules)
            if to_add_submodules:
                for r in self._save_add_submodules(to_add_submodules):
                    if r.get('status', None) == 'ok':
                        submodule_change = True
                    yield r
        to_stage_submodules = {
            f: props
            for f, props in status_state['modified_or_untracked'].items()
            if props.get('type', None) == 'dataset'}
        if to_stage_submodules:
            lgr.debug(
                '%i submodule path(s) to stage in %r %s',
                len(to_stage_submodules), self,
                to_stage_submodules
                if len(to_stage_submodules) < 10 else '')
            for r in self._save_add_submodules(to_stage_submodules):
                if r.get('status', None) == 'ok':
                    submodule_change = True
                yield r

        if submodule_change or vanished_subds:
            # the config has changed too
            self.config.reload()
            # need to include .gitmodules in what needs saving
            f = self.pathobj.joinpath('.gitmodules')
            status_state['modified_or_untracked'][f] = \
                status_state['modified'][f] = \
                dict(type='file', state='modified')
            if hasattr(self, 'uuid') and not kwargs.get('git', False):
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
            for f, props in status_state['modified_or_untracked'].items()
            if not (f in to_add_submodules or f in to_stage_submodules)}
        if to_add:
            compat_config = \
                self.config.obtain("datalad.save.windows-compat-warning")
            to_add, problems = self._check_for_win_compat(to_add, compat_config)
            lgr.debug(
                '%i path(s) to add to %s %s',
                len(to_add), self, to_add if len(to_add) < 10 else '')

            if to_add:
                yield from self._save_add(
                        to_add,
                        git_opts=None,
                        **{k: kwargs[k] for k in kwargs
                           if k in (('git',) if hasattr(self, 'uuid')
                                    else tuple())})
            if problems:
                from datalad.interface.results import get_status_dict
                msg = \
                    'Incompatible name for Windows systems; disable with ' \
                    'datalad.save.windows-compat-warning.',
                for path in problems:
                    yield get_status_dict(
                        action='save',
                        refds=self.pathobj,
                        type='file',
                        path=(self.pathobj / ut.PurePosixPath(path)),
                        status='impossible',
                        message=msg,
                        logger=lgr)


        # https://github.com/datalad/datalad/issues/6558
        # file could have become a directory. Unfortunately git
        # would then mistakenly refuse to commit if that old path is also
        # given to commit, so we better filter it out
        if status_state['deleted'] and status_state['added']:
            # check if any "deleted" is a directory now. Then for those
            # there should be some other path under that directory in 'added'
            for f in [_ for _ in status_state['deleted'] if _.is_dir()]:
                # this could potentially be expensive if lots of files become
                # directories, but it is unlikely to happen often
                # Note: PurePath.is_relative_to was added in 3.9 and seems slowish
                # path_is_subpath faster, also if comparing to "in f.parents"
                f_str = str(f)
                if any(path_is_subpath(str(f2), f_str) for f2 in status_state['added']):
                    status_state['deleted'].pop(f)  # do not bother giving it to commit below in _save_post

        # Note, that allow_empty is always ok when we amend. Required when we
        # amend an empty commit while the amendment is empty, too (though
        # possibly different message). If an empty commit was okay before, it's
        # okay now.
        status_state.pop('modified_or_untracked')  # pop the hybrid state
        self._save_post(message, chain(*status_state.values()), need_partial_commit, amend=amend,
                        allow_empty=amend)
        # TODO yield result for commit, prev helper checked hexsha pre
        # and post...

    def _check_for_win_compat(self, files, config):
        """Check file names for illegal characters or reserved names on Windows

        In the case that a non-Windows-compatible file is detected, warn users
        about potential interoperability issues.

        Parameters
        ----------
        files
          list of files to add
        config
          value of self.config.obtain("datalad.save.windows-compat-warning"),
          used to choose appropriate behavior. "none" performs no check,
          "warning" warns in case of incompatibilities, and "error" results in
          an error result in case of incompatibilities
        """
        # don't perform any check when the configuration is set to 'none'
        if config == 'none':
            return files, None

        from collections import defaultdict
        problems = defaultdict(list)
        for file in files:
            for part in Path(file).parts:
                # check every component of the path for incompatibilities
                if Path(part).stem.upper() in RESERVED_NAMES_WIN:
                    problems['Elements using a reserved filename:'].append(part)
                    problems['paths'].append(file)
                if re.search(ILLEGAL_CHARS_WIN, part):
                    problems['Elements with illegal characters:'].append(part)
                    problems['paths'].append(file)
                if part.endswith('.'):
                    problems['Elements ending with a dot:'].append(part)
                    problems['paths'].append(file)
                if part.endswith(' '):
                    problems['Elements ending with a space:'].append(part)
                    problems['paths'].append(file)
        if not problems:
            return files, None
        msg = \
            "Some elements of your dataset are not compatible with " \
            "Windows systems. Disable this check by changing " \
            "datalad.save.windows-compat-warning or consider renaming " \
            "the following elements: "
        for k, v in problems.items():
            # use the key as an explanation, and report filenames only once
            msg += f"\n{k} {[*{*v}]}" if k != 'paths' else ''
        if config == 'warning':
            lgr.warning(msg)
            return files, None

        elif config == 'error':
            # take the problematic files out of to_add
            for path in [*{*problems['paths']}]:
                files.pop(path)
            return files, [*{*problems['paths']}]

    def _save_add(self, files, git_opts=None):
        """Simple helper to add files in save()"""
        from datalad.interface.results import get_status_dict
        try:
            # without --verbose git 2.9.3  add does not return anything
            add_out = self._call_git(
                # Set annex.largefiles to prevent storing files in
                # annex with a v6+ annex repo.
                ['-c', 'annex.largefiles=nothing', 'add'] +
                ensure_list(git_opts) + ['--verbose'],
                files=list(files.keys()),
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
            lgr.error("add: %s", e)
            raise

    def _save_add_submodules(self, paths):
        """Add new submodules, or updates records of existing ones

        This method does not use `git submodule add`, but aims to be more
        efficient by limiting the scope to mere in-place registration of
        multiple already present repositories.

        Parameters
        ----------
        paths : list(Path)

        Yields
        ------
        dict
          Result records
        """
        from datalad.interface.results import get_status_dict

        # first gather info from all datasets in read-only fashion, and then
        # update index, .gitmodules and .git/config at once
        info = []
        for path in paths:
            rpath = str(path.relative_to(self.pathobj).as_posix())
            subm = repo_from_path(path)
            # if there is a corresponding branch, we want to record it's state.
            # we rely on the corresponding branch being synced already.
            # `save` should do that each time it runs.
            subm_commit = subm.get_hexsha(subm.get_corresponding_branch())
            if not subm_commit:
                yield get_status_dict(
                    action='add_submodule',
                    ds=self,
                    path=path,
                    status='error',
                    message=('cannot add subdataset %s with no commits', subm),
                    logger=lgr)
                continue
            # make an attempt to configure a submodule source URL based on the
            # discovered remote configuration
            remote, branch = subm.get_tracking_branch()
            url = subm.get_remote_url(remote) if remote else None
            if url is None:
                url = './{}'.format(rpath)
            subm_id = subm.config.get('datalad.dataset.id', None)
            info.append(
                dict(
                     # if we have additional information on this path, pass it on.
                     # if not, treat it as an untracked directory
                     paths[path] if isinstance(paths, dict)
                     else dict(type='directory', state='untracked'),
                     path=path, rpath=rpath, commit=subm_commit, id=subm_id,
                     url=url))

        # bypass any convenience or safe-manipulator for speed reasons
        # use case: saving many new subdatasets in a single run
        with (self.pathobj / '.gitmodules').open('a') as gmf, \
             (self.pathobj / '.git' / 'config').open('a') as gcf:
            for i in info:
                # we update the subproject commit unconditionally
                self.call_git([
                    'update-index', '--add', '--replace', '--cacheinfo', '160000',
                    i['commit'], i['rpath']
                ])
                # only write the .gitmodules/.config changes when this is not yet
                # a subdataset
                # TODO: we could update the URL, and branch info at this point,
                # even for previously registered subdatasets
                if i['type'] != 'dataset' or (
                        i['type'] == 'dataset' and i['state'] == 'untracked'):
                    gmprops = dict(path=i['rpath'], url=i['url'])
                    if i['id']:
                        gmprops['datalad-id'] = i['id']
                    write_config_section(
                        gmf, 'submodule', i['rpath'], gmprops)
                    write_config_section(
                        gcf, 'submodule', i['rpath'], dict(active='true', url=i['url']))

                # This mirrors the result structure yielded for
                # to_stage_submodules below.
                yield get_status_dict(
                    action='add',
                    refds=self.pathobj,
                    # should become type='dataset'
                    # https://github.com/datalad/datalad/pull/4793#discussion_r464515331
                    type='file',
                    key=None,
                    path=i['path'],
                    status='ok',
                    logger=lgr)


# used in in the get command and GitRepo.add_submodule(), the
# latter is not used outside the tests
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
    repo.config.unset('core.worktree', scope='local')
    # what we have here is some kind of reference, remove and
    # replace by the target
    os.remove(subds_dotgit)
    # make absolute
    src_dotgit = str(repo.dot_git)
    # move .git
    from os import (
        listdir,
        rename,
        rmdir,
    )
    ensure_dir(subds_dotgit)
    for dot_git_entry in listdir(src_dotgit):
        rename(opj(src_dotgit, dot_git_entry),
               opj(subds_dotgit, dot_git_entry))
    assert not listdir(src_dotgit)
    rmdir(src_dotgit)


# try retro-fitting GitRepo with deprecated functionality
# must be done last in this file
try:
    from datalad_deprecated.gitrepo import DeprecatedGitRepoMethods
    for symbol in dir(DeprecatedGitRepoMethods):
        if symbol.startswith('__'):
            # ignore Python internals
            continue
        if hasattr(GitRepo, symbol):
            lgr.debug(
                'Not retro-fitted GitRepo with deprecated %s, '
                'name-space conflict', symbol)
            # do not override existing symbols
            continue
        # assign deprecated symbol to GitRepo
        setattr(GitRepo, symbol, getattr(DeprecatedGitRepoMethods, symbol))
        lgr.debug('Retro-fitted GitRepo with deprecated %s', symbol)
except ImportError as e:
    ce = CapturedException(e)
    lgr.debug(
        'Not retro-fitting GitRepo with deprecated symbols, '
        'datalad-deprecated package not found')
