# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import collections
import hashlib
import re
import six.moves.builtins as __builtin__
import time

import logging
import shutil
import os
import sys
import tempfile
import platform
import gc
import glob
import gzip
import string
import wrapt

from copy import copy as shallow_copy
from contextlib import contextmanager
from functools import wraps
from time import sleep
from inspect import getargspec
from itertools import tee

import os.path as op
from os.path import sep as dirsep
from os.path import commonprefix
from os.path import curdir, basename, exists, realpath, islink, join as opj
from os.path import isabs, normpath, expandvars, expanduser, abspath, sep
from os.path import isdir
from os.path import relpath
from os.path import stat
from os.path import dirname
from os.path import split as psplit
import posixpath


from six import PY2, text_type, binary_type, string_types

# from datalad.dochelpers import get_docstring_split
from datalad.consts import TIMESTAMP_FMT


if PY2:
    unicode_srctypes = string_types
else:
    unicode_srctypes = string_types + (bytes,)


lgr = logging.getLogger("datalad.utils")

lgr.log(5, "Importing datalad.utils")
#
# Some useful variables
#
platform_system = platform.system().lower()
on_windows = platform_system == 'windows'
on_osx = platform_system == 'darwin'
on_linux = platform_system == 'linux'
on_msys_tainted_paths = on_windows \
                        and 'MSYS_NO_PATHCONV' not in os.environ \
                        and os.environ.get('MSYSTEM', '')[:4] in ('MSYS', 'MING')
try:
    linux_distribution_name, linux_distribution_release \
        = platform.linux_distribution()[:2]
    on_debian_wheezy = on_linux \
                       and linux_distribution_name == 'debian' \
                       and linux_distribution_release.startswith('7.')
except:  # pragma: no cover
    # MIH: IndexError?
    on_debian_wheezy = False
    linux_distribution_name = linux_distribution_release = None

# Maximal length of cmdline string
# Query the system and use hardcoded "knowledge" if None
# probably   getconf ARG_MAX   might not be available
# The last one would be the most conservative/Windows
CMD_MAX_ARG_HARDCODED = 2097152 if on_linux else 262144 if on_osx else 32767
try:
    CMD_MAX_ARG = os.sysconf('SC_ARG_MAX')
    assert CMD_MAX_ARG > 0
    if sys.version_info[:2] == (3, 4):
        # workaround for some kind of a bug which comes up with python 3.4
        # see https://github.com/datalad/datalad/issues/3150
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


def get_func_kwargs_doc(func):
    """ Provides args for a function

    Parameters
    ----------
    func: str
      name of the function from which args are being requested

    Returns
    -------
    list
      of the args that a function takes in
    """
    return getargspec(func)[0]

    # TODO: format error message with descriptions of args
    # return [repr(dict(get_docstring_split(func)[1]).get(x)) for x in getargspec(func)[0]]


def any_re_search(regexes, value):
    """Return if any of regexes (list or str) searches succesfully for value"""
    for regex in assure_tuple_or_list(regexes):
        if re.search(regex, value):
            return True
    return False


def not_supported_on_windows(msg=None):
    """A little helper to be invoked to consistently fail whenever functionality is
    not supported (yet) on Windows
    """
    if on_windows:
        raise NotImplementedError("This functionality is not yet implemented for Windows OS"
                                  + (": %s" % msg if msg else ""))


def shortened_repr(value, l=30):
    try:
        if hasattr(value, '__repr__') and (value.__repr__ is not object.__repr__):
            value_repr = repr(value)
            if not value_repr.startswith('<') and len(value_repr) > l:
                value_repr = "<<%s...>>" % (value_repr[:l - 8])
            elif value_repr.startswith('<') and value_repr.endswith('>') and ' object at 0x':
                raise ValueError("I hate those useless long reprs")
        else:
            raise ValueError("gimme class")
    except Exception as e:
        value_repr = "<%s>" % value.__class__.__name__.split('.')[-1]
    return value_repr


def __auto_repr__(obj):
    attr_names = tuple()
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
        items.append("%s=%s" % (attr, shortened_repr(value)))

    return "%s(%s)" % (obj.__class__.__name__, ', '.join(items))


def auto_repr(cls):
    """Decorator for a class to assign it an automagic quick and dirty __repr__

    It uses public class attributes to prepare repr of a class

    Original idea: http://stackoverflow.com/a/27799004/1265472
    """

    cls.__repr__ = __auto_repr__
    return cls


def _is_stream_tty(stream):
    try:
        # TODO: check on windows if hasattr check would work correctly and
        # add value:
        return stream.isatty()
    except ValueError as exc:
        # Who knows why it is a ValueError, but let's try to be specific
        # If there is a problem with I/O - non-interactive, otherwise reraise
        if "I/O" in str(exc):
            return False
        raise


def is_interactive():
    """Return True if all in/outs are open and tty.

    Note that in a somewhat abnormal case where e.g. stdin is explicitly
    closed, and any operation on it would raise a
    `ValueError("I/O operation on closed file")` exception, this function
    would just return False, since the session cannot be used interactively.
    """
    return all(_is_stream_tty(s) for s in (sys.stdin, sys.stdout, sys.stderr))


def get_ipython_shell():
    """Detect if running within IPython and returns its `ip` (shell) object

    Returns None if not under ipython (no `get_ipython` function)
    """
    try:
        return get_ipython()
    except NameError:
        return None


def md5sum(filename):
    """Compute an MD5 sum for the given file
    """
    from datalad.support.digests import Digester
    return Digester(digests=['md5'])(filename)['md5']


def sorted_files(dout):
    """Return a (sorted) list of files under dout
    """
    return sorted(sum([[opj(r, f)[len(dout) + 1:] for f in files]
                       for r, d, files in os.walk(dout)
                       if not '.git' in r], []))

_VCS_REGEX = r'%s\.(?:git|gitattributes|svn|bzr|hg)(?:%s|$)' % (dirsep, dirsep)
_DATALAD_REGEX = r'%s\.(?:datalad)(?:%s|$)' % (dirsep, dirsep)


def find_files(regex, topdir=curdir, exclude=None, exclude_vcs=True, exclude_datalad=False, dirs=False):
    """Generator to find files matching regex

    Parameters
    ----------
    regex: basestring
    exclude: basestring, optional
      Matches to exclude
    exclude_vcs:
      If True, excludes commonly known VCS subdirectories.  If string, used
      as regex to exclude those files (regex: `%r`)
    exclude_datalad:
      If True, excludes files known to be datalad meta-data files (e.g. under
      .datalad/ subdirectory) (regex: `%r`)
    topdir: basestring, optional
      Directory where to search
    dirs: bool, optional
      Whether to match directories as well as files
    """

    for dirpath, dirnames, filenames in os.walk(topdir):
        names = (dirnames + filenames) if dirs else filenames
        # TODO: might want to uniformize on windows to use '/'
        paths = (opj(dirpath, name) for name in names)
        for path in filter(re.compile(regex).search, paths):
            path = path.rstrip(dirsep)
            if exclude and re.search(exclude, path):
                continue
            if exclude_vcs and re.search(_VCS_REGEX, path):
                continue
            if exclude_datalad and re.search(_DATALAD_REGEX, path):
                continue
            yield path
find_files.__doc__ %= (_VCS_REGEX, _DATALAD_REGEX)


def expandpath(path, force_absolute=True):
    """Expand all variables and user handles in a path.

    By default return an absolute path
    """
    path = expandvars(expanduser(path))
    if force_absolute:
        path = abspath(path)
    return path


def posix_relpath(path, start=None):
    """Behave like os.path.relpath, but always return POSIX paths...

    on any platform."""
    # join POSIX style
    return posixpath.join(
        # split and relpath native style
        # python2.7 ntpath implementation of relpath cannot handle start=None
        *psplit(
            relpath(path, start=start if start is not None else '')))


def is_explicit_path(path):
    """Return whether a path explicitly points to a location

    Any absolute path, or relative path starting with either '../' or
    './' is assumed to indicate a location on the filesystem. Any other
    path format is not considered explicit."""
    path = expandpath(path, force_absolute=False)
    return isabs(path) \
        or path.startswith(os.curdir + os.sep) \
        or path.startswith(os.pardir + os.sep)


def rotree(path, ro=True, chmod_files=True):
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
                fullf = opj(root, f)
                # might be the "broken" symlink which would fail to stat etc
                if exists(fullf):
                    chmod(fullf)
        chmod(root)


def rmtree(path, chmod_files='auto', children_only=False, *args, **kwargs):
    """To remove git-annex .git it is needed to make all files and directories writable again first

    Parameters
    ----------
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

    if children_only:
        if not os.path.isdir(path):
            raise ValueError("Can remove children only of directories")
        for p in os.listdir(path):
            rmtree(op.join(path, p))
        return
    if not (os.path.islink(path) or not os.path.isdir(path)):
        rotree(path, ro=False, chmod_files=chmod_files)
        _rmtree(path, *args, **kwargs)
    else:
        # just remove the symlink
        unlink(path)


def rmdir(path, *args, **kwargs):
    """os.rmdir with our optional checking for open files"""
    assert_no_open_files(path)
    os.rmdir(path)


def get_open_files(path, log_open=False):
    """Get open files under a path

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
    path = realpath(path)
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
    def assert_no_open_files(path):
        files = get_open_files(path, log_open=40)
        if _assert_no_open_files_cfg == 'assert':
            assert not files
        elif files:
            if _assert_no_open_files_cfg == 'pdb':
                import pdb
                pdb.set_trace()
            elif _assert_no_open_files_cfg == 'epdb':
                import epdb
                epdb.serve()
            pass
        # otherwise we would just issue that error message in the log
else:
    def assert_no_open_files(*args, **kwargs):
        pass


def rmtemp(f, *args, **kwargs):
    """Wrapper to centralize removing of temp files so we could keep them around

    It will not remove the temporary file/directory if DATALAD_TESTS_TEMP_KEEP
    environment variable is defined
    """
    if not os.environ.get('DATALAD_TESTS_TEMP_KEEP'):
        if not os.path.lexists(f):
            lgr.debug("Path %s does not exist, so can't be removed" % f)
            return
        lgr.log(5, "Removing temp file: %s" % f)
        # Can also be a directory
        if os.path.isdir(f):
            rmtree(f, *args, **kwargs)
        else:
            unlink(f)
    else:
        lgr.info("Keeping temp file: %s" % f)


def file_basename(name, return_ext=False):
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


def escape_filename(filename):
    """Surround filename in "" and escape " in the filename
    """
    filename = filename.replace('"', r'\"').replace('`', r'\`')
    filename = '"%s"' % filename
    return filename


def encode_filename(filename):
    """Encode unicode filename
    """
    if isinstance(filename, text_type):
        return filename.encode(sys.getfilesystemencoding())
    else:
        return filename


def decode_input(s):
    """Given input string/bytes, decode according to stdin codepage (or UTF-8)
    if not defined

    If fails -- issue warning and decode allowing for errors
    being replaced
    """
    if isinstance(s, text_type):
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


if on_windows:
    def lmtime(filepath, mtime):
        """Set mtime for files.  On Windows a merely adapter to os.utime
        """
        os.utime(filepath, (time.time(), mtime))
else:
    def lmtime(filepath, mtime):
        """Set mtime for files, while not de-referencing symlinks.

        To overcome absence of os.lutime

        Works only on linux and OSX ATM
        """
        from .cmd import Runner
        # convert mtime to format touch understands [[CC]YY]MMDDhhmm[.SS]
        smtime = time.strftime("%Y%m%d%H%M.%S", time.localtime(mtime))
        lgr.log(3, "Setting mtime for %s to %s == %s", filepath, mtime, smtime)
        Runner().run(['touch', '-h', '-t', '%s' % smtime, filepath])
        rfilepath = realpath(filepath)
        if islink(filepath) and exists(rfilepath):
            # trust noone - adjust also of the target file
            # since it seemed like downloading under OSX (was it using curl?)
            # didn't bother with timestamps
            lgr.log(3, "File is a symlink to %s Setting mtime for it to %s",
                    rfilepath, mtime)
            os.utime(rfilepath, (time.time(), mtime))
        # doesn't work on OSX
        # Runner().run(['touch', '-h', '-d', '@%s' % mtime, filepath])


def assure_tuple_or_list(obj):
    """Given an object, wrap into a tuple if not list or tuple
    """
    if isinstance(obj, (list, tuple)):
        return obj
    return (obj,)


def assure_iter(s, cls, copy=False, iterate=True):
    """Given not a list, would place it into a list. If None - empty list is returned

    Parameters
    ----------
    s: list or anything
    cls: class
      Which iterable class to assure
    copy: bool, optional
      If correct iterable is passed, it would generate its shallow copy
    iterate: bool, optional
      If it is not a list, but something iterable (but not a text_type)
      iterate over it.
    """

    if isinstance(s, cls):
        return s if not copy else shallow_copy(s)
    elif isinstance(s, text_type):
        return cls((s,))
    elif iterate and hasattr(s, '__iter__'):
        return cls(s)
    elif s is None:
        return cls()
    else:
        return cls((s,))


def assure_list(s, copy=False, iterate=True):
    """Given not a list, would place it into a list. If None - empty list is returned

    Parameters
    ----------
    s: list or anything
    copy: bool, optional
      If list is passed, it would generate a shallow copy of the list
    iterate: bool, optional
      If it is not a list, but something iterable (but not a text_type)
      iterate over it.
    """
    return assure_iter(s, list, copy=copy, iterate=iterate)


def assure_list_from_str(s, sep='\n'):
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


def assure_dict_from_str(s, **kwargs):
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

    out = {}
    for value_str in assure_list_from_str(s, **kwargs):
        if '=' not in value_str:
            raise ValueError("{} is not in key=value format".format(repr(value_str)))
        k, v = value_str.split('=', 1)
        if k in out:
            err = "key {} was already defined in {}, but new value {} was provided".format(k, out, v)
            raise ValueError(err)
        out[k] = v
    return out


def assure_bytes(s, encoding='utf-8'):
    """Convert/encode unicode to str (PY2) or bytes (PY3) if of 'text_type'

    Parameters
    ----------
    encoding: str, optional
      Encoding to use.  "utf-8" is the default
    """
    if not isinstance(s, text_type):
        return s
    return s.encode(encoding)


def assure_unicode(s, encoding=None, confidence=None):
    """Convert/decode to unicode (PY2) or str (PY3) if of 'binary_type'

    Parameters
    ----------
    encoding: str, optional
      Encoding to use.  If None, "utf-8" is tried, and then if not a valid
      UTF-8, encoding will be guessed
    confidence: float, optional
      A value between 0 and 1, so if guessing of encoding is of lower than
      specified confidence, ValueError is raised
    """
    if not isinstance(s, binary_type):
        return s
    if encoding is None:
        # Figure out encoding, defaulting to 'utf-8' which is our common
        # target in contemporary digital society
        try:
            return s.decode('utf-8')
        except UnicodeDecodeError as exc:
            from .dochelpers import exc_str
            lgr.debug("Failed to decode a string as utf-8: %s", exc_str(exc))
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
            return s.decode(denc)
        else:
            raise ValueError(
                "Could not decode value as utf-8, or to guess its encoding: %s"
                % repr(s)
            )
    else:
        return s.decode(encoding)


def assure_bool(s):
    """Convert value into boolean following convention for strings

    to recognize on,True,yes as True, off,False,no as False
    """
    if isinstance(s, string_types):
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


def as_unicode(val, cast_types=object):
    """Given an arbitrary value, would try to obtain unicode value of it
    
    For unicode it would return original value, for python2 str or python3
    bytes it would use assure_unicode, for None - an empty (unicode) string,
    and for any other type (see `cast_types`) - would apply the unicode 
    constructor.  If value is not an instance of `cast_types`, TypeError
    is thrown
    
    Parameters
    ----------
    cast_types: type
      Which types to cast to unicode by providing to constructor
    """
    if val is None:
        return u''
    elif isinstance(val, text_type):
        return val
    elif isinstance(val, unicode_srctypes):
        return assure_unicode(val)
    elif isinstance(val, cast_types):
        return text_type(val)
    else:
        raise TypeError(
            "Value %r is not of any of known or provided %s types"
            % (val, cast_types))


def unique(seq, key=None, reverse=False):
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
    seen = set()
    seen_add = seen.add

    trans = reversed if reverse else lambda x: x

    if not key:
        out = [x for x in trans(seq) if not (x in seen or seen_add(x))]
    else:
        # OPT: could be optimized, since key is called twice, but for our cases
        # should be just as fine
        out = [x for x in trans(seq) if not (key(x) in seen or seen_add(key(x)))]

    return out[::-1] if reverse else out


def all_same(items):
    """Quick check if all items are the same.

    Identical to a check like len(set(items)) == 1 but
    should be more efficient while working on generators, since would
    return False as soon as any difference detected thus possibly avoiding
    unnecessary evaluations
    """
    first = True
    first_item = None
    for item in items:
        if first:
            first = False
            first_item = item
        else:
            if item != first_item:
                return False
    # So we return False if was empty
    return not first


def map_items(func, v):
    """A helper to apply `func` to all elements (keys and values) within dict

    No type checking of values passed to func is done, so `func`
    should be resilient to values which it should not handle

    Initial usecase - apply_recursive(url_fragment, assure_unicode)
    """
    # map all elements within item
    return v.__class__(
        item.__class__(map(func, item))
        for item in v.items()
    )


def partition(items, predicate=bool):
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


def generate_chunks(container, size):
    """Given a container, generate chunks from it with size up to `size`
    """
    # There could be a "smarter" solution but I think this would suffice
    assert size > 0,  "Size should be non-0 positive"
    while container:
        yield container[:size]
        container = container[size:]


def generate_file_chunks(files, cmd=None):
    """Given a list of files, generate chunks of them to avoid exceding cmdline length

    Parameters
    ----------
    files: list of str
    cmd: str or list of str, optional
      Command to account for as well
    """
    files = assure_list(files)
    cmd = assure_list(cmd)

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

def saved_generator(gen):
    """Given a generator returns two generators, where 2nd one just replays

    So the first one would be going through the generated items and 2nd one
    would be yielding saved items
    """
    saved = []

    def gen1():
        for x in gen:  # iterating over original generator
            saved.append(x)
            yield x

    def gen2():
        for x in saved:  # yielding saved entries
            yield x

    return gen1(), gen2()


#
# Decorators
#
def better_wraps(to_be_wrapped):
    """Decorator to replace `functools.wraps`

    This is based on `wrapt` instead of `functools` and in opposition to `wraps`
    preserves the correct signature of the decorated function.
    It is written with the intention to replace the use of `wraps` without any
    need to rewrite the actual decorators.
    """

    @wrapt.decorator(adapter=to_be_wrapped)
    def intermediator(to_be_wrapper, instance, args, kwargs):
        return to_be_wrapper(*args, **kwargs)

    return intermediator


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

        is_decorating = not kwargs and len(args) == 1 and isinstance(args[0], collections.Callable)
        if is_decorating:
            f = args[0]
            args = []
            return dec(f)
        else:
            return dec

    return wrapper


# TODO: just provide decorators for tempfile.mk* functions. This is ugly!
def get_tempfile_kwargs(tkwargs=None, prefix="", wrapped=None):
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

    directory = os.environ.get('DATALAD_TESTS_TEMP_DIR')
    if directory and 'dir' not in tkwargs_:
        tkwargs_['dir'] = directory

    return tkwargs_


@optional_args
def line_profile(func):
    """Q&D helper to line profile the function and spit out stats
    """
    import line_profiler
    prof = line_profiler.LineProfiler()

    @wraps(func)
    def newfunc(*args, **kwargs):
        try:
            pfunc = prof(func)
            return pfunc(*args, **kwargs)
        finally:
            prof.print_stats()
    return newfunc


# Borrowed from duecredit to wrap duecredit-handling to guarantee failsafe
def never_fail(f):
    """Assure that function never fails -- all exceptions are caught

    Returns `None` if function fails internally.
    """
    @wraps(f)
    def wrapped_func(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            lgr.warning(
                "DataLad internal failure while running %s: %r. "
                "Please report at https://github.com/datalad/datalad/issues"
                % (f, e)
            )

    if os.environ.get('DATALAD_ALLOW_FAIL', False):
        return f
    else:
        return wrapped_func


#
# Context Managers
#


@contextmanager
def nothing_cm():
    """Just a dummy cm to programmically switch context managers"""
    yield


@contextmanager
def swallow_outputs():
    """Context manager to help consuming both stdout and stderr, and print()

    stdout is available as cm.out and stderr as cm.err whenever cm is the
    yielded context manager.
    Internally uses temporary files to guarantee absent side-effects of swallowing
    into StringIO which lacks .fileno.

    print mocking is necessary for some uses where sys.stdout was already bound
    to original sys.stdout, thus mocking it later had no effect. Overriding
    print function had desired effect
    """

    class StringIOAdapter(object):
        """Little adapter to help getting out/err values
        """
        def __init__(self):
            kw = get_tempfile_kwargs({}, prefix="outputs")

            self._out = open(tempfile.mktemp(**kw), 'w')
            self._err = open(tempfile.mktemp(**kw), 'w')

        def _read(self, h):
            with open(h.name) as f:
                return f.read()

        @property
        def out(self):
            if not self._out.closed:
                self._out.flush()
            return self._read(self._out)

        @property
        def err(self):
            if not self._err.closed:
                self._err.flush()
            return self._read(self._err)

        @property
        def handles(self):
            return self._out, self._err

        def cleanup(self):
            self._out.close()
            self._err.close()
            out_name = self._out.name
            err_name = self._err.name
            del self._out
            del self._err
            gc.collect()
            rmtemp(out_name)
            rmtemp(err_name)

    def fake_print(*args, **kwargs):
        sep = kwargs.pop('sep', ' ')
        end = kwargs.pop('end', '\n')
        file = kwargs.pop('file', sys.stdout)

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
    oldprint = getattr(__builtin__, 'print')
    oldout, olderr = sys.stdout, sys.stderr
    olduiout = ui.out
    adapter = StringIOAdapter()

    try:
        sys.stdout, sys.stderr = adapter.handles
        ui.out = adapter.handles[0]
        setattr(__builtin__, 'print', fake_print)

        yield adapter
    finally:
        sys.stdout, sys.stderr, ui.out = oldout, olderr, olduiout
        setattr(__builtin__, 'print',  oldprint)
        adapter.cleanup()


@contextmanager
def swallow_logs(new_level=None, file_=None, name='datalad'):
    """Context manager to consume all logs.

    """
    lgr = logging.getLogger(name)

    # Keep old settings
    old_level = lgr.level
    old_handlers = lgr.handlers

    # Let's log everything into a string
    # TODO: generalize with the one for swallow_outputs
    class StringIOAdapter(object):
        """Little adapter to help getting out values

        And to stay consistent with how swallow_outputs behaves
        """
        def __init__(self):
            if file_ is None:
                kw = get_tempfile_kwargs({}, prefix="logs")
                out_file = tempfile.mktemp(**kw)
            else:
                out_file = file_
            # PY3 requires clearly one or another.  race condition possible
            self._out = open(out_file, 'a')
            self._final_out = None

        def _read(self, h):
            with open(h.name) as f:
                return f.read()

        @property
        def out(self):
            if self._final_out is not None:
                # we closed and cleaned up already
                return self._final_out
            else:
                self._out.flush()
                return self._read(self._out)

        @property
        def lines(self):
            return self.out.split('\n')

        @property
        def handle(self):
            return self._out

        def cleanup(self):
            # store for access while object exists
            self._final_out = self.out
            self._out.close()
            out_name = self._out.name
            del self._out
            gc.collect()
            if not file_:
                rmtemp(out_name)

        def assert_logged(self, msg=None, level=None, regex=True, **kwargs):
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
            from datalad.tests.utils import assert_re_in
            from datalad.tests.utils import assert_in

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

    adapter = StringIOAdapter()
    # TODO: it does store messages but without any formatting, i.e. even without
    # date/time prefix etc.  IMHO it should preserve formatting in case if file_ is
    # set
    swallow_handler = logging.StreamHandler(adapter.handle)
    # we want to log levelname so we could test against it
    swallow_handler.setFormatter(
        logging.Formatter('[%(levelname)s] %(message)s'))
    # Inherit filters
    from datalad.log import ProgressHandler
    swallow_handler.filters = sum([h.filters for h in old_handlers
                                   if not isinstance(h, ProgressHandler)],
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
        lgr.handlers, lgr.level = old_handlers, old_level
        adapter.cleanup()


# TODO: May be melt in with swallow_logs at some point:
@contextmanager
def disable_logger(logger=None):
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
        def filter(self, record):
            return 0

    if logger is None:
        # default: all of datalad's logging:
        logger = logging.getLogger('datalad')

    filter_ = NullFilter(logger.name)
    [h.addFilter(filter_) for h in logger.handlers]

    try:
        yield logger
    finally:
        [h.removeFilter(filter_) for h in logger.handlers]


#
# Additional handlers
#
_sys_excepthook = sys.excepthook  # Just in case we ever need original one


def setup_exceptionhook(ipython=False):
    """Overloads default sys.excepthook with our exceptionhook handler.

       If interactive, our exceptionhook handler will invoke
       pdb.post_mortem; if not interactive, then invokes default handler.
    """

    def _datalad_pdb_excepthook(type, value, tb):
        import traceback
        traceback.print_exception(type, value, tb)
        print()
        if is_interactive():
            import pdb
            pdb.post_mortem(tb)

    if ipython:
        from IPython.core import ultratb
        sys.excepthook = ultratb.FormattedTB(mode='Verbose',
                                             # color_scheme='Linux',
                                             call_pdb=is_interactive())
    else:
        sys.excepthook = _datalad_pdb_excepthook


def assure_dir(*args):
    """Make sure directory exists.

    Joins the list of arguments to an os-specific path to the desired
    directory and creates it, if it not exists yet.
    """
    dirname = opj(*args)
    if not exists(dirname):
        os.makedirs(dirname)
    return dirname


def updated(d, update):
    """Return a copy of the input with the 'update'

    Primarily for updating dictionaries
    """
    d = d.copy()
    d.update(update)
    return d


_pwd_mode = None


def _switch_to_getcwd(msg, *args):
    global _pwd_mode
    _pwd_mode = 'cwd'
    lgr.warning(
        msg + ". From now on will be returning os.getcwd(). Directory"
               " symlinks in the paths will be resolved",
        *args
    )
    # TODO:  we might want to mitigate by going through all flywheighted
    # repos and tuning up their .paths to be resolved?


def getpwd():
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
            pwd_real = op.realpath(pwd)
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
            return cwd  # Must not happen, but may be someone
                        # evil purges PWD from environ?
    else:
        raise RuntimeError(
            "Must have not got here. "
            "pwd_mode must be either cwd or PWD. And it is now %r" % (_pwd_mode,)
        )


class chpwd(object):
    """Wrapper around os.chdir which also adjusts environ['PWD']

    The reason is that otherwise PWD is simply inherited from the shell
    and we have no ability to assess directory path without dereferencing
    symlinks.

    If used as a context manager it allows to temporarily change directory
    to the given path
    """
    def __init__(self, path, mkdir=False, logsuffix=''):

        if path:
            pwd = getpwd()
            self._prev_pwd = pwd
        else:
            self._prev_pwd = None
            return

        if not isabs(path):
            path = normpath(opj(pwd, path))
        if not os.path.exists(path) and mkdir:
            self._mkdir = True
            os.mkdir(path)
        else:
            self._mkdir = False
        lgr.debug("chdir %r -> %r %s", self._prev_pwd, path, logsuffix)
        os.chdir(path)  # for grep people -- ok, to chdir here!
        os.environ['PWD'] = path

    def __enter__(self):
        # nothing more to do really, chdir was in the constructor
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._prev_pwd:
            # Need to use self.__class__ so this instance, if the entire
            # thing mocked during the test, still would use correct chpwd
            self.__class__(self._prev_pwd, logsuffix="(coming back)")


def dlabspath(path, norm=False):
    """Symlinks-in-the-cwd aware abspath

    os.path.abspath relies on os.getcwd() which would not know about symlinks
    in the path

    TODO: we might want to norm=True by default to match behavior of
    os .path.abspath?
    """
    if not isabs(path):
        # if not absolute -- relative to pwd
        path = opj(getpwd(), path)
    return normpath(path) if norm else path


def with_pathsep(path):
    """Little helper to guarantee that path ends with /"""
    return path + sep if not path.endswith(sep) else path


def get_path_prefix(path, pwd=None):
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


def _get_normalized_paths(path, prefix):
    if isabs(path) != isabs(prefix):
        raise ValueError("Both paths must either be absolute or relative. "
                         "Got %r and %r" % (path, prefix))
    path = with_pathsep(path)
    prefix = with_pathsep(prefix)
    return path, prefix


def path_startswith(path, prefix):
    """Return True if path starts with prefix path

    Parameters
    ----------
    path: str
    prefix: str
    """
    path, prefix = _get_normalized_paths(path, prefix)
    return path.startswith(prefix)


def path_is_subpath(path, prefix):
    """Return True if path is a subpath of prefix

    It will return False if path == prefix.

    Parameters
    ----------
    path: str
    prefix: str
    """
    path, prefix = _get_normalized_paths(path, prefix)
    return (len(prefix) < len(path)) and path.startswith(prefix)


def knows_annex(path):
    """Returns whether at a given path there is information about an annex

    It is just a thin wrapper around GitRepo.is_with_annex() classmethod
    which also checks for `path` to exist first.

    This includes actually present annexes, but also uninitialized ones, or
    even the presence of a remote annex branch.
    """
    from os.path import exists
    if not exists(path):
        lgr.debug("No annex: test path {0} doesn't exist".format(path))
        return False
    from datalad.support.gitrepo import GitRepo
    return GitRepo(path, init=False, create=False).is_with_annex()


@contextmanager
def make_tempfile(content=None, wrapped=None, **tkwargs):
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
    mkdir = tkwargs_.pop('mkdir', False)

    filename = {False: tempfile.mktemp,
                True: tempfile.mkdtemp}[mkdir](**tkwargs_)
    filename = realpath(filename)

    if content:
        with open(filename, 'w' + ('b' if isinstance(content, binary_type) else '')) as f:
            f.write(content)

    if __debug__:
        # TODO mkdir
        lgr.debug('Created temporary thing named %s"' % filename)
    try:
        yield filename
    finally:
        # glob here for all files with the same name (-suffix)
        # would be useful whenever we requested .img filename,
        # and function creates .hdr as well
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


def _path_(*p):
    """Given a path in POSIX" notation, regenerate one in native to the env one"""
    if on_windows:
        return opj(*map(lambda x: opj(*x.split('/')), p))
    else:
        # Assume that all others as POSIX compliant so nothing to be done
        return opj(*p)


def get_timestamp_suffix(time_=None, prefix='-'):
    """Return a time stamp (full date and time up to second)

    primarily to be used for generation of log files names
    """
    args = []
    if time_ is not None:
        if isinstance(time_, int):
            time_ = time.gmtime(time_)
        args.append(time_)
    return time.strftime(prefix + TIMESTAMP_FMT, *args)


def get_logfilename(dspath, cmd='datalad'):
    """Return a filename to use for logging under a dataset/repository

    directory would be created if doesn't exist, but dspath must exist
    and be a directory
    """
    assert(exists(dspath))
    assert(isdir(dspath))
    ds_logdir = assure_dir(dspath, '.git', 'datalad', 'logs')  # TODO: use WEB_META_LOG whenever #789 merged
    return opj(ds_logdir, 'crawl-%s.log' % get_timestamp_suffix())


def get_trace(edges, start, end, trace=None):
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


def get_dataset_root(path):
    """Return the root of an existent dataset containing a given path

    The root path is returned in the same absolute or relative form
    as the input argument. If no associated dataset exists, or the
    input path doesn't exist, None is returned.
    """
    suffix = '.git'
    if not isdir(path):
        path = dirname(path)
    apath = abspath(path)
    # while we can still go up
    while psplit(apath)[1]:
        if exists(opj(path, suffix)):
            return path
        # new test path in the format we got it
        path = normpath(opj(path, os.pardir))
        # no luck, next round
        apath = abspath(path)
    return None


def get_dataset_pwds(dataset):
    """Return the current directory for the dataset.

    Parameters
    ----------
    dataset : Dataset

    Returns
    -------
    A tuple, where the first item is the absolute path of the pwd and the
    second is the pwd relative to the dataset's path.
    """
    if dataset:
        pwd = dataset.path
        rel_pwd = curdir
    else:
        # act on the whole dataset if nothing else was specified

        # Follow our generic semantic that if dataset is specified,
        # paths are relative to it, if not -- relative to pwd
        pwd = getpwd()
        # Pass pwd to get_dataset_root instead of os.path.curdir to handle
        # repos whose leading paths have a symlinked directory (see the
        # TMPDIR="/var/tmp/sym link" test case).
        dataset = get_dataset_root(pwd)

        if dataset:
            rel_pwd = relpath(pwd, dataset)
        else:
            rel_pwd = pwd  # and leave handling to caller
    return pwd, rel_pwd


# ATM used in datalad_crawler extension, so do not remove yet
def try_multiple(ntrials, exception, base, f, *args, **kwargs):
    """Call f multiple times making exponentially growing delay between the calls"""
    from .dochelpers import exc_str
    for trial in range(1, ntrials+1):
        try:
            return f(*args, **kwargs)
        except exception as exc:
            if trial == ntrials:
                raise  # just reraise on the last trial
            t = base ** trial
            lgr.warning("Caught %s on trial #%d. Sleeping %f and retrying",
                        exc_str(exc), trial, t)
            sleep(t)


@optional_args
def try_multiple_dec(f, ntrials=None, duration=0.1, exceptions=None, increment_type=None):
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

    """
    from .dochelpers import exc_str
    if not exceptions:
        exceptions = (OSError, WindowsError, PermissionError) \
            if on_windows else OSError
    if not ntrials:
        # Life goes fast on proper systems, no need to delay it much
        ntrials = 50 if on_windows else 3

    assert increment_type in {None, 'exponential'}

    @wraps(f)
    def wrapped(*args, **kwargs):
        t = duration
        for trial in range(ntrials):
            try:
                return f(*args, **kwargs)
            except exceptions as exc:
                if increment_type == 'exponential':
                    t = duration ** (trial + 1)
                lgr.log(
                    5,
                    "Caught %s on trial #%d. Sleeping %f and retrying",
                    exc_str(exc), trial, t)
                if trial < ntrials - 1:
                    sleep(t)
                else:
                    raise

    return wrapped


@try_multiple_dec
def unlink(f):
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
def _rmtree(*args, **kwargs):
    """Just a helper to decorate shutil.rmtree.

    rmtree defined above does more and ideally should not itself be decorated
    since a recursive definition and does checks for open files inside etc -
    might be too runtime expensive
    """
    return shutil.rmtree(*args, **kwargs)


def slash_join(base, extension):
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


def safe_print(s):
    """Print with protection against UTF-8 encoding errors"""
    # A little bit of dance to be able to test this code
    print_f = getattr(__builtin__, "print")
    try:
        print_f(s)
    except UnicodeEncodeError:
        # failed to encode so let's do encoding while ignoring errors
        # to print at least something
        # explicit `or ascii` since somehow on buildbot it seemed to return None
        s = s.encode(getattr(sys.stdout, 'encoding', 'ascii') or 'ascii', errors='ignore') \
            if hasattr(s, 'encode') else s
        print_f(s.decode())

#
# IO Helpers
#

def open_r_encdetect(fname, readahead=1000):
    """Return a file object in read mode with auto-detected encoding

    This is helpful when dealing with files of unknown encoding.

    Parameters
    ----------
    readahead: int, optional
      How many bytes to read for guessing the encoding type.  If
      negative - full file will be read
    """
    from chardet import detect
    import io
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


def read_csv_lines(fname, dialect=None, readahead=16384, **kwargs):
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
    if dialect is None:
        with open(fname) as tsvfile:
            # add robustness, use a sniffer
            try:
                dialect = csv.Sniffer().sniff(tsvfile.read(readahead))
            except Exception as exc:
                from .dochelpers import exc_str
                lgr.warning(
                    'Could not determine file-format, assuming TSV: %s',
                    exc_str(exc)
                )
                dialect = 'excel-tab'

    kw = {} if PY2 else dict(encoding='utf-8')
    with open(fname, 'rb' if PY2 else 'r', **kw) as tsvfile:
        # csv.py doesn't do Unicode; encode temporarily as UTF-8:
        csv_reader = csv.reader(
            tsvfile,
            dialect=dialect,
            **kwargs
        )
        header = None
        for row in csv_reader:
            # decode UTF-8 back to Unicode, cell by cell:
            row_unicode = map(assure_unicode, row)
            if header is None:
                header = list(row_unicode)
            else:
                yield dict(zip(header, row_unicode))


def import_modules(modnames, pkg, msg="Failed to import {module}", log=lgr.debug):
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
            from datalad.dochelpers import exc_str
            log((msg + ': {exception}').format(
                module=modname, package=pkg, exception=exc_str(exc)))
    return mods_loaded


def import_module_from_file(modpath, pkg=None, log=lgr.debug):
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
            mod = import_module(relmodpath, pkg.__name__)
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
        from datalad.dochelpers import exc_str
        raise RuntimeError(
            "Failed to import module from %s: %s" % (modpath, exc_str(e)))

    return mod


def get_encoding_info():
    """Return a dictionary with various encoding/locale information"""
    import sys, locale
    from collections import OrderedDict
    return OrderedDict([
        ('default', sys.getdefaultencoding()),
        ('filesystem', sys.getfilesystemencoding()),
        ('locale.prefered', locale.getpreferredencoding()),
    ])


def get_envvars_info():
    from collections import OrderedDict
    envs = []
    for var, val in os.environ.items():
        if (
                var.startswith('PYTHON') or
                var.startswith('LC_') or
                var.startswith('GIT_') or
                var in ('LANG', 'LANGUAGE', 'PATH')
        ):
            envs.append((var, val))
    return OrderedDict(envs)


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

    def __init__(self, separator=" ", element_formatter=string.Formatter(),
                 *args, **kwargs):
        self.separator = separator
        self.element_formatter = element_formatter

    def format_element(self, elem, format_spec):
        """Format a single element

        For sequences, this is called once for each element in a
        sequence. For anything else, it is called on the entire
        object. It is intended to be overridden in subclases.
        """
        return self.element_formatter.format_field(elem, format_spec)

    def format_field(self, value, format_spec):
        if isinstance(value, (list, tuple, set, frozenset)):
            return self.separator.join(self.format_element(v, format_spec)
                                       for v in value)
        else:
            return self.format_element(value, format_spec)


# TODO: eventually we might want to make use of attr module
class File(object):
    """Helper for a file entry in the create_tree/@with_tree

    It allows to define additional settings for entries
    """
    def __init__(self, name, executable=False):
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

    def __str__(self):
        return self.name


def create_tree_archive(path, name, load, overwrite=False, archives_leading_dir=True):
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
        compress_files(list(map(op.basename, glob.glob(opj(full_dirname, '*')))),
                       opj(op.pardir, name),
                       path=op.join(path, dirname),
                       overwrite=overwrite)
    # remove original tree
    rmtree(full_dirname)


def create_tree(path, tree, archives_leading_dir=True, remove_existing=False):
    """Given a list of tuples (name, load) create such a tree

    if load is a tuple itself -- that would create either a subtree or an archive
    with that content and place it into the tree if name ends with .tar.gz
    """
    lgr.log(5, "Creating a tree under %s", path)
    if not op.exists(path):
        os.makedirs(path)

    if isinstance(tree, dict):
        tree = tree.items()

    for file_, load in tree:
        if isinstance(file_, File):
            executable = file_.executable
            name = file_.name
        else:
            executable = False
            name = file_
        full_name = op.join(path, name)
        if remove_existing and op.lexists(full_name):
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
            open_func = open
            if full_name.endswith('.gz'):
                open_func = gzip.open
            with open_func(full_name, "wb") as f:
                f.write(assure_bytes(load, 'utf-8'))
        if executable:
            os.chmod(full_name, os.stat(full_name).st_mode | stat.S_IEXEC)


def get_suggestions_msg(values, known, sep="\n        "):
    """Return a formatted string with suggestions for values given the known ones
    """
    import difflib
    suggestions = []
    for value in assure_list(values):  # might not want to do it if we change presentation below
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



lgr.log(5, "Done importing datalad.utils")
