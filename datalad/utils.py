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
import wrapt

from contextlib import contextmanager
from functools import wraps
from time import sleep
from inspect import getargspec

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


from six import text_type, binary_type, string_types

# from datalad.dochelpers import get_docstring_split
from datalad.consts import TIMESTAMP_FMT

lgr = logging.getLogger("datalad.utils")

lgr.log(5, "Importing datalad.utils")
#
# Some useful variables
#
platform_system = platform.system().lower()
on_windows = platform_system == 'windows'
on_osx = platform_system == 'darwin'
on_linux = platform_system == 'linux'
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


def is_interactive():
    """Return True if all in/outs are tty"""
    # TODO: check on windows if hasattr check would work correctly and add value:
    #
    return sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()


def md5sum(filename):
    with open(filename, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def sorted_files(dout):
    """Return a (sorted) list of files under dout
    """
    return sorted(sum([[opj(r, f)[len(dout) + 1:] for f in files]
                       for r, d, files in os.walk(dout)
                       if not '.git' in r], []))

_VCS_REGEX = '%s\.(?:git|gitattributes|svn|bzr|hg)(?:%s|$)' % (dirsep, dirsep)
_DATALAD_REGEX = '%s\.(?:datalad)(?:%s|$)' % (dirsep, dirsep)


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
      Either to match directories as well as files
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
      Either to make it R/O (default) or RW
    chmod_files : bool, optional
      Either to operate also on files (not just directories)
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


def rmtree(path, chmod_files='auto', *args, **kwargs):
    """To remove git-annex .git it is needed to make all files and directories writable again first

    Parameters
    ----------
    chmod_files : string or bool, optional
       Either to make files writable also before removal.  Usually it is just
       a matter of directories to have write permissions.
       If 'auto' it would chmod files on windows by default
    `*args` :
    `**kwargs` :
       Passed into shutil.rmtree call
    """
    # Give W permissions back only to directories, no need to bother with files
    if chmod_files == 'auto':
        chmod_files = on_windows

    if not (os.path.islink(path) or not os.path.isdir(path)):
        rotree(path, ro=False, chmod_files=chmod_files)
        shutil.rmtree(path, *args, **kwargs)
    else:
        # just remove the symlink
        os.unlink(path)


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
            for i in range(10):
                try:
                    os.unlink(f)
                except OSError as e:
                    if i < 9:
                        sleep(0.1)
                        continue
                    else:
                        raise
                break
    else:
        lgr.info("Keeping temp file: %s" % f)


def file_basename(name, return_ext=False):
    """
    Strips up to 2 extensions of length up to 4 characters and starting with alpha
    not a digit, so we could get rid of .tar.gz etc
    """
    bname = basename(name)
    fbname = re.sub('(\.[a-zA-Z_]\S{1,4}){0,2}$', '', bname)
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

    if isinstance(s, list):
        return s if not copy else s[:]
    elif isinstance(s, text_type):
        return [s]
    elif iterate and hasattr(s, '__iter__'):
        return list(s)
    elif s is None:
        return []
    else:
        return [s]


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


def assure_unicode(s, encoding='utf-8'):
    """Convert/decode to unicode (PY2) or str (PY3) if of 'binary_type'"""
    return s.decode(encoding) if isinstance(s, binary_type) else s

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


def unique(seq, key=None):
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
    """
    seen = set()
    seen_add = seen.add
    if not key:
        return [x for x in seq if not (x in seen or seen_add(x))]
    else:
        # OPT: could be optimized, since key is called twice, but for our cases
        # should be just as fine
        return [x for x in seq if not (key(x) in seen or seen_add(key(x)))]


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
            self._out.flush()
            return self._read(self._out)

        @property
        def err(self):
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
            sys.stdout.write(sep.join(args) + end)
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
            """Provide assertion on either a msg was logged at a given level

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
                match = '\[%s\] ' % level if level else "\[\S+\] "
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
    swallow_handler.filters = sum([h.filters for h in old_handlers], [])
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


def getpwd():
    """Try to return a CWD without dereferencing possible symlinks

    If no PWD found in the env, output of getcwd() is returned
    """
    try:
        return os.environ['PWD']
    except KeyError:
        return os.getcwd()


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
    if not isabs(path):
        # if not absolute -- relative to pwd
        path = opj(getpwd(), path)
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
        return opj(*map(lambda x: x.split('/'), p))
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
    suffix = os.sep + opj('.git', 'objects')
    if not isdir(path):
        path = dirname(path)
    apath = abspath(path)
    # while we can still go up
    while psplit(apath)[1]:
        if exists(path + suffix):
            return path
        # new test path in the format we got it
        path = normpath(opj(path, os.pardir))
        # no luck, next round
        apath = abspath(path)
    return None


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


lgr.log(5, "Done importing datalad.utils")

