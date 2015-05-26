# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Miscellaneous utilities to assist with testing"""

import glob
import shutil
import stat
import os
import tempfile
import platform
import multiprocessing
import logging
import random
import socket
import SocketServer
import SimpleHTTPServer
import BaseHTTPServer

from functools import wraps
from os.path import exists, realpath, join as opj

from nose.tools import \
    assert_equal, assert_raises, assert_greater, assert_true, assert_false, \
    assert_in, assert_in as in_, \
    raises, ok_, eq_, make_decorator

from nose import SkipTest

from ..cmd import Runner
from ..support.repos import AnnexRepoOld
from ..utils import *
from ..support.exceptions import CommandNotAvailableError
from ..support.archives import compress_files


def create_tree_archive(path, name, load, overwrite=False):
    """Given an archive `name`, create under `path` with specified `load` tree
    """
    dirname = name[:-7]
    full_dirname = opj(path, dirname)
    os.makedirs(full_dirname)
    create_tree(full_dirname, load)
    # create archive
    compress_files([dirname], name, path=path, overwrite=overwrite)
    # remove original tree
    shutil.rmtree(full_dirname)


def create_tree(path, tree):
    """Given a list of tuples (name, load) create such a tree

    if load is a tuple itself -- that would create either a subtree or an archive
    with that content and place it into the tree if name ends with .tar.gz
    """
    if not exists(path):
        os.makedirs(path)

    for name, load in tree:
        full_name = opj(path, name)
        if isinstance(load, tuple):
            if name.endswith('.tar.gz'):
                create_tree_archive(path, name, load)
            else:
                create_tree(full_name, load)
        else:
            #encoding = sys.getfilesystemencoding()
            #if isinstance(full_name, unicode):
            #    import pydb; pydb.debugger()
            with open(full_name, 'w') as f:
                if isinstance(load, unicode):
                    load = load.encode('utf-8')
                f.write(load)

#
# Addition "checkers"
#

import git
import os
from os.path import exists, join
from datalad.support.annexrepo import AnnexRepo


def ok_clean_git_annex_proxy(path):
    """Helper to check, whether an annex in direct mode is clean
    """
    # TODO: May be let's make a method of AnnexRepo for this purpose

    ar = AnnexRepo(path)
    cwd = os.getcwd()
    os.chdir(path)

    try:
        out = ar.annex_proxy("git status")
    except CommandNotAvailableError, e:
        raise SkipTest
    finally:
        os.chdir(cwd)

    assert_in("nothing to commit, working directory clean", out[0], "git-status output via proxy not plausible: %s" % out[0])


def ok_clean_git(path, annex=True, untracked=[]):
    """Verify that under given path there is a clean git repository

    it exists, .git exists, nothing is uncommitted/dirty/staged
    """
    ok_(exists(path))
    ok_(exists(join(path, '.git')))
    if annex:
        ok_(exists(join(path, '.git', 'annex')))
    repo = git.Repo(path)

    if repo.index.entries.keys():
        ok_(repo.head.is_valid())

        # get string representations of diffs with index to ease
        # troubleshooting
        index_diffs = [str(d) for d in repo.index.diff(None)]
        head_diffs = [str(d) for d in repo.index.diff(repo.head.commit)]

        eq_(sorted(repo.untracked_files), sorted(untracked))
        eq_(index_diffs, [])
        eq_(head_diffs, [])


def ok_file_under_git(path, filename, annexed=False):
    repo = AnnexRepoOld(path)
    assert(filename in repo.get_indexed_files())  # file is known to Git
    assert(annexed == os.path.islink(opj(path, filename)))

#
# Helpers to test symlinks
#

def ok_symlink(path):
    """Checks whether path is either a working or broken symlink"""
    link_path = os.path.islink(path)
    if not link_path: 
        raise AssertionError("Path {} seems not to be a symlink".format(path))


def ok_good_symlink(path):
    ok_symlink(path)
    rpath = realpath(path)
    ok_(exists(rpath),
        msg="Path {} seems to be missing.  Symlink {} is broken".format(
                rpath, path))


def ok_broken_symlink(path):
    ok_symlink(path)
    rpath = realpath(path)
    assert_false(exists(rpath),
            msg="Path {} seems to be present.  Symlink {} is not broken".format(
                    rpath, path))


def ok_startswith(s, prefix):
    ok_(s.startswith(prefix),
        msg="String %r doesn't start with %r" % (s, prefix))


def nok_startswith(s, prefix):
    assert_false(s.startswith(prefix),
        msg="String %r starts with %r" % (s, prefix))


def ok_annex_get(ar, files, network=True):
    """Helper to run .annex_get decorated checking for correct operation

    annex_get passes through stderr from the ar to the user, which pollutes
    screen while running tests
    """
    with swallow_outputs() as cmo:
        ar.annex_get(files)
        if network:
            # wget or curl - just verify that annex spits out expected progress bar
            ok_('100%' in cmo.err or '100.0%' in cmo.err)
    # verify that load was fetched
    has_content = ar.file_has_content(files)
    if isinstance(has_content, bool):
        ok_(has_content)
    else:
        ok_(all(has_content))

#
# Decorators
#

@optional_args
def with_tree(t, tree=None, **tkwargs):

    @wraps(t)
    def newfunc(*arg, **kw):
        tkwargs_ = get_tempfile_kwargs(tkwargs, prefix="tree", wrapped=t)
        d = tempfile.mkdtemp(**tkwargs_)
        create_tree(d, tree)
        try:
            t(*(arg + (d,)), **kw)
        finally:
            rmtemp(d)
    return newfunc


lgr = logging.getLogger('datalad.tests')


class SilentHTTPHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    """A little adapter to silence the handler
    """
    def __init__(self, *args, **kwargs):
        self._silent = lgr.getEffectiveLevel() > logging.DEBUG
        SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

    def log_message(self, format, *args):
        if self._silent:
            return
        lgr.debug("HTTP: " + format % args)


def _multiproc_serve_path_via_http(hostname, path_to_serve_from, queue): # pragma: no cover
    os.chdir(path_to_serve_from)
    httpd = BaseHTTPServer.HTTPServer((hostname, 0), SilentHTTPHandler) 
    queue.put(httpd.server_port)
    httpd.serve_forever()


@optional_args
def serve_path_via_http(tfunc):
    """Decorator which serves content of a directory via http url
    """
    
    @wraps(tfunc)
    def newfunc(*args, **kwargs):

        #print '\n============================'
        #print 'In serve_path_via_http'
        #print args
        #print kwargs
        #print '============================'
        args, path = args[:-1], args[-1]

        # There is a problem with Haskell on wheezy trying to
        # fetch via IPv6 whenever there is a ::1 localhost entry in
        # /etc/hosts.  Apparently fixing that docker image reliably
        # is not that straightforward, although see
        # http://jasonincode.com/customizing-hosts-file-in-docker/
        # so we just force to use 127.0.0.1 while on wheezy
        hostname = '127.0.0.1' if on_debian_wheezy else 'localhost'
        
        queue = multiprocessing.Queue()
        multi_proc = multiprocessing.Process(target=_multiproc_serve_path_via_http, 
                                             args=(hostname, path, queue))
        multi_proc.start()
        port = queue.get(timeout=300)

        url = 'http://{}:{}/'.format(hostname, port)
        lgr.debug("HTTP: serving {} under {}".format(path, url))

        try:
            tfunc(*(args + (path, url)), **kwargs)
        finally:
            lgr.debug("HTTP: stopping server")
            multi_proc.terminate()
    return newfunc


@optional_args
def with_tempfile(t, *targs, **tkwargs):
    """Decorator function to provide a temporary file name and remove it at the end

    Parameters
    ----------
    mkdir : bool, optional (default: False)
        If True, temporary directory created using tempfile.mkdtemp()
    *targs, **tkwargs:
        All other arguments are passed into the call to tempfile.mk{,d}temp(),
        and resultant temporary filename is passed as the first argument into
        the function t.  If no 'prefix' argument is provided, it will be
        constructed using module and function names ('.' replaced with
        '_').

    To change the used directory without providing keyword argument 'dir' set
    DATALAD_TESTS_TEMPDIR.

    Examples
    --------

        @with_tempfile
        def test_write(tfile):
            open(tfile, 'w').write('silly test')
    """

    @wraps(t)
    def newfunc(*arg, **kw):

        tkwargs_ = get_tempfile_kwargs(tkwargs, wrapped=t)

        # if DATALAD_TESTS_TEMPDIR is set, use that as directory,
        # let mktemp handle it otherwise. However, an explicitly provided
        # dir=... will override this.
        mkdir = tkwargs_.pop('mkdir', False)


        filename = {False: tempfile.mktemp,
                    True: tempfile.mkdtemp}[mkdir](*targs, **tkwargs_)
        if __debug__:
            lgr.debug('Running %s with temporary filename %s'
                      % (t.__name__, filename))
        try:
            return t(*(arg + (filename,)), **kw)
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
                except OSError:
                    pass
    return newfunc


def _extend_globs(paths, flavors):
    globs = glob.glob(paths)

    # TODO -- provide management of 'network' tags somehow
    flavors_ = ['local', 'network', 'clone', 'network-clone'] if flavors=='auto' else flavors

    # TODO: move away?
    def get_repo_url(path):
        """Return ultimate URL for this repo"""
        if not exists(opj(path, '.git')):
            # do the dummiest check so we know it is not git.Repo's fault
            raise AssertionError("Path %s does not point to a git repository "
                                 "-- missing .git" % path)
        repo = git.Repo(path)
        if len(repo.remotes) == 1:
            remote = repo.remotes[0]
        else:
            remote = repo.remotes.origin
        return remote.config_reader.get('url')

    def clone_url(url):
        # delay import of our code until needed for certain
        from ..cmd import Runner
        runner = Runner()
        tdir = tempfile.mkdtemp(**get_tempfile_kwargs({}, prefix='clone_url'))
        _ = runner(["git", "clone", url, tdir], expect_stderr=True)
        open(opj(tdir, ".git", "remove-me"), "w").write("Please")  # signal for it to be removed after
        return tdir

    globs_extended = []
    if 'local' in flavors_:
        globs_extended += globs

    if 'network' in flavors_:
        globs_extended += [get_repo_url(repo) for repo in globs]

    if 'clone' in flavors_:
        globs_extended += [clone_url(repo) for repo in globs]

    if 'network-clone' in flavors_:
        globs_extended += [clone_url(get_repo_url(repo)) for repo in globs]

    return globs_extended


@optional_args
def with_testrepos(t, paths='*/*', toppath=None, flavors='auto', skip=False):
    """Decorator to provide a test repository available locally and/or over the Internet

    All tests under datalad/tests/testrepos are stored in two-level hierarchy,
    where top-level name describes nature/identifier of the test repository, and
    there could be multiple instances (e.g. generated differently) of the same
    "content"

    Parameters
    ----------
    paths : string, optional
      Glob paths to consider
    toppath : string, optional
      Path to the test repositories top directory.  If not provided,
      `datalad/tests/testrepos` within datalad is used.
    flavors : {'auto', 'local', 'clone', 'network', 'network-clone'} or list of thereof, optional
      What URIs to provide.  E.g. 'local' would just provide path to that
      submodule, while 'network' would provide url of the origin remote where
      that submodule was originally fetched from.  'clone' would clone repository
      first to a temporary location. 'network-clone' would first clone from the network
      location. 'auto' would include the list of appropriate
      ones (e.g., no 'network*' flavors if network tests are "forbidden").
    skip : bool, optional
      Allow to skip if no repositories were found. Otherwise would raise
      AssertionError

    Examples
    --------

        @with_testrepos('basic/*')
        def test_write(repo):
            assert(os.path.exists(os.path.join(repo, '.git', 'annex')))

    """

    @wraps(t)
    def newfunc(*arg, **kw):
        # TODO: would need to either avoid this "decorator" approach for
        # parametric tests or again aggregate failures like sweepargs does
        toppath_ = os.path.join(os.path.dirname(__file__), 'testrepos') \
            if toppath is None else toppath

        globs_extended = _extend_globs(os.path.join(toppath_, paths), flavors)
        if not len(globs_extended):
            raise (SkipTest if skip else AssertionError)(
                "Found no test repositories under %s."
                % os.path.join(toppath_, paths) +
                " Run git submodule update --init --recursive "
                if toppath is None else "")

        # print globs_extended
        for d in globs_extended:
            repo = d
            if __debug__:
                lgr.debug('Running %s on %s' % (t.__name__, repo))
            try:
                t(*(arg + (repo,)), **kw)
            finally:
                # ad-hoc but works
                if exists(repo) and exists(opj(repo, ".git", "remove-me")):
                    rmtemp(repo)
                pass  # might need to provide additional handling so, handle
    return newfunc
with_testrepos.__test__ = False


@optional_args
def assert_cwd_unchanged(func, ok_to_chdir=False):
    """Decorator to test whether the current working directory remains unchanged
    """

    @wraps(func)
    def newfunc(*args, **kwargs):
        cwd_before = os.getcwd()
        exc_info = None
        try:
            func(*args, **kwargs)
        except:
            exc_info = sys.exc_info()
        finally:
            cwd_after = os.getcwd()

        if cwd_after != cwd_before:
            os.chdir(cwd_before)
            if not ok_to_chdir:
                lgr.warning(
                    "%s changed cwd to %s. Mitigating and changing back to %s"
                    % (func, cwd_after, cwd_before))
                # If there was already exception raised, we better re-raise
                # that one since it must be more important, so not masking it
                # here with our assertion
                if exc_info is None:
                    assert_equal(cwd_before, cwd_after,
                                 "CWD changed from %s to %s" % (cwd_before, cwd_after))

        if exc_info is not None:
            raise exc_info[0], exc_info[1], exc_info[2]

    return newfunc


def ignore_nose_capturing_stdout(func):
    """Decorator workaround for nose's behaviour with redirecting sys.stdout

    Needed for tests involving the runner and nose redirecting stdout.
    Counter-intuitively, that means it needed for nosetests without '-s'.
    See issue reported here:
    https://code.google.com/p/python-nose/issues/detail?id=243&can=1&sort=-id&colspec=ID%20Type%20Status%20Priority%20Stars%20Milestone%20Owner%20Summary
    """

    @make_decorator(func)
    def newfunc(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except AttributeError, e:
            if e.message.find('StringIO') > -1 and e.message.find('fileno') > -1:
                pass
            else:
                raise
    return newfunc

# List of most obscure filenames which might or not be supported by different
# filesystems across different OSs.  Start with the most obscure
OBSCURE_FILENAMES = (
    " \"';a&b/&cd `| ",  # shouldn't be supported anywhere I guess due to /
    " \"';a&b&cd `| ",
    " \"';abcd `| ",
    " \"';abcd | ",
    " \"';abcd ",
    " ;abcd ",
    " ;abcd",
    " ab cd ",
    " ab cd",
    "a",
    " abc d.dat ",  # they all should at least support spaces and dots
)

@with_tempfile(mkdir=True)
def get_most_obscure_supported_name(tdir):
    """Return the most filename which filesystem under TEMPDIR could support

    TODO: we might want to use it as a function where we would provide tdir
    """
    for filename in OBSCURE_FILENAMES:
        if on_windows and filename.rstrip() != filename:
            continue
        try:
            with open(opj(tdir, filename), 'w') as f:
                f.write("TEST LOAD")
            return filename  # it will get removed as a part of wiping up the directory
        except:
            lgr.debug("Filename %r is not supported on %s under %s",
                      filename, platform.system(), tdir)
            pass
    raise RuntimeError("Could not create any of the files under %s among %s"
                       % (tdir, OBSCURE_FILENAMES))

#
# Context Managers
#
