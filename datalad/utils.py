# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
import shutil, stat, os, sys
import tempfile
import platform

from functools import wraps
from os.path import exists, join as opj, realpath

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


def is_symlink(file_, good=None):
    """Check if file_ is a symlink

    Parameters
    ----------
    good: None or bool, optional
        Test not only that it is a symlink, but either it is a good symlink
        (good=True) or broken (good=False) symlink.  So if good=False,
        it would return True only if it is a symlink and it is broken.
    """
    try:
        link = os.readlink(file_)
    except OSError:
        link = None

    # TODO: copied from ok_symlink so may be we also want to check the path etc?
    # path_ = realpath(file_)
    # ok_(path_ != link)
    # TODO anything else?

    if good is None:
        # nothing to do more:
        return bool(link)
    else:
        return is_good_symlink(file_)


def is_good_symlink(file_):
    """Return if a file_ is a good symlink (assuming it is a symlink)
    """
    return exists(realpath(file_))

def ls_tree(path, files_only=False, relative=True):
    """Recurse into the directory and return all found files (and dirs if dirs)
    """
    out = []
    for root, dirs, files in os.walk(path):
        for f in files:
            out.append(opj(root, f))
        if not files_only:
            for d in dirs:
                out.append(opj(root, d))
    out = sorted(out)
    if relative:
        beg = len(path) + len(os.pathsep)
        return [o[beg:] for o in out]
    else:
        return out

def has_content(file_):
    """Returns True if a file is not a broken symlink, and if it has content
    """
    if not on_windows:
        if not is_symlink(file_, good=True):
            return False
    # verify it has content
    return os.stat(realpath(file_)).st_size > 0


def rm_empties(p, misses_files=None, misses_dirs=None):
    """Callback for traverse_for_content to be used for do_some, do_none

    To prune empty content
    """
    for d in misses_dirs:
        rmtree(opj(p, d))
    for f in misses_files:
        os.unlink(opj(p, f))


def traverse_for_content(path,
                         do_none=None,
                         do_some=None,
                         do_all=None,
                         matcher=has_content,
                         exclude=(),
                         pass_hits=False,
                         pass_misses=False,
                         return_="any"
                         ):
    """Traverse and perform actions depending on either tree files pass the matcher

    Note
    ----

    "some" is used instead of "any" to accent that it is the case when only some,
    not all files are matched

    Parameters
    ----------
    do_none, do_some, do_all: callable, optional
        Callback to use for each traversed directory in case it has None, any,
        or all files (in that directory, or under) hit by `matcher`.
        Those callbacks should have following arguments
           path: string
             path to the directory
           hits_files, hits_dirs: list, optional
             list of files and list of directories which pass the matcher.
             Passed only if pass_hits=True
           misses_files, misses_dirs: list, optional
             list of files and list of directories which pass the matcher.
             Passed only if pass_misses=True
    matcher: callable, optional
        Given the path (to a file) should return the bool result
    exclude: iterable or regexp, optional
        Files/directories to exclude from consideration. If an iterable (e.g.
        list or string) -- checked for presence in that iterable, otherwise --
        assuming it is a compiled regular expression to .match against
    pass_hits: bool, optional
        Either to pass hits_files, hits_dirs into do_* callables
    pass_misses: bool, optional
        Either to pass misses_files, misses_dirs into do_* callables
    return_: {'all', 'any'}, optional
        Instructs either function should return True when 'all' or 'any' of
        its children passed the matcher

    Returns
    -------
    bool
    """
    # Naive recursive implementation, still using os.walk though

    # Get all elements of current directory
    root, dirs, files = os.walk(path).next()
    assert(root == path)

    if exclude:
        if hasattr(exclude, '__iter__'):
            excluder = lambda x: x not in exclude
        else:
            excluder = lambda x: not exclude.match(x)

        dirs = filter(excluder, dirs)
        files = filter(excluder, files)

    # TODO: I feel like in some cases we might want to stop descent earlier
    # and not even bother with kids, but I could be wrong
    status_dirs = [
        traverse_for_content(os.path.join(root, d),
                             do_none=do_none,
                             do_some=do_some,
                             do_all=do_all,
                             matcher=matcher,
                             pass_hits=pass_hits,
                             pass_misses=pass_misses,
                             return_=return_)
        for d in dirs
    ]

    # TODO: Theoretically we could sophisticate it. E.g. if only do_some
    # or do_none defined and already we have some of status_dirs, no need
    # to verify files. Also if some are not defined in dirs and we have
    # only do_all -- no need to matcher files.  For now -- KISS

    # Now verify all the files
    status_files = [
        matcher(os.path.join(root, f))
        for f in files
    ]

    status_all = status_dirs + status_files

    # TODO: may be there is a point to pass those files into do_
    # callbacks -- add option  pass_hits?
    all_match = all(status_all)
    some_match = any(status_all)

    kw = {}
    if pass_hits:
        kw.update(
            {'hits_dirs':  [d for d, c in zip(dirs, status_dirs) if c],
             'hits_files': [f for f, c in zip(files, status_files) if c]})

    if pass_misses:
        kw.update(
            {'misses_dirs':  [d for d, c in zip(dirs, status_dirs) if not c],
             'misses_files': [f for f, c in zip(files, status_files) if not c]})

    if all_match:
        if do_all:
            do_all(root, **kw)
    elif some_match:
        if do_some:
            do_some(root, **kw)
    else:
        if do_none:
            do_none(root, **kw)

    return {'all': all_match,
            'any': some_match,
            }[return_]


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

#
# Context Managers
#

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
