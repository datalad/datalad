# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Miscellaneous utilities to assist with testing"""

import glob, shutil, stat, os
import tempfile
import platform

from functools import wraps
from os.path import exists, join as opj

from nose.tools import \
    assert_equal, assert_raises, assert_greater, assert_false, \
    assert_in, assert_in as in_, \
    raises, ok_, eq_, make_decorator
from nose import SkipTest

from ..cmd import Runner
from ..support.repos import AnnexRepo
from ..utils import *

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

def create_archive(path, name, load):
    dirname = name[:-7]
    full_dirname = opj(path, dirname)
    os.makedirs(full_dirname)
    create_tree(full_dirname, load)
    # create archive
    status = Runner().run('tar -czvf %(name)s %(dirname)s' % locals(),
                          cwd=path, expect_stderr=True)
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

#
# Addition "checkers"
#

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
    assert(annexed == os.path.islink(opj(path, filename)))


#
# Decorators
#

from ..utils import optional_args

@optional_args
def with_tree(t, tree=None, **tkwargs):
    @wraps(t)
    def newfunc(*arg, **kw):
        d = tempfile.mkdtemp(**tkwargs)
        create_tree(d, tree)
        try:
            t(*(arg + (d,)), **kw)
        finally:
            rmtemp(d)
    return newfunc


# GRRR -- this one is crippled since path where HTTPServer is serving
# from can't be changed without pain.
import logging
import random
import SimpleHTTPServer
import SocketServer
from threading import Thread

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


def serve_path_via_http():
    """Decorator which serves content of a directory via http url
    """
    def decorate(func):
        def newfunc(*arg, **kw):
            port = random.randint(8000, 8500)
            # TODO: ATM we are relying on path being local so we could
            # start HTTP server in the same directory.  FIX IT!
            SocketServer.TCPServer.allow_reuse_address = True
            httpd = SocketServer.TCPServer(("", port), SilentHTTPHandler)
            server_thread = Thread(target=httpd.serve_forever)
            arg, path = arg[:-1], arg[-1]
            # There is a problem with Haskell on wheezy trying to
            # fetch via IPv6 whenever there is a ::1 localhost entry in
            # /etc/hosts.  Apparently fixing that docker image reliably
            # is not that straightforward, although see
            # http://jasonincode.com/customizing-hosts-file-in-docker/
            # so we just force to use 127.0.0.1 while on wheezy
            hostname = '127.0.0.1' if on_debian_wheezy else 'localhost'
            url = 'http://%s:%d/%s/' % (hostname, port, path)
            lgr.debug("HTTP: serving %s under %s", path, url)
            server_thread.start()

            #time.sleep(1)               # just give it few ticks
            try:
                func(*(arg + (path, url,)), **kw)
            finally:
                lgr.debug("HTTP: stopping server")
                httpd.shutdown()
                server_thread.join()
        newfunc = make_decorator(func)(newfunc)
        return newfunc
    return decorate


# TODO: just provide decorators for tempfile.mk* functions. This is ugly!
def _update_tempfile_kwargs_for_DATALAD_TESTS_TEMPDIR(tkwargs_):
    """Updates kwargs to be passed to tempfile. calls depending on env
    """
    directory = os.environ.get('DATALAD_TESTS_TEMPDIR')
    if directory and 'dir' not in tkwargs_:
        tkwargs_['dir'] = directory


@optional_args
def with_tempfile(t, *targs, **tkwargs):
    """Decorator function to provide a temporary file name and remove it at the end

    Parameters
    ----------
    mkdir : bool, optional (default: False)
        If True, temporary directory created using tempfile.mkdtemp()
    *args, **kwargs:
        All other arguments are passed into the call to tempfile.mk{t,d}emp(),
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
        # operate on a copy of tkwargs to avoid any side-effects
        tkwargs_ = tkwargs.copy()

        if len(targs)<2 and not 'prefix' in tkwargs_:
            try:
                tkwargs_['prefix'] = 'datalad_temp_%s.%s' \
                                    % (func.__module__, func.func_name)
            except:
                # well -- if something wrong just proceed with defaults
                pass

        # if DATALAD_TESTS_TEMPDIR is set, use that as directory,
        # let mktemp handle it otherwise. However, an explicitly provided
        # dir=... will override this.
        mkdir = tkwargs_.pop('mkdir', False)

        _update_tempfile_kwargs_for_DATALAD_TESTS_TEMPDIR(tkwargs_)

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
        kw = dict(); _update_tempfile_kwargs_for_DATALAD_TESTS_TEMPDIR(kw)
        tdir = tempfile.mkdtemp(**kw)
        repo = runner(["git", "clone", url, tdir])
        open(opj(tdir, ".git", "remove-me"), "w").write("Please") # signal for it to be removed after
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
                pass # might need to provide additional handling so, handle
    return newfunc
with_testrepos.__test__ = False

def assert_cwd_unchanged(func):
    """Decorator to test whether the current working directory remains unchanged

    """

    @make_decorator(func)
    def newfunc(*args, **kwargs):
        cwd_before = os.getcwd()
        func(*args, **kwargs)
        cwd_after = os.getcwd()
        assert_equal(cwd_before, cwd_after ,"CWD changed from %s to %s" % (cwd_before, cwd_after))

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
    " \"';a&b/&cd `| ", # shouldn't be supported anywhere I guess due to /
    " \"';a&b&cd `| ",
    " \"';abcd `| ",
    " \"';abcd | ",
    " \"';abcd ",
    " ;abcd ",
    " ab cd ",
    "a",
    " abc d.dat ", # they all should at least support spaces and dots
)

@with_tempfile(mkdir=True)
def get_most_obscure_supported_name(tdir):
    """Return the most filename which filesystem under TEMPDIR could support

    TODO: we might want to use it as a function where we would provide tdir
    """
    for filename in OBSCURE_FILENAMES:
        try:
            with open(opj(tdir, filename), 'w') as f:
                f.write("TEST LOAD")
            return filename # it will get removed as a part of wiping up the directory
        except:
            lgr.debug("Filename %r is not supported on %s under %s",
                      filename, platform.system(), tdir)
            pass
    raise RuntimeError("Could not create any of the files under %s among %s"
                       % (tdir, OBSCURE_FILENAMES))

#
# Context Managers
#
import StringIO, sys
from contextlib import contextmanager

@contextmanager
def swallow_outputs():
    """Context manager to help consuming both stdout and stderr.

    stdout is available as cm.out and stderr as cm.err whenever cm is the
    yielded context manager.
    Internally uses temporary files to guarantee absent side-effects of swallowing
    into StringIO which lacks .fileno
    """

    class StringIOAdapter(object):
        """Little adapter to help getting out/err values
        """
        def __init__(self):
            kw = dict()
            _update_tempfile_kwargs_for_DATALAD_TESTS_TEMPDIR(kw)

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
    oldout, olderr = sys.stdout, sys.stderr
    adapter = StringIOAdapter()
    sys.stdout, sys.stderr = adapter.handles

    try:
        yield adapter
    finally:
        sys.stdout, sys.stderr = oldout, olderr
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
            _update_tempfile_kwargs_for_DATALAD_TESTS_TEMPDIR(kw)

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
    if old_level < logging.DEBUG: # so if HEAVYDEBUG etc -- show them!
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