# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from __future__ import annotations

import builtins
import collections
import gc
import glob
import gzip
import inspect
import logging
import os
import os.path as op
import platform
import posixpath
import re
import shutil
import stat
import string
import sys
import tempfile
import threading
import time
import warnings
from collections.abc import (
    Callable,
    Iterable,
    Iterator,
    Sequence,
)
from contextlib import contextmanager
from copy import copy as shallow_copy
from functools import (
    lru_cache,
    wraps,
)
from itertools import tee
# this import is required because other modules import opj from here.
from os.path import (
    abspath,
    basename,
    commonprefix,
    curdir,
    dirname,
    exists,
    expanduser,
    expandvars,
    isabs,
    isdir,
    islink,
)
from os.path import join as opj
from os.path import (
    lexists,
    normpath,
    pardir,
    relpath,
    sep,
    split,
    splitdrive,
)
from pathlib import (
    Path,
    PurePath,
    PurePosixPath,
)
from shlex import quote as shlex_quote
from shlex import split as shlex_split
from tempfile import NamedTemporaryFile
from time import sleep
from types import (
    ModuleType,
    TracebackType,
)
from typing import (
    IO,
    Any,
    Dict,
    List,
    NamedTuple,
    Optional,
    TextIO,
    Tuple,
    TypeVar,
    Union,
    cast,
    overload,
)

# from datalad.dochelpers import get_docstring_split
from datalad.consts import TIMESTAMP_FMT
from datalad.support.exceptions import CapturedException
from datalad.typing import (
    K,
    Literal,
    P,
    T,
    V,
)

# handle this dance once, and import pathlib from here
# in all other places

lgr = logging.getLogger("datalad.utils")

lgr.log(5, "Importing datalad.utils")
#
# Some useful variables
#
platform_system = platform.system().lower()
on_windows = platform_system == 'windows'
on_osx = platform_system == 'darwin'
on_linux = platform_system == 'linux'

# COPY_BUFSIZE sort of belongs into datalad.consts, but that would lead to
# circular import due to `on_windows`
try:
    from shutil import COPY_BUFSIZE  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    # too old
    from datalad.utils import on_windows

    # from PY3.10
    COPY_BUFSIZE = 1024 * 1024 if on_windows else 64 * 1024


# Takes ~200msec, so should not be called at import time
@lru_cache()  # output should not change through life time of datalad process
def get_linux_distribution() -> tuple[str, str, str]:
    """Compatibility wrapper for {platform,distro}.linux_distribution().
    """
    if hasattr(platform, "linux_distribution"):
        # Use deprecated (but faster) method if it's available.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            result = platform.linux_distribution()
    else:
        import distro  # We require this for Python 3.8 and above.
        return (
            distro.id(),
            distro.version(),
            distro.codename(),
        )
    return result


# Those weren't used for any critical decision making, thus we just set them to None
# Use get_linux_distribution() directly where needed
linux_distribution_name = linux_distribution_release = None

# Maximal length of cmdline string
# Query the system and use hardcoded "knowledge" if None
# probably   getconf ARG_MAX   might not be available
# The last one would be the most conservative/Windows
CMD_MAX_ARG_HARDCODED = 2097152 if on_linux else 262144 if on_osx else 32767
try:
    CMD_MAX_ARG = os.sysconf('SC_ARG_MAX')
    assert CMD_MAX_ARG > 0
    if CMD_MAX_ARG > CMD_MAX_ARG_HARDCODED * 1e6:
        # workaround for some kind of a bug which comes up with python 3.4
        # see https://github.com/datalad/datalad/issues/3150
        # or on older CentOS with conda and python as new as 3.9
        # see https://github.com/datalad/datalad/issues/5943
        # TODO: let Yarik know that the world is a paradise now whenever 1e6
        # is not large enough
        CMD_MAX_ARG = min(CMD_MAX_ARG, CMD_MAX_ARG_HARDCODED)
except Exception as exc:
    # ATM (20181005) SC_ARG_MAX available only on POSIX systems
    # so exception would be thrown e.g. on Windows, or
    # somehow during Debian build for nd14.04 it is coming up with -1:
    # https://github.com/datalad/datalad/issues/3015
    CMD_MAX_ARG = CMD_MAX_ARG_HARDCODED
    lgr.debug(
        "Failed to query or got useless SC_ARG_MAX sysconf, "
        "will use hardcoded value: %s", exc)
# Even with all careful computations we do, due to necessity to account for
# environment and what not, we still could not figure out "exact" way to
# estimate it, but it was shown that 300k safety margin on linux was sufficient.
# https://github.com/datalad/datalad/pull/2977#issuecomment-436264710
# 300k is ~15%, so to be safe, and for paranoid us we will just use up to 50%
# of the length for "safety margin".  We might probably still blow due to
# env vars, unicode, etc...  so any hard limit imho is not a proper solution
CMD_MAX_ARG = int(0.5 * CMD_MAX_ARG)
lgr.debug(
    "Maximal length of cmdline string (adjusted for safety margin): %d",
    CMD_MAX_ARG)

#
# Little helpers
#

# `getargspec` has been deprecated in Python 3.
class ArgSpecFake(NamedTuple):
    args: list[str]
    varargs: Optional[str]
    keywords: Optional[str]
    defaults: Optional[tuple[Any, ...]]


# adding cache here somehow does break it -- even 'datalad wtf' does not run
# @lru_cache()  # signatures stay the same, why to "redo"? brings it into ns from mks
def getargspec(func: Callable[..., Any], *, include_kwonlyargs: bool=False) -> ArgSpecFake:
    """Compat shim for getargspec deprecated in python 3.

    The main difference from inspect.getargspec (and inspect.getfullargspec
    for that matter) is that by using inspect.signature we are providing
    correct args/defaults for functools.wraps'ed functions.

    `include_kwonlyargs` option was added to centralize getting all args,
    even the ones which are kwonly (follow the ``*,``).

    For internal use and not advised for use in 3rd party code.
    Please use inspect.signature directly.
    """
    # We use signature, and not getfullargspec, because only signature properly
    # "passes" args from a functools.wraps decorated function.
    # Note: getfullargspec works Ok on wrapt-decorated functions
    f_sign = inspect.signature(func)
    # Loop through parameters and compose argspec
    args: list[str] = []
    varargs: Optional[str] = None
    keywords: Optional[str] = None
    defaults: dict[str, Any] = {}
    # Collect all kwonlyargs into a dedicated dict - name: default
    kwonlyargs: dict[str, Any] = {}
    P = inspect.Parameter

    for p_name, p in f_sign.parameters.items():
        if p.kind in (P.POSITIONAL_ONLY, P.POSITIONAL_OR_KEYWORD):
            assert not kwonlyargs  # yoh: must not come after kwonlyarg
            args.append(p_name)
            if p.default is not P.empty:
                defaults[p_name] = p.default
        elif p.kind == P.VAR_POSITIONAL:
            varargs = p_name
        elif p.kind == P.VAR_KEYWORD:
            keywords = p_name
        elif p.kind == P.KEYWORD_ONLY:
            assert p.default is not P.empty
            kwonlyargs[p_name] = p.default

    if kwonlyargs:
        if not include_kwonlyargs:
            raise ValueError(
                'Function has keyword-only parameters or annotations, either use '
                'inspect.signature() API which can support them, or provide include_kwonlyargs=True '
                'to this function'
            )
        else:
            args.extend(list(kwonlyargs))
            defaults.update(kwonlyargs)

    # harmonize defaults to how original getargspec returned them -- just a tuple
    d_defaults = None if not defaults else tuple(defaults.values())
    return ArgSpecFake(args, varargs, keywords, d_defaults)


# Definitions to be (re)used in the next function
_SIG_P = inspect.Parameter
_SIG_KIND_SELECTORS: dict[str, set[int]] = {
    'pos_only': {_SIG_P.POSITIONAL_ONLY,},
    'pos_any': {_SIG_P.POSITIONAL_ONLY, _SIG_P.POSITIONAL_OR_KEYWORD},
    'kw_any': {_SIG_P.POSITIONAL_OR_KEYWORD, _SIG_P.KEYWORD_ONLY},
    'kw_only': {_SIG_P.KEYWORD_ONLY,},
}
_SIG_KIND_SELECTORS['any'] = set().union(*_SIG_KIND_SELECTORS.values())


@lru_cache()  # signatures stay the same, why to "redo"? brings it into ns from mks
def get_sig_param_names(f: Callable[..., Any], kinds: tuple[str, ...]) -> tuple[list[str], ...]:
    """A helper to selectively return parameters from inspect.signature.

    inspect.signature is the ultimate way for introspecting callables.  But
    its interface is not so convenient for a quick selection of parameters
    (AKA arguments) of desired type or combinations of such.  This helper
    should make it easier to retrieve desired collections of parameters.

    Since often it is desired to get information about multiple specific types
    of parameters, `kinds` is a list, so in a single invocation of `signature`
    and looping through the results we can obtain all information.

    Parameters
    ----------
    f: callable
    kinds: tuple with values from {'pos_any', 'pos_only', 'kw_any', 'kw_only', 'any'}
      Is a list of what kinds of args to return in result (tuple). Each element
      should be one of: 'any_pos' - positional or keyword which could be used
      positionally. 'kw_only' - keyword only (cannot be used positionally) arguments,
      'any_kw` - any keyword (could be a positional which could be used as a keyword),
      `any` -- any type from the above.

    Returns
    -------
    tuple:
      Each element is a list of parameters (names only) of that "kind".
    """
    selectors: list[set[int]] = []
    for kind in kinds:
        if kind not in _SIG_KIND_SELECTORS:
            raise ValueError(f"Unknown 'kind' {kind}. Known are: {', '.join(_SIG_KIND_SELECTORS)}")
        selectors.append(_SIG_KIND_SELECTORS[kind])

    out: list[list[str]] = [[] for _ in kinds]
    for p_name, p in inspect.signature(f).parameters.items():
        for i, selector in enumerate(selectors):
            if p.kind in selector:
                out[i].append(p_name)

    return tuple(out)


def any_re_search(regexes: str | list[str], value: str) -> bool:
    """Return if any of regexes (list or str) searches successfully for value"""
    for regex in ensure_tuple_or_list(regexes):
        if re.search(regex, value):
            return True
    return False


def not_supported_on_windows(msg: Optional[str]=None) -> None:
    """A little helper to be invoked to consistently fail whenever functionality is
    not supported (yet) on Windows
    """
    if on_windows:
        raise NotImplementedError("This functionality is not yet implemented for Windows OS"
                                  + (": %s" % msg if msg else ""))


def get_home_envvars(new_home: str | Path) -> dict[str, str]:
    """Return dict with env variables to be adjusted for a new HOME

    Only variables found in current os.environ are adjusted.

    Parameters
    ----------
    new_home: str or Path
      New home path, in native to OS "schema"
    """
    new_home = str(new_home)
    out = {'HOME': new_home}
    if on_windows:
        # requires special handling, since it has a number of relevant variables
        # and also Python changed its behavior and started to respect USERPROFILE only
        # since python 3.8: https://bugs.python.org/issue36264
        out['USERPROFILE'] = new_home
        out['HOMEDRIVE'], out['HOMEPATH'] = splitdrive(new_home)

    return {v: val for v, val in out.items() if v in os.environ}


def _is_stream_tty(stream: Optional[IO]) -> bool:
    try:
        # TODO: check on windows if hasattr check would work correctly and
        # add value:
        return stream is not None and stream.isatty()
    except ValueError as exc:
        # Who knows why it is a ValueError, but let's try to be specific
        # If there is a problem with I/O - non-interactive, otherwise reraise
        if "I/O" in str(exc):
            return False
        raise


def is_interactive() -> bool:
    """Return True if all in/outs are open and tty.

    Note that in a somewhat abnormal case where e.g. stdin is explicitly
    closed, and any operation on it would raise a
    `ValueError("I/O operation on closed file")` exception, this function
    would just return False, since the session cannot be used interactively.
    """
    return all(_is_stream_tty(s) for s in (sys.stdin, sys.stdout, sys.stderr))


def get_ipython_shell() -> Optional[Any]:
    """Detect if running within IPython and returns its `ip` (shell) object

    Returns None if not under ipython (no `get_ipython` function)
    """
    try:
        return get_ipython()  # type: ignore[name-defined]
    except NameError:
        return None


def md5sum(filename: str | Path) -> str:
    """Compute an MD5 sum for the given file
    """
    from datalad.support.digests import Digester
    return Digester(digests=['md5'])(filename)['md5']


_encoded_dirsep = r'\\'  if on_windows else r'/'
_VCS_REGEX = r'%s\.(?:git|gitattributes|svn|bzr|hg)(?:%s|$)' % (
    _encoded_dirsep, _encoded_dirsep)
_DATALAD_REGEX = r'%s\.(?:datalad)(?:%s|$)' % (
    _encoded_dirsep, _encoded_dirsep)


def find_files(regex: str, topdir: str | Path = curdir, exclude: Optional[str]=None, exclude_vcs: bool =True, exclude_datalad: bool =False, dirs: bool =False) -> Iterator[str]:
    """Generator to find files matching regex

    Parameters
    ----------
    regex: string
    exclude: string, optional
      Matches to exclude
    exclude_vcs:
      If True, excludes commonly known VCS subdirectories.  If string, used
      as regex to exclude those files (regex: `%r`)
    exclude_datalad:
      If True, excludes files known to be datalad meta-data files (e.g. under
      .datalad/ subdirectory) (regex: `%r`)
    topdir: string, optional
      Directory where to search
    dirs: bool, optional
      Whether to match directories as well as files
    """
    for dirpath, dirnames, filenames in os.walk(topdir):
        names = (dirnames + filenames) if dirs else filenames
        # TODO: might want to uniformize on windows to use '/'
        paths = (op.join(dirpath, name) for name in names)
        for path in filter(re.compile(regex).search, paths):
            path = path.rstrip(sep)
            if exclude and re.search(exclude, path):
                continue
            if exclude_vcs and re.search(_VCS_REGEX, path):
                continue
            if exclude_datalad and re.search(_DATALAD_REGEX, path):
                continue
            yield path
find_files.__doc__ %= (_VCS_REGEX, _DATALAD_REGEX)  # type: ignore[operator]


def expandpath(path: str | Path, force_absolute: bool =True) -> str:
    """Expand all variables and user handles in a path.

    By default return an absolute path
    """
    path = expandvars(expanduser(path))
    if force_absolute:
        path = abspath(path)
    return path


def posix_relpath(path: str | Path, start: Optional[str | Path]=None) -> str:
    """Behave like os.path.relpath, but always return POSIX paths...

    on any platform."""
    # join POSIX style
    return posixpath.join(
        # split and relpath native style
        # python2.7 ntpath implementation of relpath cannot handle start=None
        *split(
            relpath(path, start=start if start is not None else '')))


def is_explicit_path(path: str | Path) -> bool:
    """Return whether a path explicitly points to a location

    Any absolute path, or relative path starting with either '../' or
    './' is assumed to indicate a location on the filesystem. Any other
    path format is not considered explicit."""
    path = expandpath(path, force_absolute=False)
    return isabs(path) \
        or path.startswith(os.curdir + os.sep) \
        or path.startswith(os.pardir + os.sep)


def rotree(path: str | Path, ro: bool =True, chmod_files: bool =True) -> None:
    """To make tree read-only or writable

    Parameters
    ----------
    path : string
      Path to the tree/directory to chmod
    ro : bool, optional
      Whether to make it R/O (default) or RW
    chmod_files : bool, optional
      Whether to operate also on files (not just directories)
    """
    if ro:
        chmod = lambda f: os.chmod(f, os.stat(f).st_mode & ~stat.S_IWRITE)
    else:
        chmod = lambda f: os.chmod(f, os.stat(f).st_mode | stat.S_IWRITE | stat.S_IREAD)

    for root, dirs, files in os.walk(path, followlinks=False):
        if chmod_files:
            for f in files:
                fullf = op.join(root, f)
                # might be the "broken" symlink which would fail to stat etc
                if exists(fullf):
                    chmod(fullf)
        chmod(root)


def rmtree(path: str | Path, chmod_files: bool | Literal["auto"] ='auto', children_only: bool =False, *args: Any, **kwargs: Any) -> None:
    """To remove git-annex .git it is needed to make all files and directories writable again first

    Parameters
    ----------
    path: Path or str
       Path to remove
    chmod_files : string or bool, optional
       Whether to make files writable also before removal.  Usually it is just
       a matter of directories to have write permissions.
       If 'auto' it would chmod files on windows by default
    children_only : bool, optional
       If set, all files and subdirectories would be removed while the path
       itself (must be a directory) would be preserved
    `*args` :
    `**kwargs` :
       Passed into shutil.rmtree call
    """
    # Give W permissions back only to directories, no need to bother with files
    if chmod_files == 'auto':
        chmod_files = on_windows
    # TODO:  yoh thinks that if we could quickly check our Flyweight for
    #        repos if any of them is under the path, and could call .precommit
    #        on those to possibly stop batched processes etc, we did not have
    #        to do it on case by case
    # Check for open files
    assert_no_open_files(path)

    # TODO the whole thing should be reimplemented with pathlib, but for now
    # at least accept Path
    path = str(path)

    if children_only:
        if not isdir(path):
            raise ValueError("Can remove children only of directories")
        for p in os.listdir(path):
            rmtree(op.join(path, p))
        return
    if not (islink(path) or not isdir(path)):
        rotree(path, ro=False, chmod_files=chmod_files)
        if on_windows:
            # shutil fails to remove paths that exceed 260 characters on Windows machines
            # that did not enable long path support. A workaround to remove long paths
            # anyway is to prepend \\?\ to the path.
            # https://docs.microsoft.com/en-us/windows/win32/fileio/naming-a-file?redirectedfrom=MSDN#win32-file-namespaces
            path = r'\\?\ '.strip() + path
        _rmtree(path, *args, **kwargs)
    else:
        # just remove the symlink
        unlink(path)


def rmdir(path: str | Path, *args: Any, **kwargs: Any) -> None:
    """os.rmdir with our optional checking for open files"""
    assert_no_open_files(path)
    os.rmdir(path)


def get_open_files(path: str | Path, log_open: int = False) -> dict[str, Any]:
    """Get open files under a path

    Note: This function is very slow on Windows.

    Parameters
    ----------
    path : str
      File or directory to check for open files under
    log_open : bool or int
      If set - logger level to use

    Returns
    -------
    dict
      path : pid

    """
    # Original idea: https://stackoverflow.com/a/11115521/1265472
    import psutil
    files = {}
    # since the ones returned by psutil would not be aware of symlinks in the
    # path we should also get realpath for path
    # do absolute() in addition to always get an absolute path
    # even with non-existing paths on windows
    path = str(Path(path).resolve().absolute())
    for proc in psutil.process_iter():
        try:
            open_paths = [p.path for p in proc.open_files()] + [proc.cwd()]
            for p in open_paths:
                # note: could be done more efficiently so we do not
                # renormalize path over and over again etc
                if path_startswith(p, path):
                    files[p] = proc
        # Catch a race condition where a process ends
        # before we can examine its files
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            pass

    if files and log_open:
        lgr.log(log_open, "Open files under %s: %s", path, files)
    return files


_assert_no_open_files_cfg = os.environ.get('DATALAD_ASSERT_NO_OPEN_FILES')
if _assert_no_open_files_cfg:
    def assert_no_open_files(path: str | Path) -> None:
        files = get_open_files(path, log_open=40)
        if _assert_no_open_files_cfg == 'assert':
            assert not files, "Got following files still open: %s" % ','.join(files)
        elif files:
            if _assert_no_open_files_cfg == 'pdb':
                import pdb
                pdb.set_trace()
            elif _assert_no_open_files_cfg == 'epdb':
                import epdb  # type: ignore[import]
                epdb.serve()
            pass
        # otherwise we would just issue that error message in the log
else:
    def assert_no_open_files(path: str | Path) -> None:
        pass


def rmtemp(f: str | Path, *args: Any, **kwargs: Any) -> None:
    """Wrapper to centralize removing of temp files so we could keep them around

    It will not remove the temporary file/directory if DATALAD_TESTS_TEMP_KEEP
    environment variable is defined
    """
    if not os.environ.get('DATALAD_TESTS_TEMP_KEEP'):
        if not os.path.lexists(f):
            lgr.debug("Path %s does not exist, so can't be removed", f)
            return
        lgr.log(5, "Removing temp file: %s", f)
        # Can also be a directory
        if isdir(f):
            rmtree(f, *args, **kwargs)
        else:
            unlink(f)
    else:
        lgr.info("Keeping temp file: %s", f)


@overload
def file_basename(name: str | Path, return_ext: Literal[True]) -> tuple[str, str]:
    ...

@overload
def file_basename(name: str | Path, return_ext: Literal[False] = False) -> str:
    ...

def file_basename(name: str | Path, return_ext: bool =False) -> str | tuple[str, str]:
    """
    Strips up to 2 extensions of length up to 4 characters and starting with alpha
    not a digit, so we could get rid of .tar.gz etc
    """
    bname = basename(name)
    fbname = re.sub(r'(\.[a-zA-Z_]\S{1,4}){0,2}$', '', bname)
    if return_ext:
        return fbname, bname[len(fbname) + 1:]
    else:
        return fbname


# unused in -core
def escape_filename(filename: str) -> str:
    """Surround filename in "" and escape " in the filename
    """
    filename = filename.replace('"', r'\"').replace('`', r'\`')
    filename = '"%s"' % filename
    return filename


# unused in -core
def encode_filename(filename: str | bytes) -> bytes:
    """Encode unicode filename
    """
    if isinstance(filename, str):
        return filename.encode(sys.getfilesystemencoding())
    else:
        return filename


# unused in -core
def decode_input(s: str | bytes) -> str:
    """Given input string/bytes, decode according to stdin codepage (or UTF-8)
    if not defined

    If fails -- issue warning and decode allowing for errors
    being replaced
    """
    if isinstance(s, str):
        return s
    else:
        encoding = sys.stdin.encoding or 'UTF-8'
        try:
            return s.decode(encoding)
        except UnicodeDecodeError as exc:
            lgr.warning(
                "Failed to decode input string using %s encoding. "
                "Decoding allowing for errors", encoding)
            return s.decode(encoding, errors='replace')


# unused in -core
if on_windows:
    def lmtime(filepath: str | Path, mtime: int | float) -> None:
        """Set mtime for files.  On Windows a merely adapter to os.utime
        """
        os.utime(filepath, (time.time(), mtime))
else:
    def lmtime(filepath: str | Path, mtime: int | float) -> None:
        """Set mtime for files, while not de-referencing symlinks.

        To overcome absence of os.lutime

        Works only on linux and OSX ATM
        """
        from .cmd import WitlessRunner

        # convert mtime to format touch understands [[CC]YY]MMDDhhmm[.SS]
        smtime = time.strftime("%Y%m%d%H%M.%S", time.localtime(mtime))
        lgr.log(3, "Setting mtime for %s to %s == %s", filepath, mtime, smtime)
        WitlessRunner().run(['touch', '-h', '-t', '%s' % smtime, str(filepath)])
        filepath = Path(filepath)
        rfilepath = filepath.resolve()
        if filepath.is_symlink() and rfilepath.exists():
            # trust no one - adjust also of the target file
            # since it seemed like downloading under OSX (was it using curl?)
            # didn't bother with timestamps
            lgr.log(3, "File is a symlink to %s Setting mtime for it to %s",
                    rfilepath, mtime)
            os.utime(str(rfilepath), (time.time(), mtime))
        # doesn't work on OSX
        # Runner().run(['touch', '-h', '-d', '@%s' % mtime, filepath])


# See <https://github.com/python/typing/discussions/1366> for a request for a
# better way to annotate this function.
def ensure_tuple_or_list(obj: Any) -> list | tuple:
    """Given an object, wrap into a tuple if not list or tuple
    """
    if isinstance(obj, (list, tuple)):
        return tuple(obj)
    return (obj,)


ListOrSet = TypeVar("ListOrSet", list, set)


# TODO: Improve annotation:
def ensure_iter(s: Any, cls: type[ListOrSet], copy: bool=False, iterate: bool=True) -> ListOrSet:
    """Given not a list, would place it into a list. If None - empty list is returned

    Parameters
    ----------
    s: list or anything
    cls: class
      Which iterable class to ensure
    copy: bool, optional
      If correct iterable is passed, it would generate its shallow copy
    iterate: bool, optional
      If it is not a list, but something iterable (but not a str)
      iterate over it.
    """

    if isinstance(s, cls):
        return s if not copy else shallow_copy(s)
    elif isinstance(s, str):
        return cls((s,))
    elif iterate and hasattr(s, '__iter__'):
        return cls(s)
    elif s is None:
        return cls()
    else:
        return cls((s,))


# TODO: Improve annotation:
def ensure_list(s: Any, copy: bool=False, iterate: bool=True) -> list:
    """Given not a list, would place it into a list. If None - empty list is returned

    Parameters
    ----------
    s: list or anything
    copy: bool, optional
      If list is passed, it would generate a shallow copy of the list
    iterate: bool, optional
      If it is not a list, but something iterable (but not a str)
      iterate over it.
    """
    return ensure_iter(s, list, copy=copy, iterate=iterate)


# TODO: Improve annotation:
def ensure_result_list(r: Any) -> list:
    """Return a list of result records

    Largely same as ensure_list, but special casing a single dict being passed
    in, which a plain `ensure_list` would iterate over. Hence, this deals with
    the three ways datalad commands return results:
    - single dict
    - list of dicts
    - generator

    Used for result assertion helpers.
    """
    return [r] if isinstance(r, dict) else ensure_list(r)

@overload
def ensure_list_from_str(s: str, sep: str='\n') -> Optional[list[str]]:
    ...

@overload
def ensure_list_from_str(s: list[T], sep: str='\n') -> Optional[list[T]]:
    ...

def ensure_list_from_str(s: str | list[T], sep: str='\n') -> Optional[list[str]] | Optional[list[T]]:
    """Given a multiline string convert it to a list of return None if empty

    Parameters
    ----------
    s: str or list
    """

    if not s:
        return None

    if isinstance(s, list):
        return s
    return s.split(sep)

@overload
def ensure_dict_from_str(s: str, sep: str = '\n') -> Optional[dict[str, str]]:
    ...

@overload
def ensure_dict_from_str(s: dict[K, V], sep: str = '\n') -> Optional[dict[K, V]]:
    ...

def ensure_dict_from_str(s: str | dict[K, V], sep: str = '\n') -> Optional[dict[str, str]] | Optional[dict[K, V]]:
    """Given a multiline string with key=value items convert it to a dictionary

    Parameters
    ----------
    s: str or dict

    Returns None if input s is empty
    """

    if not s:
        return None

    if isinstance(s, dict):
        return s

    out: dict[str, str] = {}
    values = ensure_list_from_str(s, sep=sep)
    assert values is not None
    for value_str in values:
        if '=' not in value_str:
            raise ValueError("{} is not in key=value format".format(repr(value_str)))
        k, v = value_str.split('=', 1)
        if k in out:
            err = "key {} was already defined in {}, but new value {} was provided".format(k, out, v)
            raise ValueError(err)
        out[k] = v
    return out


def ensure_bytes(s: str | bytes, encoding: str='utf-8') -> bytes:
    """Convert/encode unicode string to bytes.

    If `s` isn't a string, return it as is.

    Parameters
    ----------
    encoding: str, optional
      Encoding to use.  "utf-8" is the default
    """
    if not isinstance(s, str):
        return s
    return s.encode(encoding)


def ensure_unicode(s: str | bytes, encoding: Optional[str]=None, confidence: Optional[float]=None) -> str:
    """Convert/decode bytestring to unicode.

    If `s` isn't a bytestring, return it as is.

    Parameters
    ----------
    encoding: str, optional
      Encoding to use.  If None, "utf-8" is tried, and then if not a valid
      UTF-8, encoding will be guessed
    confidence: float, optional
      A value between 0 and 1, so if guessing of encoding is of lower than
      specified confidence, ValueError is raised
    """
    if not isinstance(s, bytes):
        return s
    if encoding is None:
        # Figure out encoding, defaulting to 'utf-8' which is our common
        # target in contemporary digital society
        try:
            return s.decode('utf-8')
        except UnicodeDecodeError as exc:
            lgr.debug("Failed to decode a string as utf-8: %s",
                      CapturedException(exc))
        # And now we could try to guess
        from chardet import detect
        enc = detect(s)
        denc = enc.get('encoding', None)
        if denc:
            denc_confidence = enc.get('confidence', 0)
            if confidence is not None and  denc_confidence < confidence:
                raise ValueError(
                    "Failed to auto-detect encoding with high enough "
                    "confidence. Highest confidence was %s for %s"
                    % (denc_confidence, denc)
                )
            lgr.log(5, "Auto-detected encoding to be %s", denc)
            return s.decode(denc)
        else:
            raise ValueError(
                "Could not decode value as utf-8, or to guess its encoding: %s"
                % repr(s)
            )
    else:
        return s.decode(encoding)


def ensure_bool(s: Any) -> bool:
    """Convert value into boolean following convention for strings

    to recognize on,True,yes as True, off,False,no as False
    """
    if isinstance(s, str):
        if s.isdigit():
            return bool(int(s))
        sl = s.lower()
        if sl in {'y', 'yes', 'true', 'on'}:
            return True
        elif sl in {'n', 'no', 'false', 'off'}:
            return False
        else:
            raise ValueError("Do not know how to treat %r as a boolean" % s)
    return bool(s)


def unique(seq: Sequence[T], key: Optional[Callable[[T], Any]]=None, reverse: bool=False) -> list[T]:
    """Given a sequence return a list only with unique elements while maintaining order

    This is the fastest solution.  See
    https://www.peterbe.com/plog/uniqifiers-benchmark
    and
    http://stackoverflow.com/a/480227/1265472
    for more information.
    Enhancement -- added ability to compare for uniqueness using a key function

    Parameters
    ----------
    seq:
      Sequence to analyze
    key: callable, optional
      Function to call on each element so we could decide not on a full
      element, but on its member etc
    reverse: bool, optional
      If True, uniqueness checked in the reverse order, so that the later ones
      will take the order
    """
    seen: set[T] = set()
    seen_add = seen.add

    if reverse:
        def trans(x: Sequence[T]) -> Iterable[T]:
            return reversed(x)
    else:
        def trans(x: Sequence[T]) -> Iterable[T]:
            return x

    if key is None:
        out = [x for x in trans(seq) if not (x in seen or seen_add(x))]
    else:
        # OPT: could be optimized, since key is called twice, but for our cases
        # should be just as fine
        out = [x for x in trans(seq) if not (key(x) in seen or seen_add(key(x)))]

    return out[::-1] if reverse else out


# TODO: Annotate (would be made easier if the return value was always a dict
# instead of doing `v.__class__(...)`)
def map_items(func, v):
    """A helper to apply `func` to all elements (keys and values) within dict

    No type checking of values passed to func is done, so `func`
    should be resilient to values which it should not handle

    Initial usecase - apply_recursive(url_fragment, ensure_unicode)
    """
    # map all elements within item
    return v.__class__(
        item.__class__(map(func, item))
        for item in v.items()
    )


def partition(items: Iterable[T], predicate: Callable[[T], Any]=bool) -> tuple[Iterator[T], Iterator[T]]:
    """Partition `items` by `predicate`.

    Parameters
    ----------
    items : iterable
    predicate : callable
        A function that will be mapped over each element in `items`. The
        elements will partitioned based on whether the return value is false or
        true.

    Returns
    -------
    A tuple with two generators, the first for 'false' items and the second for
    'true' ones.

    Notes
    -----
    Taken from Peter Otten's snippet posted at
    https://nedbatchelder.com/blog/201306/filter_a_list_into_two_parts.html
    """
    a, b = tee((predicate(item), item) for item in items)
    return ((item for pred, item in a if not pred),
            (item for pred, item in b if pred))


def generate_chunks(container: list[T], size: int) -> Iterator[list[T]]:
    """Given a container, generate chunks from it with size up to `size`
    """
    # There could be a "smarter" solution but I think this would suffice
    assert size > 0,  "Size should be non-0 positive"
    while container:
        yield container[:size]
        container = container[size:]


def generate_file_chunks(files: list[str], cmd: str | list[str] | None = None) -> Iterator[list[str]]:
    """Given a list of files, generate chunks of them to avoid exceeding cmdline length

    Parameters
    ----------
    files: list of str
    cmd: str or list of str, optional
      Command to account for as well
    """
    files = ensure_list(files)
    cmd = ensure_list(cmd)

    maxl = max(map(len, files)) if files else 0
    chunk_size = max(
        1,  # should at least be 1. If blows then - not our fault
        (CMD_MAX_ARG
         - sum((len(x) + 3) for x in cmd)
         - 4  # for '--' below
         ) // (maxl + 3)  # +3 for possible quotes and a space
    )
    # TODO: additional treatment for "too many arguments"? although
    # as https://github.com/datalad/datalad/issues/1883#issuecomment
    # -436272758
    # shows there seems to be no hardcoded limit on # of arguments,
    # but may be we decide to go for smth like follow to be on safe side
    # chunk_size = min(10240 - len(cmd), chunk_size)
    file_chunks = generate_chunks(files, chunk_size)
    return file_chunks


#
# Generators helpers
#

def saved_generator(gen: Iterable[T]) -> tuple[Iterator[T], Iterator[T]]:
    """Given a generator returns two generators, where 2nd one just replays

    So the first one would be going through the generated items and 2nd one
    would be yielding saved items
    """
    saved = []

    def gen1() -> Iterator[T]:
        for x in gen:  # iterating over original generator
            saved.append(x)
            yield x

    def gen2() -> Iterator[T]:
        for x in saved:  # yielding saved entries
            yield x

    return gen1(), gen2()


#
# Decorators
#

# Originally better_wraps was created to provide `wrapt`-based, instead of
# `functools.wraps` implementation to preserve the correct signature of the
# decorated function. By using inspect.signature in our getargspec, which
# works fine on `functools.wraps`ed functions, we mediated this necessity.
better_wraps = wraps


# TODO: Annotate:
# Borrowed from pandas
# Copyright: 2011-2014, Lambda Foundry, Inc. and PyData Development Team
# License: BSD-3
def optional_args(decorator):
    """allows a decorator to take optional positional and keyword arguments.
        Assumes that taking a single, callable, positional argument means that
        it is decorating a function, i.e. something like this::

            @my_decorator
            def function(): pass

        Calls decorator with decorator(f, `*args`, `**kwargs`)"""

    @better_wraps(decorator)
    def wrapper(*args, **kwargs):
        def dec(f):
            return decorator(f, *args, **kwargs)

        is_decorating = not kwargs and len(args) == 1 and isinstance(args[0], Callable)
        if is_decorating:
            f = args[0]
            args = []
            return dec(f)
        else:
            return dec

    return wrapper


# TODO: just provide decorators for tempfile.mk* functions. This is ugly!
def get_tempfile_kwargs(tkwargs: Optional[dict[str, Any]]=None, prefix: str="", wrapped: Optional[Callable]=None) -> dict[str, Any]:
    """Updates kwargs to be passed to tempfile. calls depending on env vars
    """
    if tkwargs is None:
        tkwargs_ = {}
    else:
        # operate on a copy of tkwargs to avoid any side-effects
        tkwargs_ = tkwargs.copy()

    # TODO: don't remember why I had this one originally
    # if len(targs)<2 and \
    if 'prefix' not in tkwargs_:
        tkwargs_['prefix'] = '_'.join(
            ['datalad_temp'] +
            ([prefix] if prefix else []) +
            ([''] if (on_windows or not wrapped) else [wrapped.__name__]))

    directory = os.environ.get('TMPDIR')
    if directory and 'dir' not in tkwargs_:
        tkwargs_['dir'] = directory

    return tkwargs_


def line_profile(func: Callable[P, T]) -> Callable[P, T]:
    """Q&D helper to line profile the function and spit out stats
    """
    import line_profiler  # type: ignore[import]
    prof = line_profiler.LineProfiler()

    @wraps(func)
    def  _wrap_line_profile(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            pfunc = prof(func)
            return pfunc(*args, **kwargs)
        finally:
            prof.print_stats()
    return  _wrap_line_profile


# unused in -core
@optional_args
def collect_method_callstats(func: Callable[P, T]) -> Callable[P, T]:
    """Figure out methods which call the method repeatedly on the same instance

    Use case(s):
      - .repo is expensive since does all kinds of checks.
      - .config is expensive transitively since it calls .repo each time

    TODO:
      - fancy one could look through the stack for the same id(self) to see if
        that location is already in memo.  That would hint to the cases where object
        is not passed into underlying functions, causing them to redo the same work
        over and over again
      - ATM might flood with all "1 lines" calls which are not that informative.
        The underlying possibly suboptimal use might be coming from their callers.
        It might or not relate to the previous TODO
    """
    import traceback
    from collections import defaultdict
    from time import time
    memo: defaultdict[tuple[int, str], defaultdict[int, int]] = defaultdict(lambda: defaultdict(int))  # it will be a dict of lineno: count
    # gross timing
    times = []
    toppath = dirname(__file__) + sep

    @wraps(func)
    def _wrap_collect_method_callstats(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            self = args[0]
            stack = traceback.extract_stack()
            caller = stack[-2]
            stack_sig = \
                "{relpath}:{s.name}".format(
                    s=caller, relpath=relpath(caller.filename, toppath))
            sig = (id(self), stack_sig)
            # we will count based on id(self) + wherefrom
            if caller.lineno is not None:
                memo[sig][caller.lineno] += 1
            t0 = time()
            return func(*args, **kwargs)
        finally:
            times.append(time() - t0)
            pass

    def print_stats() -> None:
        print("The cost of property {}:".format(func.__name__))
        if not memo:
            print("None since no calls")
            return
        # total count
        counts = {k: sum(v.values()) for k,v in memo.items()}
        total = sum(counts.values())
        ids = {self_id for (self_id, _) in memo}
        print(" Total: {} calls from {} objects with {} contexts taking {:.2f} sec"
              .format(total, len(ids), len(memo), sum(times)))
        # now we need to sort by value
        for (self_id, caller), count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            print("  {} {}: {} from {} lines"
                  .format(self_id, caller, count, len(memo[(self_id, caller)])))

    # Upon total exit we print the stats
    import atexit
    atexit.register(print_stats)

    return  _wrap_collect_method_callstats


# Borrowed from duecredit to wrap duecredit-handling to guarantee failsafe
def never_fail(f: Callable[P, T]) -> Callable[P, Optional[T]]:
    """Assure that function never fails -- all exceptions are caught

    Returns `None` if function fails internally.
    """
    @wraps(f)
    def wrapped_func(*args: P.args, **kwargs: P.kwargs) -> Optional[T]:
        try:
            return f(*args, **kwargs)
        except Exception as e:
            lgr.warning(
                "DataLad internal failure while running %s: %r. "
                "Please report at https://github.com/datalad/datalad/issues"
                % (f, e)
            )
            return None

    if os.environ.get('DATALAD_ALLOW_FAIL', False):
        return f
    else:
        return wrapped_func


def shortened_repr(value: Any, l: int=30) -> str:
    try:
        if hasattr(value, '__repr__') and (value.__repr__ is not object.__repr__):
            value_repr = repr(value)
            if not value_repr.startswith('<') and len(value_repr) > l:
                value_repr = "<<%s++%d chars++%s>>" % (
                    value_repr[:l - 16],
                    len(value_repr) - (l - 16 + 4),
                    value_repr[-4:]
                )
            elif value_repr.startswith('<') and value_repr.endswith('>') and ' object at 0x':
                raise ValueError("I hate those useless long reprs")
        else:
            raise ValueError("gimme class")
    except Exception as e:
        value_repr = "<%s>" % value.__class__.__name__.split('.')[-1]
    return value_repr


def __auto_repr__(obj: Any, short: bool =True) -> str:
    attr_names: tuple[str, ...] = tuple()
    if hasattr(obj, '__dict__'):
        attr_names += tuple(obj.__dict__.keys())
    if hasattr(obj, '__slots__'):
        attr_names += tuple(obj.__slots__)

    items = []
    for attr in sorted(set(attr_names)):
        if attr.startswith('_'):
            continue
        value = getattr(obj, attr)
        # TODO:  should we add this feature to minimize some talktative reprs
        # such as of URL?
        #if value is None:
        #    continue
        items.append("%s=%s" % (attr, shortened_repr(value) if short else value))

    return "%s(%s)" % (obj.__class__.__name__, ', '.join(items))


@optional_args
def auto_repr(cls: type[T], short: bool=True) -> type[T]:
    """Decorator for a class to assign it an automagic quick and dirty __repr__

    It uses public class attributes to prepare repr of a class

    Original idea: http://stackoverflow.com/a/27799004/1265472
    """

    cls.__repr__ = lambda obj:__auto_repr__(obj, short=short)  # type: ignore[assignment]
    return cls


def todo_interface_for_extensions(f: T) -> T:
    return f


#
# Context Managers
#


# unused in -core
@contextmanager
def nothing_cm() -> Iterator[None]:
    """Just a dummy cm to programmically switch context managers"""
    yield


class SwallowOutputsAdapter:
    """Little adapter to help getting out/err values
    """
    def __init__(self) -> None:
        kw = get_tempfile_kwargs({}, prefix="outputs")

        self._out = NamedTemporaryFile(delete=False, mode='w', **kw)
        self._err = NamedTemporaryFile(delete=False, mode='w', **kw)

    def _read(self, h: IO[str]) -> str:
        with open(h.name) as f:
            return f.read()

    @property
    def out(self) -> str:
        if not self._out.closed:
            self._out.flush()
        return self._read(self._out)

    @property
    def err(self) -> str:
        if not self._err.closed:
            self._err.flush()
        return self._read(self._err)

    @property
    def handles(self) -> tuple[TextIO, TextIO]:
        return (cast(TextIO, self._out), cast(TextIO, self._err))

    def cleanup(self) -> None:
        self._out.close()
        self._err.close()
        out_name = self._out.name
        err_name = self._err.name
        from datalad import cfg
        if cfg.getbool('datalad.log', 'outputs', default=False) \
                and lgr.getEffectiveLevel() <= logging.DEBUG:
            for s, sname in ((self.out, 'stdout'),
                             (self.err, 'stderr')):
                if s:
                    pref = os.linesep + "| "
                    lgr.debug("Swallowed %s:%s%s", sname, pref, s.replace(os.linesep, pref))
                else:
                    lgr.debug("Nothing was swallowed for %s", sname)
        del self._out
        del self._err
        gc.collect()
        rmtemp(out_name)
        rmtemp(err_name)

@contextmanager
def swallow_outputs() -> Iterator[SwallowOutputsAdapter]:
    """Context manager to help consuming both stdout and stderr, and print()

    stdout is available as cm.out and stderr as cm.err whenever cm is the
    yielded context manager.
    Internally uses temporary files to guarantee absent side-effects of swallowing
    into StringIO which lacks .fileno.

    print mocking is necessary for some uses where sys.stdout was already bound
    to original sys.stdout, thus mocking it later had no effect. Overriding
    print function had desired effect
    """

    def fake_print(*args: str, sep: str = ' ', end: str = "\n", file: Optional[IO[str]] = None) -> None:
        if file is None:
            file = sys.stdout

        if file in (oldout, olderr, sys.stdout, sys.stderr):
            # we mock
            try:
                sys.stdout.write(sep.join(args) + end)
            except UnicodeEncodeError as exc:
                lgr.error(
                    "Failed to write to mocked stdout, got %s, continue as it "
                    "didn't happen",  exc)
        else:
            # must be some other file one -- leave it alone
            oldprint(*args, sep=sep, end=end, file=file)

    from .ui import ui

    # preserve -- they could have been mocked already
    oldprint = getattr(builtins, 'print')
    oldout, olderr = sys.stdout, sys.stderr
    olduiout = ui.out
    adapter = SwallowOutputsAdapter()

    try:
        sys.stdout, sys.stderr = adapter.handles
        ui.out = adapter.handles[0]
        setattr(builtins, 'print', fake_print)

        yield adapter
    finally:
        sys.stdout, sys.stderr, ui.out = oldout, olderr, olduiout
        setattr(builtins, 'print',  oldprint)
        adapter.cleanup()


# Let's log everything into a string
# TODO: generalize with the one for swallow_outputs
class SwallowLogsAdapter:
    """Little adapter to help getting out values

    And to stay consistent with how swallow_outputs behaves
    """
    def __init__(self, file_: str | Path | None) -> None:
        self._out: IO[str]
        if file_ is None:
            kw = get_tempfile_kwargs({}, prefix="logs")
            self._out = NamedTemporaryFile(mode='a', delete=False, **kw)
        else:
            out_file = file_
            # PY3 requires clearly one or another.  race condition possible
            self._out = open(out_file, 'a')
        self.file = file_
        self._final_out: Optional[str] = None

    def _read(self, h: IO[str]) -> str:
        with open(h.name) as f:
            return f.read()

    @property
    def out(self) -> str:
        if self._final_out is not None:
            # we closed and cleaned up already
            return self._final_out
        else:
            self._out.flush()
            return self._read(self._out)

    @property
    def lines(self) -> list[str]:
        return self.out.split('\n')

    @property
    def handle(self) -> IO[str]:
        return self._out

    def cleanup(self) -> None:
        # store for access while object exists
        self._final_out = self.out
        self._out.close()
        out_name = self._out.name
        del self._out
        gc.collect()
        if not self.file:
            rmtemp(out_name)

    def assert_logged(self, msg: Optional[str]=None, level: Optional[str]=None, regex: bool =True, **kwargs: Any) -> None:
        """Provide assertion on whether a msg was logged at a given level

        If neither `msg` nor `level` provided, checks if anything was logged
        at all.

        Parameters
        ----------
        msg: str, optional
          Message (as a regular expression, if `regex`) to be searched.
          If no msg provided, checks if anything was logged at a given level.
        level: str, optional
          String representing the level to be logged
        regex: bool, optional
          If False, regular `assert_in` is used
        **kwargs: str, optional
          Passed to `assert_re_in` or `assert_in`
        """
        from datalad.tests.utils_pytest import (
            assert_in,
            assert_re_in,
        )

        if regex:
            match = r'\[%s\] ' % level if level else r"\[\S+\] "
        else:
            match = '[%s] ' % level if level else ''

        if msg:
            match += msg

        if match:
            (assert_re_in if regex else assert_in)(match, self.out, **kwargs)
        else:
            assert not kwargs, "no kwargs to be passed anywhere"
            assert self.out, "Nothing was logged!?"


@contextmanager
def swallow_logs(new_level: str | int | None = None, file_ : str | Path | None = None, name: str='datalad') -> Iterator[SwallowLogsAdapter]:
    """Context manager to consume all logs."""
    lgr = logging.getLogger(name)

    # Keep old settings
    old_level = lgr.level
    old_handlers = lgr.handlers

    adapter = SwallowLogsAdapter(file_)
    # TODO: it does store messages but without any formatting, i.e. even without
    # date/time prefix etc.  IMHO it should preserve formatting in case if file_ is
    # set
    swallow_handler = logging.StreamHandler(adapter.handle)
    # we want to log levelname so we could test against it
    swallow_handler.setFormatter(
        logging.Formatter('[%(levelname)s] %(message)s'))
    swallow_handler.filters = sum([h.filters for h in old_handlers],
                                  [])
    lgr.handlers = [swallow_handler]
    if old_level < logging.DEBUG:  # so if HEAVYDEBUG etc -- show them!
        lgr.handlers += old_handlers

    if isinstance(new_level, str):
        new_level = getattr(logging, new_level)

    if new_level is not None:
        lgr.setLevel(new_level)

    try:
        yield adapter
        # TODO: if file_ and there was an exception -- most probably worth logging it?
        # although ideally it should be the next log outside added to that file_ ... oh well
    finally:
        lgr.handlers = old_handlers
        lgr.setLevel(old_level)
        adapter.cleanup()


# TODO: May be melt in with swallow_logs at some point:
@contextmanager
def disable_logger(logger: Optional[logging.Logger]=None) -> Iterator[logging.Logger]:
    """context manager to temporarily disable logging

    This is to provide one of swallow_logs' purposes without unnecessarily
    creating temp files (see gh-1865)

    Parameters
    ----------
    logger: Logger
        Logger whose handlers will be ordered to not log anything.
        Default: datalad's topmost Logger ('datalad')
    """

    class NullFilter(logging.Filter):
        """Filter class to reject all records
        """
        def filter(self, record: logging.LogRecord) -> bool:
            return False

    if logger is None:
        # default: all of datalad's logging:
        logger = logging.getLogger('datalad')

    filter_ = NullFilter(logger.name)
    for h in logger.handlers:
        h.addFilter(filter_)

    try:
        yield logger
    finally:
        for h in logger.handlers:
            h.removeFilter(filter_)


@contextmanager
def lock_if_required(lock_required: bool, lock: threading.Lock) -> Iterator[threading.Lock]:
    """ Acquired and released the provided lock if indicated by a flag"""
    if lock_required:
        lock.acquire()
    try:
        yield lock
    finally:
        if lock_required:
            lock.release()


#
# Additional handlers
#
def ensure_dir(*args: str) -> str:
    """Make sure directory exists.

    Joins the list of arguments to an os-specific path to the desired
    directory and creates it, if it not exists yet.
    """
    dirname = op.join(*args)
    if not exists(dirname):
        os.makedirs(dirname)
    return dirname


def updated(d: dict[K, V], update: dict[K, V]) -> dict[K, V]:
    """Return a copy of the input with the 'update'

    Primarily for updating dictionaries
    """
    d = d.copy()
    d.update(update)
    return d


_pwd_mode: Optional[str] = None


def _switch_to_getcwd(msg: str, *args: Any) -> None:
    global _pwd_mode
    _pwd_mode = 'cwd'
    lgr.debug(
        msg + ". From now on will be returning os.getcwd(). Directory"
               " symlinks in the paths will be resolved",
        *args
    )
    # TODO:  we might want to mitigate by going through all flywheighted
    # repos and tuning up their .paths to be resolved?


def getpwd() -> str:
    """Try to return a CWD without dereferencing possible symlinks

    This function will try to use PWD environment variable to provide a current
    working directory, possibly with some directories along the path being
    symlinks to other directories.  Unfortunately, PWD is used/set only by the
    shell and such functions as `os.chdir` and `os.getcwd` nohow use or modify
    it, thus `os.getcwd()` returns path with links dereferenced.

    While returning current working directory based on PWD env variable we
    verify that the directory is the same as `os.getcwd()` after resolving all
    symlinks.  If that verification fails, we fall back to always use
    `os.getcwd()`.

    Initial decision to either use PWD env variable or os.getcwd() is done upon
    the first call of this function.
    """
    global _pwd_mode
    if _pwd_mode is None:
        # we need to decide!
        try:
            pwd = os.environ['PWD']
            if on_windows and pwd and pwd.startswith('/'):
                # It should be a path from MSYS.
                # - it might start with a drive letter or not
                # - it seems to be "illegal" to have a single letter directories
                #   under / path, i.e. if created - they aren't found
                # - 'ln -s' does not fail to create a "symlink" but it just
                # copies!
                #   so we are not likely to need original PWD purpose on
                # those systems
                # Verdict:
                _pwd_mode = 'cwd'
            else:
                _pwd_mode = 'PWD'
        except KeyError:
            _pwd_mode = 'cwd'

    if _pwd_mode == 'cwd':
        return os.getcwd()
    elif _pwd_mode == 'PWD':
        try:
            cwd = os.getcwd()
        except OSError as exc:
            if "o such file" in str(exc):
                # directory was removed but we promised to be robust and
                # still report the path we might know since we are still in PWD
                # mode
                cwd = None
            else:
                raise
        try:
            pwd = os.environ['PWD']
            # do absolute() in addition to always get an absolute path
            # even with non-existing paths on windows
            pwd_real = str(Path(pwd).resolve().absolute())
            # This logic would fail to catch the case where chdir did happen
            # to the directory where current PWD is pointing to, e.g.
            # $> ls -ld $PWD
            # lrwxrwxrwx 1 yoh yoh 5 Oct 11 13:27 /home/yoh/.tmp/tmp -> /tmp//
            # hopa:~/.tmp/tmp
            # $> python -c 'import os; os.chdir("/tmp"); from datalad.utils import getpwd; print(getpwd(), os.getcwd())'
            # ('/home/yoh/.tmp/tmp', '/tmp')
            # but I guess that should not be too harmful
            if cwd is not None and pwd_real != cwd:
                _switch_to_getcwd(
                    "realpath of PWD=%s is %s whenever os.getcwd()=%s",
                    pwd, pwd_real, cwd
                )
                return cwd
            return pwd
        except KeyError:
            _switch_to_getcwd("PWD env variable is no longer available")
            if cwd is not None:
                return cwd  # Must not happen, but may be someone
                            # evil purges PWD from environ?
    raise RuntimeError(
        "Must have not got here. "
        "pwd_mode must be either cwd or PWD. And it is now %r" % (_pwd_mode,)
    )


class chpwd:
    """Wrapper around os.chdir which also adjusts environ['PWD']

    The reason is that otherwise PWD is simply inherited from the shell
    and we have no ability to assess directory path without dereferencing
    symlinks.

    If used as a context manager it allows to temporarily change directory
    to the given path
    """
    def __init__(self, path: str | Path | None, mkdir: bool=False, logsuffix: str='') -> None:

        self._prev_pwd: Optional[str]
        if path:
            pwd = getpwd()
            self._prev_pwd = pwd
        else:
            self._prev_pwd = None
            return

        if not isabs(path):
            path = normpath(op.join(pwd, path))
        if not os.path.exists(path) and mkdir:
            self._mkdir = True
            os.mkdir(path)
        else:
            self._mkdir = False
        lgr.debug("chdir %r -> %r %s", self._prev_pwd, path, logsuffix)
        os.chdir(path)  # for grep people -- ok, to chdir here!
        os.environ['PWD'] = str(path)

    def __enter__(self) -> None:
        # nothing more to do really, chdir was in the constructor
        pass

    def __exit__(self, exc_type: Optional[type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        if self._prev_pwd:
            # Need to use self.__class__ so this instance, if the entire
            # thing mocked during the test, still would use correct chpwd
            self.__class__(self._prev_pwd, logsuffix="(coming back)")


def dlabspath(path: str | Path, norm: bool =False) -> str:
    """Symlinks-in-the-cwd aware abspath

    os.path.abspath relies on os.getcwd() which would not know about symlinks
    in the path

    TODO: we might want to norm=True by default to match behavior of
    os .path.abspath?
    """
    if not isabs(path):
        # if not absolute -- relative to pwd
        path = op.join(getpwd(), path)
    return normpath(path) if norm else str(path)


def with_pathsep(path: str) -> str:
    """Little helper to guarantee that path ends with /"""
    return path + sep if not path.endswith(sep) else path


def get_path_prefix(path: str | Path, pwd: Optional[str]=None) -> str:
    """Get path prefix (for current directory)

    Returns relative path to the topdir, if we are under topdir, and if not
    absolute path to topdir.  If `pwd` is not specified - current directory
    assumed
    """
    pwd = pwd or getpwd()
    path = dlabspath(path)
    path_ = with_pathsep(path)
    pwd_ = with_pathsep(pwd)
    common = commonprefix((path_, pwd_))
    if common.endswith(sep) and common in {path_, pwd_}:
        # we are in subdir or above the path = use relative path
        location_prefix = relpath(path, pwd)
        # if benign "here" - cut off
        if location_prefix in (curdir, curdir + sep):
            location_prefix = ''
        return location_prefix
    else:
        # just return absolute path
        return path


def _get_normalized_paths(path: str, prefix: str) -> tuple[str, str]:
    if isabs(path) != isabs(prefix):
        raise ValueError("Both paths must either be absolute or relative. "
                         "Got %r and %r" % (path, prefix))
    path = with_pathsep(path)
    prefix = with_pathsep(prefix)
    return path, prefix


def path_startswith(path: str, prefix: str) -> bool:
    """Return True if path starts with prefix path

    Parameters
    ----------
    path: str
    prefix: str
    """
    path, prefix = _get_normalized_paths(path, prefix)
    return path.startswith(prefix)


def path_is_subpath(path: str, prefix: str) -> bool:
    """Return True if path is a subpath of prefix

    It will return False if path == prefix.

    Parameters
    ----------
    path: str
    prefix: str
    """
    path, prefix = _get_normalized_paths(path, prefix)
    return (len(prefix) < len(path)) and path.startswith(prefix)


def knows_annex(path: str | Path) -> bool:
    """Returns whether at a given path there is information about an annex

    It is just a thin wrapper around GitRepo.is_with_annex() classmethod
    which also checks for `path` to exist first.

    This includes actually present annexes, but also uninitialized ones, or
    even the presence of a remote annex branch.
    """
    from os.path import exists
    if not exists(path):
        lgr.debug("No annex: test path %s doesn't exist", path)
        return False
    from datalad.support.gitrepo import GitRepo
    return GitRepo(path, init=False, create=False).is_with_annex()


@contextmanager
def make_tempfile(content: str | bytes | None = None, wrapped: Optional[Callable[..., Any]] = None, **tkwargs: Any) -> Iterator[str]:
    """Helper class to provide a temporary file name and remove it at the end (context manager)

    Parameters
    ----------
    mkdir : bool, optional (default: False)
        If True, temporary directory created using tempfile.mkdtemp()
    content : str or bytes, optional
        Content to be stored in the file created
    wrapped : function, optional
        If set, function name used to prefix temporary file name
    `**tkwargs`:
        All other arguments are passed into the call to tempfile.mk{,d}temp(),
        and resultant temporary filename is passed as the first argument into
        the function t.  If no 'prefix' argument is provided, it will be
        constructed using module and function names ('.' replaced with
        '_').

    To change the used directory without providing keyword argument 'dir' set
    DATALAD_TESTS_TEMP_DIR.

    Examples
    --------
        >>> from os.path import exists
        >>> from datalad.utils import make_tempfile
        >>> with make_tempfile() as fname:
        ...    k = open(fname, 'w').write('silly test')
        >>> assert not exists(fname)  # was removed

        >>> with make_tempfile(content="blah") as fname:
        ...    assert open(fname).read() == "blah"
    """

    if tkwargs.get('mkdir', None) and content is not None:
        raise ValueError("mkdir=True while providing content makes no sense")

    tkwargs_ = get_tempfile_kwargs(tkwargs, wrapped=wrapped)

    # if DATALAD_TESTS_TEMP_DIR is set, use that as directory,
    # let mktemp handle it otherwise. However, an explicitly provided
    # dir=... will override this.
    mkdir = bool(tkwargs_.pop('mkdir', False))

    filename = {False: tempfile.mktemp,
                True: tempfile.mkdtemp}[mkdir](**tkwargs_)
    # MIH: not clear to me why we need to perform this (possibly expensive)
    # resolve. It was already part of the original implementation
    # 008d9ab8cc3e0170c0a9b8479e80dee9ffe6eb7f
    filepath = Path(filename).resolve()

    if content:
        if isinstance(content, bytes):
            filepath.write_bytes(content)
        else:
            filepath.write_text(content)

    # TODO globbing below can also be done with pathlib
    filename = str(filepath)

    if __debug__:
        lgr.debug(
            'Created temporary %s named %s',
            'directory' if mkdir else 'file',
            filename)
    try:
        yield filename
    finally:
        # glob here for all files with the same name (-suffix)
        # would be useful whenever we requested .img filename,
        # and function creates .hdr as well
        # MIH: this is undocumented behavior, and undesired in the general
        # case. it should be made conditional and explicit
        lsuffix = len(tkwargs_.get('suffix', ''))
        filename_ = lsuffix and filename[:-lsuffix] or filename
        filenames = glob.glob(filename_ + '*')
        if len(filename_) < 3 or len(filenames) > 5:
            # For paranoid yoh who stepped into this already ones ;-)
            lgr.warning("It is unlikely that it was intended to remove all"
                        " files matching %r. Skipping" % filename_)
            return
        for f in filenames:
            try:
                rmtemp(f)
            except OSError:  # pragma: no cover
                pass


def _path_(*p: str) -> str:
    """Given a path in POSIX notation, regenerate one in native to the env one"""
    if on_windows:
        return op.join(*map(lambda x: op.join(*x.split('/')), p))
    else:
        # Assume that all others as POSIX compliant so nothing to be done
        return op.join(*p)


def get_timestamp_suffix(time_: int | time.struct_time | None=None, prefix: str='-') -> str:
    """Return a time stamp (full date and time up to second)

    primarily to be used for generation of log files names
    """
    args = []
    if time_ is not None:
        if isinstance(time_, int):
            time_ = time.gmtime(time_)
        args.append(time_)
    return time.strftime(prefix + TIMESTAMP_FMT, *args)


# unused in -core
def get_logfilename(dspath: str | Path, cmd: str='datalad') -> str:
    """Return a filename to use for logging under a dataset/repository

    directory would be created if doesn't exist, but dspath must exist
    and be a directory
    """
    assert(exists(dspath))
    assert(isdir(dspath))
    ds_logdir = ensure_dir(str(dspath), '.git', 'datalad', 'logs')  # TODO: use WEB_META_LOG whenever #789 merged
    return op.join(ds_logdir, 'crawl-%s.log' % get_timestamp_suffix())


def get_trace(edges: Sequence[tuple[T, T]], start: T, end: T, trace: Optional[list[T]]=None) -> Optional[list[T]]:
    """Return the trace/path to reach a node in a tree.

    Parameters
    ----------
    edges : sequence(2-tuple)
      The tree given by a sequence of edges (parent, child) tuples. The
      nodes can be identified by any value and data type that supports
      the '==' operation.
    start :
      Identifier of the start node. Must be present as a value in the parent
      location of an edge tuple in order to be found.
    end :
      Identifier of the target/end node. Must be present as a value in the child
      location of an edge tuple in order to be found.
    trace : list
      Mostly useful for recursive calls, and used internally.

    Returns
    -------
    None or list
      Returns a list with the trace to the target (the starts and the target
      are not included in the trace, hence if start and end are directly connected
      an empty list is returned), or None when no trace to the target can be found,
      or start and end are identical.
    """
    # the term trace is used to avoid confusion with a path in the sense
    # of a filesystem path, but the analogy fits and nodes can be paths
    if trace is None:
        trace = []
    if not edges:
        raise ValueError("no edges given")
    for cand in edges:
        cand_super, cand_sub = cand
        if cand_sub in trace:
            # only DAGs, skip any cyclic traces
            continue
        if trace and cand_super != trace[-1]:
            # only consider edges that lead off the end of the trace
            continue
        if not trace and cand_super != start:
            # we got nothing yet, and this edges is not matching the start
            continue
        if cand_sub == end:
            return trace
        # dive into potential subnodes
        cand_trace = get_trace(
            edges,
            start,
            end,
            trace + [cand_sub])
        if cand_trace:
            return cand_trace
    return None


def get_dataset_root(path: str | Path) -> Optional[str]:
    """Return the root of an existent dataset containing a given path

    The root path is returned in the same absolute or relative form
    as the input argument. If no associated dataset exists, or the
    input path doesn't exist, None is returned.

    If `path` is a symlink or something other than a directory, its
    the root dataset containing its parent directory will be reported.
    If none can be found, at a symlink at `path` is pointing to a
    dataset, `path` itself will be reported as the root.

    Parameters
    ----------
    path : Path-like

    Returns
    -------
    str or None
    """

    # NOTE: path = "" is effectively "."

    path = str(path)
    suffix = '.git'
    altered = None
    if islink(path) or not isdir(path):
        altered = path
        path = dirname(path)
    apath = abspath(path)
    # while we can still go up
    while split(apath)[1]:
        if exists(op.join(path, suffix)):
            return path
        # new test path in the format we got it
        path = normpath(op.join(path, os.pardir))
        # no luck, next round
        apath = abspath(path)
    # if we applied dirname() at the top, we give it another go with
    # the actual path, if it was itself a symlink, it could be the
    # top-level dataset itself
    if altered and exists(op.join(altered, suffix)):
        return altered

    return None


# ATM used in datalad_crawler extension, so do not remove yet
def try_multiple(ntrials: int, exception: type[BaseException], base: float, f: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Call f multiple times making exponentially growing delay between the calls"""
    for trial in range(1, ntrials+1):
        try:
            return f(*args, **kwargs)
        except exception as exc:
            if trial == ntrials:
                raise  # just reraise on the last trial
            t = base ** trial
            lgr.warning("Caught %s on trial #%d. Sleeping %f and retrying",
                        CapturedException(exc), trial, t)
            sleep(t)
    raise ValueError("ntrials must be > 0")


@optional_args
def try_multiple_dec(
        f: Callable[P, T],
        ntrials: Optional[int] = None,
        duration: float = 0.1,
        exceptions: type[BaseException] | tuple[type[BaseException], ...] | None = None,
        increment_type: Literal["exponential"] | None = None,
        exceptions_filter: Optional[Callable[[BaseException], Any]] = None,
        logger: Optional[Callable] = None,
) -> Callable[P, T]:
    """Decorator to try function multiple times.

    Main purpose is to decorate functions dealing with removal of files/directories
    and which might need a few seconds to work correctly on Windows which takes
    its time to release files/directories.

    Parameters
    ----------
    ntrials: int, optional
    duration: float, optional
      Seconds to sleep before retrying.
    increment_type: {None, 'exponential'}
      Note that if it is exponential, duration should typically be > 1.0
      so it grows with higher power
    exceptions: Exception or tuple of Exceptions, optional
      Exception or a tuple of multiple exceptions, on which to retry
    exceptions_filter: callable, optional
      If provided, this function will be called with a caught exception
      instance.  If function returns True - we will re-try, if False - exception
      will be re-raised without retrying.
    logger: callable, optional
      Logger to log upon failure.  If not provided, will use stock logger
      at the level of 5 (heavy debug).
    """
    # We need to bind these to new names so that mypy doesn't complain about
    # the values possibly being `None` inside the inner function:
    exceptions_: type[BaseException] | tuple[type[BaseException], ...]
    if not exceptions:
        exceptions_ = (OSError, PermissionError) if on_windows else OSError
    else:
        exceptions_ = exceptions
    if not ntrials:
        # Life goes fast on proper systems, no need to delay it much
        ntrials_ = 100 if on_windows else 10
    else:
        ntrials_ = ntrials
    if logger is None:
        def logger_(*args: Any, **kwargs: Any) -> None:
            return lgr.log(5, *args, **kwargs)
    else:
        logger_ = logger
    assert increment_type in {None, 'exponential'}

    @wraps(f)
    def _wrap_try_multiple_dec(*args: P.args, **kwargs: P.kwargs) -> T:
        t = duration
        for trial in range(ntrials_):
            try:
                return f(*args, **kwargs)
            except exceptions_ as exc:
                if exceptions_filter and not exceptions_filter(exc):
                    raise
                if trial < ntrials_ - 1:
                    if increment_type == 'exponential':
                        t = duration ** (trial + 1)
                    logger_(
                        "Caught %s on trial #%d. Sleeping %f and retrying",
                        CapturedException(exc), trial, t)
                    sleep(t)
                else:
                    raise
        raise ValueError("ntrials must be > 0")

    return _wrap_try_multiple_dec


@try_multiple_dec
def unlink(f: str | Path) -> None:
    """'Robust' unlink.  Would try multiple times

    On windows boxes there is evidence for a latency of more than a second
    until a file is considered no longer "in-use".
    WindowsError is not known on Linux, and if IOError or any other
    exception
    is thrown then if except statement has WindowsError in it -- NameError
    also see gh-2533
    """
    # Check for open files
    assert_no_open_files(f)
    return os.unlink(f)


@try_multiple_dec
def _rmtree(*args: Any, **kwargs: Any) -> None:
    """Just a helper to decorate shutil.rmtree.

    rmtree defined above does more and ideally should not itself be decorated
    since a recursive definition and does checks for open files inside etc -
    might be too runtime expensive
    """
    shutil.rmtree(*args, **kwargs)


def slash_join(base: Optional[str], extension: Optional[str]) -> Optional[str]:
    """Join two strings with a '/', avoiding duplicate slashes

    If any of the strings is None the other is returned as is.
    """
    if extension is None:
        return base
    if base is None:
        return extension
    return '/'.join(
        (base.rstrip('/'),
         extension.lstrip('/')))


#
# IO Helpers
#

# unused in -core
def open_r_encdetect(fname: str | Path, readahead: int=1000) -> IO[str]:
    """Return a file object in read mode with auto-detected encoding

    This is helpful when dealing with files of unknown encoding.

    Parameters
    ----------
    readahead: int, optional
      How many bytes to read for guessing the encoding type.  If
      negative - full file will be read
    """
    import io

    from chardet import detect

    # read some bytes from the file
    with open(fname, 'rb') as f:
        head = f.read(readahead)
    enc = detect(head)
    denc = enc.get('encoding', None)
    lgr.debug("Auto-detected encoding %s for file %s (confidence: %s)",
              denc,
              fname,
              enc.get('confidence', 'unknown'))
    return io.open(fname, encoding=denc)


@overload
def read_file(fname: str | Path, decode: Literal[True] =True) -> str:
    ...

@overload
def read_file(fname: str | Path, decode: Literal[False]) -> bytes:
    ...

def read_file(fname: str | Path, decode: Literal[True, False] =True) -> str | bytes:
    """A helper to read file passing content via ensure_unicode

    Parameters
    ----------
    decode: bool, optional
      if False, no ensure_unicode and file content returned as bytes
    """
    with open(fname, 'rb') as f:
        content = f.read()
    return ensure_unicode(content) if decode else content


def read_csv_lines(fname: str | Path, dialect: Optional[str] = None, readahead: int=16384, **kwargs: Any) -> Iterator[dict[str, str]]:
    """A generator of dict records from a CSV/TSV

    Automatically guesses the encoding for each record to convert to UTF-8

    Parameters
    ----------
    fname: str
      Filename
    dialect: str, optional
      Dialect to specify to csv.reader. If not specified -- guessed from
      the file, if fails to guess, "excel-tab" is assumed
    readahead: int, optional
      How many bytes to read from the file to guess the type
    **kwargs
      Passed to `csv.reader`
    """
    import csv
    csv_dialect: str | type[csv.Dialect]
    if dialect is None:
        with open(fname) as tsvfile:
            # add robustness, use a sniffer
            try:
                csv_dialect = csv.Sniffer().sniff(tsvfile.read(readahead))
            except Exception as exc:
                lgr.warning(
                    'Could not determine file-format, assuming TSV: %s',
                    CapturedException(exc)
                )
                csv_dialect = 'excel-tab'
    else:
        csv_dialect = dialect

    with open(fname, 'r', encoding="utf-8") as tsvfile:
        csv_reader = csv.reader(
            tsvfile,
            dialect=csv_dialect,
            **kwargs
        )
        header: Optional[list[str]] = None
        for row in csv_reader:
            if header is None:
                header = row
            else:
                yield dict(zip(header, row))


def import_modules(modnames: Iterable[str], pkg: str, msg: str="Failed to import {module}", log: Callable[[str], Any]=lgr.debug) -> list[ModuleType]:
    """Helper to import a list of modules without failing if N/A

    Parameters
    ----------
    modnames: list of str
      List of module names to import
    pkg: str
      Package under which to import
    msg: str, optional
      Message template for .format() to log at DEBUG level if import fails.
      Keys {module} and {package} will be provided and ': {exception}' appended
    log: callable, optional
      Logger call to use for logging messages
    """
    from importlib import import_module
    _globals = globals()
    mods_loaded = []
    if pkg and not pkg in sys.modules:
        # with python 3.5.1 (ok with 3.5.5) somehow kept running into
        #  Failed to import dlsub1: Parent module 'dltestm1' not loaded
        # while running the test. Preloading pkg resolved the issue
        import_module(pkg)
    for modname in modnames:
        try:
            _globals[modname] = mod = import_module(
                '.{}'.format(modname),
                pkg)
            mods_loaded.append(mod)
        except Exception as exc:
            from datalad.support.exceptions import CapturedException
            ce = CapturedException(exc)
            log((msg + ': {exception}').format(
                module=modname, package=pkg, exception=ce.message))
    return mods_loaded


def import_module_from_file(modpath: str, pkg: Optional[ModuleType]=None, log: Callable[[str], Any]=lgr.debug) -> ModuleType:
    """Import provided module given a path

    TODO:
    - RF/make use of it in pipeline.py which has similar logic
    - join with import_modules above?

    Parameters
    ----------
    pkg: module, optional
       If provided, and modpath is under pkg.__path__, relative import will be
       used
    """
    assert(modpath.endswith('.py'))  # for now just for .py files

    log("Importing %s" % modpath)

    modname = basename(modpath)[:-3]
    relmodpath = None
    if pkg:
        for pkgpath in pkg.__path__:
            if path_is_subpath(modpath, pkgpath):
                # for now relying on having .py extension -- assertion above
                relmodpath = '.' + relpath(modpath[:-3], pkgpath).replace(sep, '.')
                break

    try:
        if relmodpath:
            from importlib import import_module
            mod = import_module(relmodpath, pkg.__name__ if pkg is not None else None)
        else:
            dirname_ = dirname(modpath)
            try:
                sys.path.insert(0, dirname_)
                mod = __import__(modname, level=0)
            finally:
                if dirname_ in sys.path:
                    sys.path.pop(sys.path.index(dirname_))
                else:
                    log("Expected path %s to be within sys.path, but it was gone!" % dirname_)
    except Exception as e:
        raise RuntimeError(
            "Failed to import module from %s" % modpath) from e

    return mod


def get_encoding_info() -> dict[str, str]:
    """Return a dictionary with various encoding/locale information"""
    import locale
    import sys
    return dict([
        ('default', sys.getdefaultencoding()),
        ('filesystem', sys.getfilesystemencoding()),
        ('locale.prefered', locale.getpreferredencoding()),
    ])


def get_envvars_info() -> dict[str, str]:
    envs = []
    for var, val in os.environ.items():
        if (
                var.startswith('PYTHON') or
                var.startswith('LC_') or
                var.startswith('GIT_') or
                var in ('LANG', 'LANGUAGE', 'PATH')
        ):
            envs.append((var, val))
    return dict(envs)


# This class is modified from Snakemake (v5.1.4)
class SequenceFormatter(string.Formatter):
    """string.Formatter subclass with special behavior for sequences.

    This class delegates formatting of individual elements to another
    formatter object. Non-list objects are formatted by calling the
    delegate formatter's "format_field" method. List-like objects
    (list, tuple, set, frozenset) are formatted by formatting each
    element of the list according to the specified format spec using
    the delegate formatter and then joining the resulting strings with
    a separator (space by default).
    """

    def __init__(self, separator: str=" ", element_formatter: string.Formatter =string.Formatter(),
                 *args: Any, **kwargs: Any) -> None:
        self.separator = separator
        self.element_formatter = element_formatter

    def format_element(self, elem: Any, format_spec: str) -> Any:
        """Format a single element

        For sequences, this is called once for each element in a
        sequence. For anything else, it is called on the entire
        object. It is intended to be overridden in subclases.
        """
        return self.element_formatter.format_field(elem, format_spec)

    def format_field(self, value: Any, format_spec: str) -> Any:
        if isinstance(value, (list, tuple, set, frozenset)):
            return self.separator.join(self.format_element(v, format_spec)
                                       for v in value)
        else:
            return self.format_element(value, format_spec)


# TODO: eventually we might want to make use of attr module
class File:
    """Helper for a file entry in the create_tree/@with_tree

    It allows to define additional settings for entries
    """
    def __init__(self, name: str, executable: bool=False) -> None:
        """

        Parameters
        ----------
        name : str
          Name of the file
        executable: bool, optional
          Make it executable
        """
        self.name = name
        self.executable = executable

    def __str__(self) -> str:
        return self.name


TreeSpec = Union[
    Tuple[Tuple[Union[str, File], "Load"], ...],
    List[Tuple[Union[str, File], "Load"]],
    Dict[Union[str, File], "Load"],
]

Load = Union[str, bytes, "TreeSpec"]


def create_tree_archive(path: str, name: str, load: TreeSpec, overwrite: bool=False, archives_leading_dir: bool=True) -> None:
    """Given an archive `name`, create under `path` with specified `load` tree
    """
    from datalad.support.archives import compress_files
    dirname = file_basename(name)
    full_dirname = op.join(path, dirname)
    os.makedirs(full_dirname)
    create_tree(full_dirname, load, archives_leading_dir=archives_leading_dir)
    # create archive
    if archives_leading_dir:
        compress_files([dirname], name, path=path, overwrite=overwrite)
    else:
        compress_files(
            # <https://github.com/python/mypy/issues/9864>
            list(map(basename, glob.glob(op.join(full_dirname, '*')))),  # type: ignore[arg-type]
                       op.join(pardir, name),
                       path=op.join(path, dirname),
                       overwrite=overwrite)
    # remove original tree
    rmtree(full_dirname)


def create_tree(path: str, tree: TreeSpec, archives_leading_dir: bool =True, remove_existing: bool =False) -> None:
    """Given a list of tuples (name, load) create such a tree

    if load is a tuple itself -- that would create either a subtree or an archive
    with that content and place it into the tree if name ends with .tar.gz
    """
    lgr.log(5, "Creating a tree under %s", path)
    if not exists(path):
        os.makedirs(path)

    if isinstance(tree, dict):
        tree = list(tree.items())

    for file_, load in tree:
        if isinstance(file_, File):
            executable = file_.executable
            name = file_.name
        else:
            executable = False
            name = file_
        full_name = op.join(path, name)
        if remove_existing and lexists(full_name):
            rmtree(full_name, chmod_files=True)
        if isinstance(load, (tuple, list, dict)):
            if name.endswith('.tar.gz') or name.endswith('.tar') or name.endswith('.zip'):
                create_tree_archive(
                    path, name, load,
                    archives_leading_dir=archives_leading_dir)
            else:
                create_tree(
                    full_name, load,
                    archives_leading_dir=archives_leading_dir,
                    remove_existing=remove_existing)
        else:
            if full_name.endswith('.gz'):
                def open_func() -> IO[bytes]:
                    return gzip.open(full_name, "wb")  # type: ignore[return-value]
            elif full_name.split('.')[-1] in ('xz', 'lzma'):
                import lzma
                def open_func() -> IO[bytes]:
                    return lzma.open(full_name, "wb")
            else:
                def open_func() -> IO[bytes]:
                    return open(full_name, "wb")
            with open_func() as f:
                f.write(ensure_bytes(load, 'utf-8'))
        if executable:
            os.chmod(full_name, os.stat(full_name).st_mode | stat.S_IEXEC)


def get_suggestions_msg(values: Optional[str | Iterable[str]], known: str, sep: str="\n        ") -> str:
    """Return a formatted string with suggestions for values given the known ones
    """
    import difflib
    suggestions = []
    if not values:
        values = []
    elif isinstance(values, str):
        values = [values]
    for value in values:  # might not want to do it if we change presentation below
        suggestions += difflib.get_close_matches(value, known)
    suggestions = unique(suggestions)
    msg = "Did you mean any of these?"
    if suggestions:
        if '\n' in sep:
            # if separator includes new line - we add entire separator right away
            msg += sep
        else:
            msg += ' '
        return msg + "%s\n" % sep.join(suggestions)
    return ''


def bytes2human(n: int | float, format: str ='%(value).1f %(symbol)sB') -> str:
    """
    Convert n bytes into a human readable string based on format.
    symbols can be either "customary", "customary_ext", "iec" or "iec_ext",
    see: http://goo.gl/kTQMs

      >>> from datalad.utils import bytes2human
      >>> bytes2human(1)
      '1.0 B'
      >>> bytes2human(1024)
      '1.0 KB'
      >>> bytes2human(1048576)
      '1.0 MB'
      >>> bytes2human(1099511627776127398123789121)
      '909.5 YB'

      >>> bytes2human(10000, "%(value).1f %(symbol)s/sec")
      '9.8 K/sec'

      >>> # precision can be adjusted by playing with %f operator
      >>> bytes2human(10000, format="%(value).5f %(symbol)s")
      '9.76562 K'

    Taken from: http://goo.gl/kTQMs and subsequently simplified
    Original Author: Giampaolo Rodola' <g.rodola [AT] gmail [DOT] com>
    License: MIT
    """
    n = int(n)
    if n < 0:
        raise ValueError("n < 0")
    symbols = ('', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
    prefix = {}
    for i, s in enumerate(symbols[1:]):
        prefix[s] = 1 << (i + 1) * 10
    for symbol in reversed(symbols[1:]):
        if n >= prefix[symbol]:
            value = float(n) / prefix[symbol]
            return format % locals()
    return format % dict(symbol=symbols[0], value=n)


def quote_cmdlinearg(arg: str) -> str:
    """Perform platform-appropriate argument quoting"""
    # https://stackoverflow.com/a/15262019
    return '"{}"'.format(
        arg.replace('"', '""')
    ) if on_windows else shlex_quote(arg)


def guard_for_format(arg: str) -> str:
    """Replace { and } with {{ and }}

    To be used in cases if arg is not expected to have provided
    by user .format() placeholders, but 'arg' might become a part
    of a composite passed to .format(), e.g. via 'Run'
    """
    return arg.replace('{', '{{').replace('}', '}}')


def join_cmdline(args: Iterable[str]) -> str:
    """Join command line args into a string using quote_cmdlinearg
    """
    return ' '.join(map(quote_cmdlinearg, args))


def split_cmdline(s: str) -> list[str]:
    """Perform platform-appropriate command line splitting.

    Identical to `shlex.split()` on non-windows platforms.

    Modified from https://stackoverflow.com/a/35900070
    """
    if not on_windows:
        return shlex_split(s)

    # the rest is for windows
    RE_CMD_LEX = r'''"((?:""|\\["\\]|[^"])*)"?()|(\\\\(?=\\*")|\\")|(&&?|\|\|?|\d?>|[<])|([^\s"&|<>]+)|(\s+)|(.)'''

    args = []
    accu = None   # collects pieces of one arg
    for qs, qss, esc, pipe, word, white, fail in re.findall(RE_CMD_LEX, s):
        if word:
            pass   # most frequent
        elif esc:
            word = esc[1]
        elif white or pipe:
            if accu is not None:
                args.append(accu)
            if pipe:
                args.append(pipe)
            accu = None
            continue
        elif fail:
            raise ValueError("invalid or incomplete shell string")
        elif qs:
            word = qs.replace('\\"', '"').replace('\\\\', '\\')
            if platform == 0:
                word = word.replace('""', '"')
        else:
            word = qss   # may be even empty; must be last

        accu = (accu or '') + word

    if accu is not None:
        args.append(accu)

    return args


def get_wrapped_class(wrapped: Callable) -> type:
    """Determine the command class a wrapped __call__ belongs to"""
    mod = sys.modules[wrapped.__module__]
    command_class_name = wrapped.__qualname__.split('.')[-2]
    _func_class = mod.__dict__[command_class_name]
    lgr.debug("Determined class of decorated function: %s", _func_class)
    return _func_class


def _make_assure_kludge(fn: Callable[P, T]) -> Callable[P, T]:
    old_name = fn.__name__.replace("ensure", "assure")

    @wraps(fn)
    def compat_fn(*args: P.args, **kwargs: P.kwargs) -> T:
        warnings.warn(
            "{} is deprecated and will be removed in a future release. "
            "Use {} instead."
            .format(old_name, fn.__name__),
            DeprecationWarning)
        return fn(*args, **kwargs)

    compat_fn.__doc__ = ("Note: This function is deprecated. Use {} instead."
                         .format(fn.__name__))
    return compat_fn


assure_tuple_or_list = _make_assure_kludge(ensure_tuple_or_list)
assure_iter = _make_assure_kludge(ensure_iter)
assure_list = _make_assure_kludge(ensure_list)
assure_list_from_str = _make_assure_kludge(ensure_list_from_str)
assure_dict_from_str = _make_assure_kludge(ensure_dict_from_str)
assure_bytes = _make_assure_kludge(ensure_bytes)
assure_unicode = _make_assure_kludge(ensure_unicode)
assure_bool = _make_assure_kludge(ensure_bool)
assure_dir = _make_assure_kludge(ensure_dir)


lgr.log(5, "Done importing datalad.utils")


def check_symlink_capability(path: Path, target: Path) -> bool:
    """helper similar to datalad.tests.utils_pytest.has_symlink_capability

    However, for use in a datalad command context, we shouldn't
    assume to be able to write to tmpfile and also not import a whole lot from
    datalad's test machinery. Finally, we want to know, whether we can create a
    symlink at a specific location, not just somewhere. Therefore use
    arbitrary path to test-build a symlink and delete afterwards. Suitable
    location can therefore be determined by high lever code.

    Parameters
    ----------
    path: Path
    target: Path

    Returns
    -------
    bool
    """

    try:
        target.touch()
        path.symlink_to(target)
        return True
    except Exception:
        return False
    finally:
        if path.exists():
            path.unlink()
        if target.exists():
            target.unlink()


def obtain_write_permission(path: Path) -> Optional[int]:
    """Obtains write permission for `path` and returns previous mode if a
    change was actually made.

    Parameters
    ----------
    path: Path
      path to try to obtain write permission for

    Returns
    -------
    int or None
      previous mode of `path` as return by stat().st_mode if a change in
      permission was actually necessary, `None` otherwise.
    """

    mode = path.stat().st_mode
    # only IWRITE works on Windows, in principle
    if not mode & stat.S_IWRITE:
        path.chmod(mode | stat.S_IWRITE)
        return mode
    else:
        return None


@contextmanager
def ensure_write_permission(path: Path) -> Iterator[None]:
    """Context manager to get write permission on `path` and
    restore original mode afterwards.

    Parameters
    ----------
    path: Path
      path to the target file

    Raises
    ------
    PermissionError
       if write permission could not be obtained
    """

    restore = None
    try:
        restore = obtain_write_permission(path)
        yield
    finally:
        if restore is not None:
            try:
                path.chmod(restore)
            except FileNotFoundError:
                # If `path` was deleted within the context block, there's
                # nothing to do. Don't test exists(), though - asking for
                # forgiveness to save a call.
                pass
