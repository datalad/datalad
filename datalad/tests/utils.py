# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import shutil, stat, os
import tempfile
from functools import wraps

from nose.tools import assert_equal, assert_raises, assert_greater, raises, \
    ok_, eq_, make_decorator
from nose import SkipTest

from ..cmd import Runner
from ..support.repos import AnnexRepo

def rmtree(path, *args, **kwargs):
    """To remove git-annex .git it is needed to make all files and directories writable again first
    """
    for root, dirs, files in os.walk(path):
        for f in files:
            fullf = os.path.join(root, f)
            # might be the "broken" symlink which would fail to stat etc
            if os.path.exists(fullf):
                os.chmod(fullf, os.stat(fullf).st_mode | stat.S_IWRITE | stat.S_IREAD)
        os.chmod(root, os.stat(root).st_mode | stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(path, *args, **kwargs)

def create_archive(path, name, load):
    dirname = name[:-7]
    full_dirname = os.path.join(path, dirname)
    os.makedirs(full_dirname)
    create_tree(full_dirname, load)
    # create archive
    status = Runner().run('cd %(path)s && tar -czvf %(name)s %(dirname)s' % locals())
    # remove original tree
    shutil.rmtree(full_dirname)

def create_tree(path, tree):
    """Given a list of tuples (name, load) create such a tree

    if load is a tuple itself -- that would create either a subtree or an archive
    with that content and place it into the tree if name ends with .tar.gz
    """
    if not os.path.exists(path):
        os.makedirs(path)

    for name, load in tree:
        full_name = os.path.join(path, name)
        if isinstance(load, tuple):
            if name.endswith('.tar.gz'):
                create_archive(path, name, load)
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

@optional_args
def with_tree(t, tree=None, **tkwargs):
    @wraps(t)
    def newfunc(*arg, **kw):
        d = tempfile.mkdtemp(**tkwargs)
        create_tree(d, tree)
        try:
            t(*((d,) + arg), **kw)
        finally:
            #print "TODO: REMOVE tree ", d
            shutil.rmtree(d)
    return newfunc


import hashlib
def md5sum(filename):
    with open(filename) as f:
        return hashlib.md5(f.read()).hexdigest()


import git
from os.path import exists, join
def ok_clean_git(path, annex=True, untracked=[]):
    """Verify that under given path there is a clean git repository

    it exists, .git exists, nothing is uncommitted/dirty/staged
    """
    ok_(exists(path))
    ok_(exists(join(path, '.git')))
    if annex:
        ok_(exists(join(path, '.git', 'annex')))
    repo = git.Repo(path)

    ok_(repo.head.is_valid())

    # get string representations of diffs with index to ease troubleshooting
    index_diffs = [str(d) for d in repo.index.diff(None)]
    head_diffs = [str(d) for d in repo.index.diff(repo.head.commit)]

    eq_(sorted(repo.untracked_files), sorted(untracked))
    eq_(index_diffs, [])
    eq_(head_diffs, [])

def ok_file_under_git(path, filename, annexed=False):
    repo = AnnexRepo(path)
    assert(filename in repo.get_indexed_files()) # file is known to Git
    assert(annexed == os.path.islink(os.path.join(path, filename)))


# GRRR -- this one is crippled since path where HTTPServer is serving
# from can't be changed without pain.
import logging
import random
import SimpleHTTPServer
import SocketServer
from threading import Thread

lgr = logging.getLogger('datalad')

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

def serve_path_via_http(*args, **tkwargs):
    def decorate(func):
        def newfunc(path, *arg, **kw):
            port = random.randint(8000, 8500)
            #print "Starting to serve path ", path
            # TODO: ATM we are relying on path being local so we could
            # start HTTP server in the same directory.  FIX IT!
            SocketServer.TCPServer.allow_reuse_address = True
            httpd = SocketServer.TCPServer(("", port), SilentHTTPHandler)
            server_thread = Thread(target=httpd.serve_forever)
            url = 'http://localhost:%d/%s/' % (port, path)
            lgr.debug("HTTP: serving %s under %s", path, url)
            server_thread.start()
            if 'path' in kw:
                raise ValueError(
                    "path kwarg to be provided by serve_path_via_http")
            kw_ = {'path': path}
            kw_.update(kw)

            #time.sleep(1)               # just give it few ticks
            try:
                func(*((url,)+arg), **kw_)
            finally:
                lgr.debug("HTTP: stopping server")
                httpd.shutdown()
                #print "Waiting for thread to stop"
                server_thread.join()
        newfunc = make_decorator(func)(newfunc)
        return newfunc
    return decorate

def sorted_files(dout):
    """Return a (sorted) list of files under dout
    """
    return sorted(sum([[os.path.join(r, f)[len(dout)+1:] for f in files]
                       for r,d,files in os.walk(dout)
                       if not '.git' in r], []))

import glob


@optional_args
def with_tempfile(t, *targs, **tkwargs):
    """Decorator function to provide a temporary file name and remove it at the end.

    All arguments are passed into the call to tempfile.mktemp(), and
    resultant temporary filename is passed as the first argument into
    the test.  If no 'prefix' argument is provided, it will be
    constructed using module and function names ('.' replaced with
    '_').

    To change the used directory without providing keyword argument 'dir' set
    DATALAD_TESTS_TEMPDIR.

    Example use::

        @with_tempfile
        def test_write(tfile):
            open(tfile, 'w').write('silly test')
    """

    @wraps(t)
    def newfunc(*arg, **kw):
        if len(targs)<2 and not 'prefix' in tkwargs:
            try:
                tkwargs['prefix'] = 'datalad_temp_%s.%s' \
                                    % (func.__module__, func.func_name)
            except:
                # well -- if something wrong just proceed with defaults
                pass

        # if DATALAD_TESTS_TEMPDIR is set, use that as directory,
        # let mktemp handle it otherwise. However, an explicitly provided
        # dir=... will override this.
        directory = os.environ.get('DATALAD_TESTS_TEMPDIR')
        if directory is not None and 'dir' not in tkwargs:
            tkwargs['dir'] = directory


        filename = tempfile.mktemp(*targs, **tkwargs)
        if __debug__:
            lgr.debug('Running %s with temporary filename %s'
                      % (t.__name__, filename))
        try:
            t(*(arg + (filename,)), **kw)
        finally:
            # glob here for all files with the same name (-suffix)
            # would be useful whenever we requested .img filename,
            # and function creates .hdr as well
            lsuffix = len(tkwargs.get('suffix', ''))
            filename_ = lsuffix and filename[:-lsuffix] or filename
            filenames = glob.glob(filename_ + '*')
            if len(filename_) < 3 or len(filenames) > 5:
                # For paranoid yoh who stepped into this already ones ;-)
                lgr.warning("It is unlikely that it was intended to remove all"
                            " files matching %r. Skipping" % filename_)
                return
            for f in filenames:
                try:
                    # Can also be a directory
                    if os.path.isdir(f):
                        rmtree(f)
                    else:
                        os.unlink(f)
                except OSError:
                    pass
    return newfunc


def _extend_globs(paths, flavors):
    globs = glob.glob(paths)

    # TODO -- provide management of 'network' tags somehow
    flavors_ = ['local', 'network'] if flavors=='auto' else flavors
    if 'clone' in flavors_:
        raise NotImplementedError("Providing clones is not implemented here yet")
    globs_extended = []
    if 'local' in flavors_:
        globs_extended += globs

    # TODO: move away?
    def get_repo_url(path):
        """Return ultimate URL for this repo"""
        if not os.path.exists(os.path.join(path, '.git')):
            # do the dummiest check so we know it is not git.Repo's fault
            raise AssertionError("Path %s does not point to a git repository "
                                 "-- missing .git" % path)
        repo = git.Repo(path)
        if len(repo.remotes) == 1:
            remote = repo.remotes[0]
        else:
            remote = repo.remotes.origin
        return remote.config_reader.get('url')

    if 'network' in flavors_:
        globs_extended += [get_repo_url(repo) for repo in globs]
    return globs_extended

@optional_args
def with_testrepos(t, paths='*/*', toppath=None, flavors='auto', skip=False):
    """Decorator function to provide test with a test repository available locally and/or over the Internet

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
    flavors : {'auto', 'local', 'clone', 'network'} or list of thereof, optional
      What URIs to provide.  E.g. 'local' would just provide path to that
      submodule, while 'network' would provide url of the origin remote where
      that submodule was originally fetched from.  'clone' would clone repository
      first to a temporary location. 'auto' would include the list of appropriate
      ones (e.g., no 'network' if network tests are "forbidden")
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
                t(repo, *arg, **kw)
            finally:
                pass # might need to provide additional handling so, handle
    return newfunc
with_testrepos.__test__ = False

def assert_cwd_unchanged(func):
    """Decorator to test whether the current working directory remains unchanged by `func`

    """

    @make_decorator(func)
    def newfunc(*args, **kwargs):
        cwd_before = os.getcwd()
        func(*args, **kwargs)
        cwd_after = os.getcwd()
        assert_equal(cwd_before, cwd_after ,"CWD changed from %s to %s" % (cwd_before, cwd_after))

    return newfunc

def ignore_nose_capturing_stdout(func):
    """Workaround for nose's behaviour with redirecting sys.stdout


    Needed for tests involving the runner and nose redirecting stdout.
    Counterintuitivly, that means it needed for nosestests without '-s'.
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