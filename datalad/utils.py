# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import __builtin__

import logging
import shutil, stat, os, sys
import tempfile
import platform

from functools import wraps
from os.path import exists, join as opj

lgr = logging.getLogger("datalad.utils")

#
# Some useful variables
#
on_windows = platform.system() == 'Windows'
on_osx = platform.system() == 'Darwin'
on_linux = platform.system() == 'Linux'
try:
    on_debian_wheezy = platform.system() == 'Linux' \
                and platform.linux_distribution()[0] == 'debian' \
                and platform.linux_distribution()[1].startswith('7.')
except:  # pragma: no cover
    on_debian_wheezy = False

#
# Little helpers
#

def is_interactive():
    """Return True if all in/outs are tty"""
    # TODO: check on windows if hasattr check would work correctly and add value:
    #
    return sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()

import hashlib
def md5sum(filename):
    with open(filename) as f:
        return hashlib.md5(f.read()).hexdigest()


def sorted_files(dout):
    """Return a (sorted) list of files under dout
    """
    return sorted(sum([[opj(r, f)[len(dout)+1:] for f in files]
                       for r,d,files in os.walk(dout)
                       if not '.git' in r], []))

#### windows workaround ###
# TODO: There should be a better way
def get_local_file_url(fname):
    """Return OS specific URL pointing to a local file

    Parameters
    ----------
    fname : string
        Full filename
    """
    if on_windows:
        fname_rep = fname.replace('\\', '/')
        furl = "file:///%s" % fname_rep
        lgr.debug("Replaced '\\' in file\'s url: %s" % furl)
    else:
        furl = "file://%s" % fname
    return furl


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

    for root, dirs, files in os.walk(path):
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
    *args, **kwargs :
       Passed into shutil.rmtree call
    """
    # Give W permissions back only to directories, no need to bother with files
    if chmod_files == 'auto':
        chmod_files = on_windows
    rotree(path, ro=False, chmod_files=chmod_files)
    shutil.rmtree(path, *args, **kwargs)


def rmtemp(f, *args, **kwargs):
    """Wrapper to centralize removing of temp files so we could keep them around

    It will not remove the temporary file/directory if DATALAD_TESTS_KEEPTEMP
    environment variable is defined
    """
    if not os.environ.get('DATALAD_TESTS_KEEPTEMP'):
        lgr.log(5, "Removing temp file: %s" % f)
        # Can also be a directory
        if os.path.isdir(f):
            rmtree(f, *args, **kwargs)
        else:
            os.unlink(f)
    else:
        lgr.info("Keeping temp file: %s" % f)


#
# Decorators
#

# Borrowed from pandas
# Copyright: 2011-2014, Lambda Foundry, Inc. and PyData Development Team
# Licese: BSD-3
def optional_args(decorator):
    """allows a decorator to take optional positional and keyword arguments.
        Assumes that taking a single, callable, positional argument means that
        it is decorating a function, i.e. something like this::

            @my_decorator
            def function(): pass

        Calls decorator with decorator(f, *args, **kwargs)"""

    @wraps(decorator)
    def wrapper(*args, **kwargs):
        def dec(f):
            return decorator(f, *args, **kwargs)

        is_decorating = not kwargs and len(args) == 1 and callable(args[0])
        if is_decorating:
            f = args[0]
            args = []
            return dec(f)
        else:
            return dec

    return wrapper


# TODO: just provide decorators for tempfile.mk* functions. This is ugly!
def get_tempfile_kwargs(tkwargs, prefix="", wrapped=None):
    """Updates kwargs to be passed to tempfile. calls depending on env vars
    """
    # operate on a copy of tkwargs to avoid any side-effects
    tkwargs_ = tkwargs.copy()

    # TODO: don't remember why I had this one originally
    # if len(targs)<2 and \
    if not 'prefix' in tkwargs_:
        tkwargs_['prefix'] = '_'.join(
            ['datalad_temp'] +
            ([prefix] if prefix else []) +
            ([''] if (on_windows or not wrapped)
                  else [wrapped.func_name]))

    directory = os.environ.get('DATALAD_TESTS_TEMPDIR')
    if directory and 'dir' not in tkwargs_:
        tkwargs_['dir'] = directory

    return tkwargs_


#
# Context Managers
#

from contextlib import contextmanager

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
            rmtemp(self._out.name)
            rmtemp(self._err.name)



    # preserve -- they could have been mocked already
    oldprint = getattr(__builtin__, 'print')
    oldout, olderr = sys.stdout, sys.stderr
    adapter = StringIOAdapter()
    sys.stdout, sys.stderr = adapter.handles

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
    setattr(__builtin__, 'print', fake_print)

    try:
        yield adapter
    finally:
        sys.stdout, sys.stderr = oldout, olderr
        setattr(__builtin__, 'print',  oldprint)
        adapter.cleanup()


@contextmanager
def swallow_logs(new_level=None):
    """Context manager to consume all logs.

    """
    lgr = logging.getLogger("datalad")

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
            kw = dict()
            get_tempfile_kwargs(kw, prefix="logs")

            self._out = open(tempfile.mktemp(**kw), 'w')

        def _read(self, h):
            with open(h.name) as f:
                return f.read()

        @property
        def out(self):
            self._out.flush()
            return self._read(self._out)

        @property
        def lines(self):
            return self.out.split('\n')

        @property
        def handle(self):
            return self._out

        def cleanup(self):
            self._out.close()
            rmtemp(self._out.name)

    adapter = StringIOAdapter()
    lgr.handlers = [logging.StreamHandler(adapter.handle)]
    if old_level < logging.DEBUG:  # so if HEAVYDEBUG etc -- show them!
        lgr.handlers += old_handlers
    if isinstance(new_level, basestring):
        new_level = getattr(logging, new_level)

    if new_level is not None:
        lgr.setLevel(new_level)

    try:
        yield adapter
    finally:
        lgr.handlers, lgr.level = old_handlers, old_level
        adapter.cleanup()


#
# Additional handlers
#
_sys_excepthook = sys.excepthook # Just in case we ever need original one

def setup_exceptionhook():
    def _datalad_pdb_excepthook(type, value, tb):
        if not is_interactive:
            lgr.warn("We cannot setup exception hook since not in interactive mode")
            # we are in interactive mode or we don't have a tty-like
            # device, so we call the default hook
            sys.__excepthook__(type, value, tb)
        else:
            import traceback, pdb
            traceback.print_exception(type, value, tb)
            print
            pdb.post_mortem(tb)
    sys.excepthook = _datalad_pdb_excepthook
