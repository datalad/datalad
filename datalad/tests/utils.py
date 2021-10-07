# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Miscellaneous utilities to assist with testing"""

import glob
import gzip
import inspect
import lzma
import shutil
import stat
from json import dumps
import os
import re
import tempfile
import platform
import multiprocessing
import logging
import random
import socket
import textwrap
import warnings
from fnmatch import fnmatch
import time
from difflib import unified_diff
from contextlib import contextmanager
from unittest.mock import patch

from http.server import (
    HTTPServer,
    SimpleHTTPRequestHandler,
)

from functools import wraps
from os.path import (
    curdir,
    exists,
    join as opj,
    relpath,
    split as pathsplit,
)

from nose.plugins.attrib import attr
from nose.tools import (
    assert_equal,
    assert_false,
    assert_greater,
    assert_greater_equal,
    assert_in as in_,
    assert_in,
    assert_is,
    assert_is_none,
    assert_is_not,
    assert_is_not_none,
    assert_not_equal,
    assert_not_in,
    assert_not_is_instance,
    assert_raises,
    assert_true,
    eq_,
    make_decorator,
    ok_,
    raises,
)

from nose.tools import assert_set_equal
from nose.tools import assert_is_instance
from nose import SkipTest

from datalad import cfg as dl_cfg
import datalad.utils as ut
# TODO this must go
from ..utils import *
from datalad.utils import (
    Path,
    ensure_unicode,
)

from .. import utils
from ..support.exceptions import (
    CommandError,
    CommandNotAvailableError,
)
from ..support.external_versions import external_versions
from ..support.vcr_ import *
from ..support.keyring_ import MemoryKeyring
from ..support.network import RI
from ..dochelpers import exc_str, borrowkwargs
from ..cmdline.helpers import get_repo_instance
from ..consts import (
    ARCHIVES_TEMP_DIR,
)
from . import _TEMP_PATHS_GENERATED
from datalad.cmd import (
    GitWitlessRunner,
    KillOutput,
    StdOutErrCapture,
    WitlessRunner,
)

# temp paths used by clones
_TEMP_PATHS_CLONES = set()


# Additional indicators
on_travis = bool(os.environ.get('TRAVIS', False))

if external_versions["cmd:git"] >= "2.28":
    # The specific value here doesn't matter, but it should not be the default
    # from any Git version to test that we work with custom values.
    DEFAULT_BRANCH = "dl-test-branch"  # Set by setup_package().
else:
    DEFAULT_BRANCH = "master"

if external_versions["cmd:git"] >= "2.30.0":
    # The specific value here doesn't matter, but it should not be the default
    # from any Git version to test that we work with custom values.
    DEFAULT_REMOTE = "dl-test-remote"  # Set by setup_package().
else:
    DEFAULT_REMOTE = "origin"

# additional shortcuts
neq_ = assert_not_equal
nok_ = assert_false

lgr = logging.getLogger("datalad.tests.utils")


def skip_if_no_module(module):
    try:
        imp = __import__(module)
    except Exception as exc:
        raise SkipTest("Module %s fails to load: %s" % (module, exc_str(exc)))


def skip_if_scrapy_without_selector():
    """A little helper to skip some tests which require recent scrapy"""
    try:
        import scrapy
        from scrapy.selector import Selector
    except ImportError:
        from nose import SkipTest
        raise SkipTest(
            "scrapy misses Selector (too old? version: %s)"
            % getattr(scrapy, '__version__'))


def skip_if_url_is_not_available(url, regex=None):
    # verify that dataset is available
    from datalad.downloaders.providers import Providers
    from datalad.downloaders.base import DownloadError
    providers = Providers.from_config_files()
    try:
        content = providers.fetch(url)
        if regex and re.search(regex, content):
            raise SkipTest("%s matched %r -- skipping the test" % (url, regex))
    except DownloadError:
        raise SkipTest("%s failed to download" % url)


def check_not_generatorfunction(func):
    """Internal helper to verify that we are not decorating generator tests"""
    if inspect.isgeneratorfunction(func):
        raise RuntimeError("{}: must not be decorated, is a generator test"
                           .format(func.__name__))


def skip_if_no_network(func=None):
    """Skip test completely in NONETWORK settings

    If not used as a decorator, and just a function, could be used at the module level
    """
    check_not_generatorfunction(func)

    def check_and_raise():
        if dl_cfg.get('datalad.tests.nonetwork'):
            raise SkipTest("Skipping since no network settings")

    if func:
        @wraps(func)
        @attr('network')
        @attr('skip_if_no_network')
        def  _wrap_skip_if_no_network(*args, **kwargs):
            check_and_raise()
            return func(*args, **kwargs)
        return  _wrap_skip_if_no_network
    else:
        check_and_raise()


def skip_if_on_windows(func=None):
    """Skip test completely under Windows
    """
    check_not_generatorfunction(func)

    def check_and_raise():
        if on_windows:
            raise SkipTest("Skipping on Windows")

    if func:
        @wraps(func)
        @attr('skip_if_on_windows')
        def  _wrap_skip_if_on_windows(*args, **kwargs):
            check_and_raise()
            return func(*args, **kwargs)
        return  _wrap_skip_if_on_windows
    else:
        check_and_raise()


def skip_if_root(func=None):
    """Skip test if uid == 0.

    Note that on Windows (or anywhere else `os.geteuid` is not available) the
    test is _not_ skipped.
    """
    check_not_generatorfunction(func)

    def check_and_raise():
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            raise SkipTest("Skipping: test assumptions fail under root")

    if func:
        @wraps(func)
        @attr('skip_if_root')
        def  _wrap_skip_if_root(*args, **kwargs):
            check_and_raise()
            return func(*args, **kwargs)
        return  _wrap_skip_if_root
    else:
        check_and_raise()


@optional_args
def skip_if(func, cond=True, msg=None, method='raise'):
    """Skip test for specific condition

    Parameters
    ----------
    cond: bool
      condition on which to skip
    msg: str
      message to print if skipping
    method: str
      either 'raise' or 'pass'. Whether to skip by raising `SkipTest` or by
      just proceeding and simply not calling the decorated function.
      This is particularly meant to be used, when decorating single assertions
      in a test with method='pass' in order to not skip the entire test, but
      just that assertion.
    """

    check_not_generatorfunction(func)

    @wraps(func)
    def  _wrap_skip_if(*args, **kwargs):
        if cond:
            if method == 'raise':
                raise SkipTest(msg if msg else "condition was True")
            elif method == 'pass':
                print(msg if msg else "condition was True")
                return
        return func(*args, **kwargs)
    return  _wrap_skip_if


def skip_ssh(func):
    """Skips SSH tests if on windows or if environment variable
    DATALAD_TESTS_SSH was not set
    """

    check_not_generatorfunction(func)

    @wraps(func)
    @attr('skip_ssh')
    def  _wrap_skip_ssh(*args, **kwargs):
        test_ssh = dl_cfg.get("datalad.tests.ssh", '')
        if not test_ssh or test_ssh in ('0', 'false', 'no'):
            raise SkipTest("Run this test by setting DATALAD_TESTS_SSH")
        return func(*args, **kwargs)
    return  _wrap_skip_ssh


def skip_nomultiplex_ssh(func):
    """Skips SSH tests if default connection/manager does not support multiplexing

    e.g. currently on windows or if set via datalad.ssh.multiplex-connections config variable
    """

    check_not_generatorfunction(func)
    from ..support.sshconnector import MultiplexSSHManager, SSHManager

    @wraps(func)
    @attr('skip_nomultiplex_ssh')
    @skip_ssh
    def  _wrap_skip_nomultiplex_ssh(*args, **kwargs):
        if SSHManager is not MultiplexSSHManager:
            raise SkipTest("SSH without multiplexing is used")
        return func(*args, **kwargs)
    return  _wrap_skip_nomultiplex_ssh

#
# Addition "checkers"
#

import os
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileNotInAnnexError
from datalad.distribution.dataset import Dataset
from ..utils import chpwd, getpwd


def ok_clean_git(path, annex=None, index_modified=[], untracked=[]):
    """Obsolete test helper. Use assert_repo_status() instead.

    Still maps a few common cases to the new helper, to ease transition
    in extensions.
    """
    kwargs = {}
    if index_modified:
        kwargs['modified'] = index_modified
    if untracked:
        kwargs['untracked'] = untracked
    assert_repo_status(
        path,
        annex=annex,
        **kwargs,
    )


def ok_file_under_git(path, filename=None, annexed=False):
    """Test if file is present and under git/annex control

    If relative path provided, then test from current directory
    """
    annex, file_repo_path, filename, path, repo = _prep_file_under_git(path, filename)
    assert_in(file_repo_path, repo.get_indexed_files())  # file is known to Git

    if annex:
        try:
            # operates on relative to curdir path
            repo.get_file_key(file_repo_path)
            in_annex = True
        except FileNotInAnnexError as e:
            in_annex = False
    else:
        in_annex = False

    assert(annexed == in_annex)


def put_file_under_git(path, filename=None, content=None, annexed=False):
    """Place file under git/annex and return used Repo
    """
    annex, file_repo_path, filename, path, repo = _prep_file_under_git(path, filename)
    if content is None:
        content = ""
    with open(opj(repo.path, file_repo_path), 'w') as f_:
        f_.write(content)

    if annexed:
        if not isinstance(repo, AnnexRepo):
            repo = AnnexRepo(repo.path)
        repo.add(file_repo_path)
    else:
        repo.add(file_repo_path, git=True)
    repo.commit(_datalad_msg=True)
    ok_file_under_git(repo.path, file_repo_path, annexed)
    return repo


def _prep_file_under_git(path, filename):
    """Get instance of the repository for the given filename

    Helper to be used by few functions
    """
    if filename is None:
        # path provides the path and the name
        path, filename = pathsplit(path)
    try:
        # if succeeds when must not (not `annexed`) -- fail
        repo = get_repo_instance(path, class_=AnnexRepo)
        annex = True
    except RuntimeError as e:
        # TODO: make a dedicated Exception
        if "No annex repository found in" in str(e):
            repo = get_repo_instance(path, class_=GitRepo)
            annex = False
        else:
            raise

    # path to the file within the repository
    # repo.path is a "realpath" so to get relpath working correctly
    # we need to realpath our path as well
    # do absolute() in addition to always get an absolute path
    # even with non-existing paths on windows
    path = str(Path(path).resolve().absolute())  # intentional realpath to match GitRepo behavior
    file_repo_dir = relpath(path, repo.path)
    file_repo_path = filename if file_repo_dir == curdir else opj(file_repo_dir, filename)
    return annex, file_repo_path, filename, path, repo


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
    rpath = Path(path).resolve()
    ok_(rpath.exists(),
        msg="Path {} seems to be missing.  Symlink {} is broken".format(
                rpath, path))


def ok_broken_symlink(path):
    ok_symlink(path)
    rpath = Path(path).resolve()
    assert_false(rpath.exists(),
            msg="Path {} seems to be present.  Symlink {} is not broken".format(
                    rpath, path))


def ok_startswith(s, prefix):
    ok_(s.startswith(prefix),
        msg="String %r doesn't start with %r" % (s, prefix))


def ok_endswith(s, suffix):
    ok_(s.endswith(suffix),
        msg="String %r doesn't end with %r" % (s, suffix))


def nok_startswith(s, prefix):
    assert_false(s.startswith(prefix),
        msg="String %r starts with %r" % (s, prefix))


def ok_git_config_not_empty(ar):
    """Helper to verify that nothing rewritten the config file"""
    # TODO: we don't support bare -- do we?
    assert_true(os.stat(opj(ar.path, '.git', 'config')).st_size)


def ok_annex_get(ar, files, network=True):
    """Helper to run .get decorated checking for correct operation

    get passes through stderr from the ar to the user, which pollutes
    screen while running tests

    Note: Currently not true anymore, since usage of --json disables
    progressbars
    """
    ok_git_config_not_empty(ar) # we should be working in already inited repo etc
    with swallow_outputs() as cmo:
        ar.get(files)
    # verify that load was fetched
    ok_git_config_not_empty(ar) # whatever we do shouldn't destroy the config file
    has_content = ar.file_has_content(files)
    if isinstance(has_content, bool):
        ok_(has_content)
    else:
        ok_(all(has_content))


def ok_generator(gen):
    assert_true(inspect.isgenerator(gen), msg="%s is not a generator" % gen)


assert_is_generator = ok_generator  # just an alias


def ok_archives_caches(repopath, n=1, persistent=None):
    """Given a path to repository verify number of archives

    Parameters
    ----------
    repopath : str
      Path to the repository
    n : int, optional
      Number of archives directories to expect
    persistent: bool or None, optional
      If None -- both persistent and not count.
    """
    # looking into subdirectories
    glob_ptn = opj(repopath,
                   ARCHIVES_TEMP_DIR + {None: '*', True: '', False: '-*'}[persistent],
                   '*')
    dirs = glob.glob(glob_ptn)
    n2 = n * 2  # per each directory we should have a .stamp file
    assert_equal(len(dirs), n2,
                 msg="Found following dirs when needed %d of them: %s" % (n2, dirs))


def ok_exists(path):
    assert Path(path).exists(), 'path %s does not exist (or dangling symlink)' % path


def ok_file_has_content(path, content, strip=False, re_=False,
                        decompress=False, **kwargs):
    """Verify that file exists and has expected content"""
    path = Path(path)
    ok_exists(path)
    if decompress:
        if path.suffix == '.gz':
            open_func = gzip.open
        elif path.suffix in ('.xz', '.lzma'):
            open_func = lzma.open
        else:
            raise NotImplementedError("Don't know how to decompress %s" % path)
    else:
        open_func = open

    with open_func(str(path), 'rb') as f:
        file_content = f.read()

    if isinstance(content, str):
        file_content = ensure_unicode(file_content)

    if os.linesep != '\n':
        # for consistent comparisons etc. Apparently when reading in `b` mode
        # on Windows we would also get \r
        # https://github.com/datalad/datalad/pull/3049#issuecomment-444128715
        file_content = file_content.replace(os.linesep, '\n')

    if strip:
        file_content = file_content.strip()

    if re_:
        assert_re_in(content, file_content, **kwargs)
    else:
        assert_equal(content, file_content, **kwargs)


#
# Decorators
#


@optional_args
def with_tree(t, tree=None, archives_leading_dir=True, delete=True, **tkwargs):

    @wraps(t)
    def  _wrap_with_tree(*arg, **kw):
        if 'dir' not in tkwargs.keys():
            # if not specified otherwise, respect datalad.tests.temp.dir config
            # as this is a test helper
            tkwargs['dir'] = dl_cfg.get("datalad.tests.temp.dir")
        tkwargs_ = get_tempfile_kwargs(tkwargs, prefix="tree", wrapped=t)
        d = tempfile.mkdtemp(**tkwargs_)
        create_tree(d, tree, archives_leading_dir=archives_leading_dir)
        try:
            return t(*(arg + (d,)), **kw)
        finally:
            if delete:
                rmtemp(d)
    return  _wrap_with_tree


lgr = logging.getLogger('datalad.tests')


class SilentHTTPHandler(SimpleHTTPRequestHandler):
    """A little adapter to silence the handler
    """
    def __init__(self, *args, **kwargs):
        self._silent = lgr.getEffectiveLevel() > logging.DEBUG
        SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

    def log_message(self, format, *args):
        if self._silent:
            return
        lgr.debug("HTTP: " + format, *args)


def _multiproc_serve_path_via_http(hostname, path_to_serve_from, queue): # pragma: no cover
    chpwd(path_to_serve_from)
    httpd = HTTPServer((hostname, 0), SilentHTTPHandler)
    queue.put(httpd.server_port)
    httpd.serve_forever()


class HTTPPath(object):
    """Serve the content of a path via an HTTP URL.

    This class can be used as a context manager, in which case it returns the
    URL.

    Alternatively, the `start` and `stop` methods can be called directly.

    Parameters
    ----------
    path : str
        Directory with content to serve.
    """
    def __init__(self, path):
        self.path = path
        self.url = None
        self._env_patch = None
        self._mproc = None

    def __enter__(self):
        self.start()
        return self.url

    def __exit__(self, *args):
        self.stop()

    def start(self):
        """Start serving `path` via HTTP.
        """
        # There is a problem with Haskell on wheezy trying to
        # fetch via IPv6 whenever there is a ::1 localhost entry in
        # /etc/hosts.  Apparently fixing that docker image reliably
        # is not that straightforward, although see
        # http://jasonincode.com/customizing-hosts-file-in-docker/
        # so we just force to use 127.0.0.1 while on wheezy
        #hostname = '127.0.0.1' if on_debian_wheezy else 'localhost'
        hostname = '127.0.0.1'

        queue = multiprocessing.Queue()
        self._mproc = multiprocessing.Process(
            target=_multiproc_serve_path_via_http,
            args=(hostname, self.path, queue))
        self._mproc.start()
        port = queue.get(timeout=300)
        self.url = 'http://{}:{}/'.format(hostname, port)
        lgr.debug("HTTP: serving %s under %s", self.path, self.url)

        # Such tests don't require real network so if http_proxy settings were
        # provided, we remove them from the env for the duration of this run
        env = os.environ.copy()
        env.pop('http_proxy', None)
        self._env_patch = patch.dict('os.environ', env, clear=True)
        self._env_patch.start()

    def stop(self):
        """Stop serving `path`.
        """
        lgr.debug("HTTP: stopping server under %s", self.path)
        self._env_patch.stop()
        self._mproc.terminate()


@optional_args
def serve_path_via_http(tfunc, *targs):
    """Decorator which serves content of a directory via http url
    """

    @wraps(tfunc)
    @attr('serve_path_via_http')
    def  _wrap_serve_path_via_http(*args, **kwargs):

        if targs:
            # if a path is passed into serve_path_via_http, then it's in targs
            assert len(targs) == 1
            path = targs[0]

        elif len(args) > 1:
            args, path = args[:-1], args[-1]
        else:
            args, path = (), args[0]

        with HTTPPath(path) as url:
            return tfunc(*(args + (path, url)), **kwargs)
    return  _wrap_serve_path_via_http


@optional_args
def with_memory_keyring(t):
    """Decorator to use non-persistant MemoryKeyring instance
    """
    @wraps(t)
    @attr('with_memory_keyring')
    def  _wrap_with_memory_keyring(*args, **kwargs):
        keyring = MemoryKeyring()
        with patch("datalad.downloaders.credentials.keyring_", keyring):
            return t(*(args + (keyring,)), **kwargs)

    return  _wrap_with_memory_keyring


@optional_args
def without_http_proxy(tfunc):
    """Decorator to remove http*_proxy env variables for the duration of the test
    """
    
    @wraps(tfunc)
    @attr('without_http_proxy')
    def  _wrap_without_http_proxy(*args, **kwargs):
        if on_windows:
            raise SkipTest('Unclear why this is not working on windows')
        # Such tests don't require real network so if http_proxy settings were
        # provided, we remove them from the env for the duration of this run
        env = os.environ.copy()
        env.pop('http_proxy', None)
        env.pop('https_proxy', None)
        with patch.dict('os.environ', env, clear=True):
            return tfunc(*args, **kwargs)

    return  _wrap_without_http_proxy


@borrowkwargs(methodname=make_tempfile)
@optional_args
def with_tempfile(t, **tkwargs):
    """Decorator function to provide a temporary file name and remove it at the end

    Parameters
    ----------

    To change the used directory without providing keyword argument 'dir' set
    DATALAD_TESTS_TEMP_DIR.

    Examples
    --------

    ::

        @with_tempfile
        def test_write(tfile):
            open(tfile, 'w').write('silly test')
    """

    @wraps(t)
    def  _wrap_with_tempfile(*arg, **kw):
        if 'dir' not in tkwargs.keys():
            # if not specified otherwise, respect datalad.tests.temp.dir config
            # as this is a test helper
            tkwargs['dir'] = dl_cfg.get("datalad.tests.temp.dir")
        with make_tempfile(wrapped=t, **tkwargs) as filename:
            return t(*(arg + (filename,)), **kw)

    return  _wrap_with_tempfile


# ### ###
# START known failure decorators
# ### ###

def probe_known_failure(func):
    """Test decorator allowing the test to pass when it fails and vice versa

    Setting config datalad.tests.knownfailures.probe to True tests, whether or
    not the test is still failing. If it's not, an AssertionError is raised in
    order to indicate that the reason for failure seems to be gone.
    """

    @wraps(func)
    @attr('probe_known_failure')
    def  _wrap_probe_known_failure(*args, **kwargs):
        if dl_cfg.obtain("datalad.tests.knownfailures.probe"):
            assert_raises(Exception, func, *args, **kwargs)  # marked as known failure
            # Note: Since assert_raises lacks a `msg` argument, a comment
            # in the same line is helpful to determine what's going on whenever
            # this assertion fails and we see a trace back. Otherwise that line
            # wouldn't be very telling.
        else:
            return func(*args, **kwargs)
    return  _wrap_probe_known_failure


@optional_args
def skip_known_failure(func, method='raise'):
    """Test decorator allowing to skip a test that is known to fail

    Setting config datalad.tests.knownfailures.skip to a bool enables/disables
    skipping.
    """

    @skip_if(cond=dl_cfg.obtain("datalad.tests.knownfailures.skip"),
             msg="Skip test known to fail",
             method=method)
    @wraps(func)
    @attr('skip_known_failure')
    def  _wrap_skip_known_failure(*args, **kwargs):
        return func(*args, **kwargs)
    return  _wrap_skip_known_failure


def known_failure(func):
    """Test decorator marking a test as known to fail

    This combines `probe_known_failure` and `skip_known_failure` giving the
    skipping precedence over the probing.
    """

    @skip_known_failure
    @probe_known_failure
    @wraps(func)
    @attr('known_failure')
    def  _wrap_known_failure(*args, **kwargs):
        return func(*args, **kwargs)
    return  _wrap_known_failure


def known_failure_direct_mode(func):
    """DEPRECATED.  Stop using.  Does nothing

    Test decorator marking a test as known to fail in a direct mode test run

    If datalad.repo.direct is set to True behaves like `known_failure`.
    Otherwise the original (undecorated) function is returned.
    """
    # TODO: consider adopting   nibabel/deprecated.py  nibabel/deprecator.py
    # mechanism to consistently deprecate functionality and ensure they are
    # displayed.
    # Since 2.7 Deprecation warnings aren't displayed by default
    # and thus kinda pointless to issue a warning here, so we will just log
    msg = "Direct mode support is deprecated, so no point in using " \
          "@known_failure_direct_mode for %r since glorious future " \
          "DataLad 0.12" % func.__name__
    lgr.warning(msg)
    return func


def known_failure_windows(func):
    """Test decorator marking a test as known to fail on windows

    On Windows behaves like `known_failure`.
    Otherwise the original (undecorated) function is returned.
    """
    if on_windows:

        @known_failure
        @wraps(func)
        @attr('known_failure_windows')
        @attr('windows')
        def dm_func(*args, **kwargs):
            return func(*args, **kwargs)

        return dm_func
    return func


def known_failure_githubci_win(func):
    """Test decorator for a known test failure on Github's Windows CI
    """
    if 'GITHUB_WORKFLOW' in os.environ and on_windows:
        @known_failure
        @wraps(func)
        @attr('known_failure_githubci_win')
        @attr('githubci_win')
        def dm_func(*args, **kwargs):
            return func(*args, **kwargs)
        return dm_func
    return func


def known_failure_githubci_osx(func):
    """Test decorator for a known test failure on Github's macOS CI
    """
    if 'GITHUB_WORKFLOW' in os.environ and on_osx:
        @known_failure
        @wraps(func)
        @attr('known_failure_githubci_osx')
        @attr('githubci_osx')
        def dm_func(*args, **kwargs):
            return func(*args, **kwargs)
        return dm_func
    return func


def known_failure_osx(func):
    """Test decorator for a known test failure on macOS
    """
    if on_osx:
        @known_failure
        @wraps(func)
        @attr('known_failure_osx')
        @attr('osx')
        def dm_func(*args, **kwargs):
            return func(*args, **kwargs)
        return dm_func
    return func

# ### ###
# END known failure decorators
# ### ###


def _get_resolved_flavors(flavors):
    #flavors_ = (['local', 'clone'] + (['local-url'] if not on_windows else [])) \
    #           if flavors == 'auto' else flavors
    flavors_ = (['local', 'clone', 'local-url', 'network'] if not on_windows
                else ['network', 'network-clone']) \
               if flavors == 'auto' else flavors

    if not isinstance(flavors_, list):
        flavors_ = [flavors_]

    if dl_cfg.get('datalad.tests.nonetwork'):
        flavors_ = [x for x in flavors_ if not x.startswith('network')]
    return flavors_


def clone_url(url):
    runner = GitWitlessRunner()
    tdir = tempfile.mkdtemp(**get_tempfile_kwargs(
        {'dir': dl_cfg.get("datalad.tests.temp.dir")}, prefix='clone_url'))
    runner.run(["git", "clone", url, tdir], protocol=KillOutput)
    if GitRepo(tdir).is_with_annex():
        AnnexRepo(tdir, init=True)
    _TEMP_PATHS_CLONES.add(tdir)
    return tdir


local_testrepo_flavors = ['local'] # 'local-url'

_TESTREPOS = None

def _get_testrepos_uris(regex, flavors):
    global _TESTREPOS
    # we should instantiate those whenever test repos actually asked for
    # TODO: just absorb all this lazy construction within some class
    if not _TESTREPOS:
        from .utils_testrepos import BasicAnnexTestRepo, BasicGitTestRepo, \
            SubmoduleDataset, NestedDataset, InnerSubmodule

        _basic_annex_test_repo = BasicAnnexTestRepo()
        _basic_git_test_repo = BasicGitTestRepo()
        _submodule_annex_test_repo = SubmoduleDataset()
        _nested_submodule_annex_test_repo = NestedDataset()
        _inner_submodule_annex_test_repo = InnerSubmodule()
        _TESTREPOS = {'basic_annex':
                        {'network': 'git://github.com/datalad/testrepo--basic--r1',
                         'local': _basic_annex_test_repo.path,
                         'local-url': _basic_annex_test_repo.url},
                      'basic_git':
                        {'local': _basic_git_test_repo.path,
                         'local-url': _basic_git_test_repo.url},
                      'submodule_annex':
                        {'local': _submodule_annex_test_repo.path,
                         'local-url': _submodule_annex_test_repo.url},
                      'nested_submodule_annex':
                        {'local': _nested_submodule_annex_test_repo.path,
                         'local-url': _nested_submodule_annex_test_repo.url},
                      # TODO: append 'annex' to the name:
                      # Currently doesn't work with some annex tests, despite
                      # working manually. So, figure out how the tests' setup
                      # messes things up with this one.
                      'inner_submodule':
                        {'local': _inner_submodule_annex_test_repo.path,
                         'local-url': _inner_submodule_annex_test_repo.url}
                      }
        # assure that now we do have those test repos created -- delayed
        # their creation until actually used
        _basic_annex_test_repo.create()
        _basic_git_test_repo.create()
        _submodule_annex_test_repo.create()
        _nested_submodule_annex_test_repo.create()
        _inner_submodule_annex_test_repo.create()
    uris = []
    for name, spec in _TESTREPOS.items():
        if not re.match(regex, name):
            continue
        uris += [spec[x] for x in set(spec.keys()).intersection(flavors)]

        # additional flavors which might have not been
        if 'clone' in flavors and 'clone' not in spec:
            uris.append(clone_url(spec['local']))

        if 'network-clone' in flavors \
                and 'network' in spec \
                and 'network-clone' not in spec:
            uris.append(clone_url(spec['network']))

    return uris


@optional_args
def with_testrepos(t, regex='.*', flavors='auto', skip=False, count=None):
    """Decorator to provide a local/remote test repository

    All tests under datalad/tests/testrepos are stored in two-level hierarchy,
    where top-level name describes nature/identifier of the test repository,
    and there could be multiple instances (e.g. generated differently) of the
    same "content"

    Parameters
    ----------
    regex : string, optional
      Regex to select which test repos to use
    flavors : {'auto', 'local', 'local-url', 'clone', 'network', 'network-clone'} or list of thereof, optional
      What URIs to provide.  E.g. 'local' would just provide path to the
      repository, while 'network' would provide url of the remote location
      available on Internet containing the test repository.  'clone' would
      clone repository first to a temporary location. 'network-clone' would
      first clone from the network location. 'auto' would include the list of
      appropriate ones (e.g., no 'network*' flavors if network tests are
      "forbidden").
    count: int, optional
      If specified, only up to that number of repositories to test with

    Examples
    --------

    >>> from datalad.tests.utils import with_testrepos
    >>> @with_testrepos('basic_annex')
    ... def test_write(repo):
    ...    assert(os.path.exists(os.path.join(repo, '.git', 'annex')))

    """
    @wraps(t)
    @attr('with_testrepos')
    def  _wrap_with_testrepos(*arg, **kw):
        # addurls with our generated file:// URLs doesn't work on appveyor
        # https://ci.appveyor.com/project/mih/datalad/builds/29841505/job/330rwn2a3cvtrakj
        #if 'APPVEYOR' in os.environ:
        #    raise SkipTest("Testrepo setup is broken on AppVeyor")
        # TODO: would need to either avoid this "decorator" approach for
        # parametric tests or again aggregate failures like sweepargs does
        flavors_ = _get_resolved_flavors(flavors)

        testrepos_uris = _get_testrepos_uris(regex, flavors_)
        # we should always have at least one repo to test on, unless explicitly only
        # network was requested by we are running without networked tests
        if not (dl_cfg.get('datalad.tests.nonetwork') and flavors == ['network']):
            assert(testrepos_uris)
        else:
            if not testrepos_uris:
                raise SkipTest("No non-networked repos to test on")

        fake_dates = dl_cfg.get("datalad.fake-dates")
        ntested = 0
        for uri in testrepos_uris:
            if count and ntested >= count:
                break
            ntested += 1
            if __debug__:
                lgr.debug('Running %s on %s', t.__name__, uri)
            try:
                t(*(arg + (uri,)), **kw)
            finally:
                # The is_explicit_path check is needed because it may be a URL,
                # but check_dates needs a local path or GitRepo object.
                if fake_dates and is_explicit_path(uri):
                    from ..support.repodates import check_dates
                    assert_false(
                        check_dates(uri, annex="tree")["objects"])
                if uri in _TEMP_PATHS_CLONES:
                    _TEMP_PATHS_CLONES.discard(uri)
                    rmtemp(uri)
                pass  # might need to provide additional handling so, handle
    return  _wrap_with_testrepos
with_testrepos.__test__ = False


@optional_args
def with_sameas_remote(func, autoenabled=False):
    """Provide a repository with a git-annex sameas remote configured.

    The repository will have two special remotes: r_dir (type=directory) and
    r_rsync (type=rsync). The rsync remote will be configured with
    --sameas=r_dir, and autoenabled if `autoenabled` is true.
    """
    from datalad.support.annexrepo import AnnexRepo
    from datalad.support.exceptions import CommandError

    @wraps(func)
    @attr('with_sameas_remotes')
    @skip_if_on_windows
    @skip_ssh
    @with_tempfile(mkdir=True)
    @with_tempfile(mkdir=True)
    def  _wrap_with_sameas_remote(*args, **kwargs):
        # With git-annex's 8.20200522-77-g1f2e2d15e, transferring from an rsync
        # special remote hangs on Xenial. This is likely due to an interaction
        # with an older rsync or openssh version. Use openssh as a rough
        # indicator. See
        # https://git-annex.branchable.com/bugs/Recent_hang_with_rsync_remote_with_older_systems___40__Xenial__44___Jessie__41__/
        if external_versions['cmd:system-ssh'] < '7.4' and \
           '8.20200522' < external_versions['cmd:annex'] < '8.20200720':
            raise SkipTest("Test known to hang")

        sr_path, repo_path = args[-2:]
        fn_args = args[:-2]
        repo = AnnexRepo(repo_path)
        repo.init_remote("r_dir",
                         options=["type=directory",
                                  "encryption=none",
                                  "directory=" + sr_path])
        options = ["type=rsync",
                   "rsyncurl=datalad-test:" + sr_path]
        if autoenabled:
            options.append("autoenable=true")
        options.append("--sameas=r_dir")
        repo.init_remote("r_rsync", options=options)
        return func(*(fn_args + (repo,)), **kwargs)
    return  _wrap_with_sameas_remote


@optional_args
def with_fake_cookies_db(func, cookies={}):
    """mock original cookies db with a fake one for the duration of the test
    """
    from ..support.cookies import cookies_db

    @wraps(func)
    @attr('with_fake_cookies_db')
    def  _wrap_with_fake_cookies_db(*args, **kwargs):
        try:
            orig_cookies_db = cookies_db._cookies_db
            cookies_db._cookies_db = cookies.copy()
            return func(*args, **kwargs)
        finally:
            cookies_db._cookies_db = orig_cookies_db
    return  _wrap_with_fake_cookies_db


@optional_args
def assert_cwd_unchanged(func, ok_to_chdir=False):
    """Decorator to test whether the current working directory remains unchanged

    Parameters
    ----------
    ok_to_chdir: bool, optional
      If True, allow to chdir, so this decorator would not then raise exception
      if chdir'ed but only return to original directory
    """

    @wraps(func)
    def  _wrap_assert_cwd_unchanged(*args, **kwargs):
        cwd_before = os.getcwd()
        pwd_before = getpwd()
        exc_info = None
        # record previous state of PWD handling
        utils_pwd_mode = utils._pwd_mode
        try:
            ret = func(*args, **kwargs)
        except:
            exc_info = sys.exc_info()
        finally:
            utils._pwd_mode = utils_pwd_mode
            try:
                cwd_after = os.getcwd()
            except OSError as e:
                lgr.warning("Failed to getcwd: %s" % e)
                cwd_after = None

        if cwd_after != cwd_before:
            chpwd(pwd_before)
            # Above chpwd could also trigger the change of _pwd_mode, so we
            # would need to reset it again since we know that it is all kosher
            utils._pwd_mode = utils_pwd_mode
            if not ok_to_chdir:
                lgr.warning(
                    "%s changed cwd to %s. Mitigating and changing back to %s"
                    % (func, cwd_after, pwd_before))
                # If there was already exception raised, we better reraise
                # that one since it must be more important, so not masking it
                # here with our assertion
                if exc_info is None:
                    assert_equal(cwd_before, cwd_after,
                                 "CWD changed from %s to %s" % (cwd_before, cwd_after))

        if exc_info is not None:
            raise exc_info[1]

        return ret

    return  _wrap_assert_cwd_unchanged


@optional_args
def run_under_dir(func, newdir='.'):
    """Decorator to run tests under another directory

    It is somewhat ugly since we can't really chdir
    back to a directory which had a symlink in its path.
    So using this decorator has potential to move entire
    testing run under the dereferenced directory name -- sideeffect.

    The only way would be to instruct testing framework (i.e. nose
    in our case ATM) to run a test by creating a new process with
    a new cwd
    """

    @wraps(func)
    def  _wrap_run_under_dir(*args, **kwargs):
        pwd_before = getpwd()
        try:
            chpwd(newdir)
            func(*args, **kwargs)
        finally:
            chpwd(pwd_before)


    return  _wrap_run_under_dir


def assert_re_in(regex, c, flags=0, match=True, msg=None):
    """Assert that container (list, str, etc) contains entry matching the regex
    """
    if not isinstance(c, (list, tuple)):
        c = [c]
    for e in c:
        if (re.match if match else re.search)(regex, e, flags=flags):
            return
    raise AssertionError(
        msg or "Not a single entry matched %r in %r" % (regex, c)
    )


def assert_dict_equal(d1, d2):
    msgs = []
    if set(d1).difference(d2):
        msgs.append(" keys in the first dict but not in the second: %s"
                    % list(set(d1).difference(d2)))
    if set(d2).difference(d1):
        msgs.append(" keys in the second dict but not in the first: %s"
                    % list(set(d2).difference(d1)))
    for k in set(d1).intersection(d2):
        same = True
        try:
            if isinstance(d1[k], str):
                # do not compare types for string types to avoid all the hassle
                # with the distinction of str and unicode in PY3, and simple
                # test for equality
                same = bool(d1[k] == d2[k])
            else:
                same = type(d1[k]) == type(d2[k]) and bool(d1[k] == d2[k])
        except:  # if comparison or conversion to bool (e.g. with numpy arrays) fails
            same = False

        if not same:
            msgs.append(" [%r] differs: %r != %r" % (k, d1[k], d2[k]))

        if len(msgs) > 10:
            msgs.append("and more")
            break
    if msgs:
        raise AssertionError("dicts differ:\n%s" % "\n".join(msgs))
    # do generic comparison just in case we screwed up to detect difference correctly above
    eq_(d1, d2)


def assert_str_equal(s1, s2):
    """Helper to compare two lines"""
    diff = list(unified_diff(s1.splitlines(), s2.splitlines()))
    assert not diff, '\n'.join(diff)
    assert_equal(s1, s2)


def assert_status(label, results):
    """Verify that each status dict in the results has a given status label

    `label` can be a sequence, in which case status must be one of the items
    in this sequence.
    """
    label = ensure_list(label)
    results = ensure_list(results)
    for i, r in enumerate(results):
        try:
            assert_in('status', r)
            assert_in(r['status'], label)
        except AssertionError:
            raise AssertionError('Test {}/{}: expected status {} not found in:\n{}'.format(
                i + 1,
                len(results),
                label,
                dumps(results, indent=1, default=lambda x: str(x))))


def assert_message(message, results):
    """Verify that each status dict in the results has a message

    This only tests the message template string, and not a formatted message
    with args expanded.
    """
    for r in ensure_list(results):
        assert_in('message', r)
        m = r['message'][0] if isinstance(r['message'], tuple) else r['message']
        assert_equal(m, message)


def _format_res(x):
    return textwrap.indent(
        dumps(x, indent=1, default=str, sort_keys=True),
        prefix="  ")


def assert_result_count(results, n, **kwargs):
    """Verify specific number of results (matching criteria, if any)"""
    count = 0
    results = ensure_list(results)
    for r in results:
        if not len(kwargs):
            count += 1
        elif all(k in r and r[k] == v for k, v in kwargs.items()):
            count += 1
    if not n == count:
        raise AssertionError(
            'Got {} instead of {} expected results matching\n{}\nInspected {} record(s):\n{}'.format(
                count,
                n,
                _format_res(kwargs),
                len(results),
                _format_res(results)))


def _check_results_in(should_contain, results, **kwargs):
    found = False
    for r in ensure_list(results):
        if all(k in r and r[k] == v for k, v in kwargs.items()):
            found = True
            break
    if found ^ should_contain:
        if should_contain:
            msg = "Desired result\n{}\nnot found among\n{}"
        else:
            msg = "Result\n{}\nunexpectedly found among\n{}"
        raise AssertionError(msg.format(_format_res(kwargs),
                                        _format_res(results)))


def assert_in_results(results, **kwargs):
    """Verify that the particular combination of keys and values is found in
    one of the results"""
    _check_results_in(True, results, **kwargs)


def assert_not_in_results(results, **kwargs):
    """Verify that the particular combination of keys and values is not in any
    of the results"""
    _check_results_in(False, results, **kwargs)


def assert_result_values_equal(results, prop, values):
    """Verify that the values of all results for a given key in the status dicts
    match the given sequence"""
    assert_equal(
        [r[prop] for r in results],
        values)


def assert_result_values_cond(results, prop, cond):
    """Verify that the values of all results for a given key in the status dicts
    fulfill condition `cond`.

    Parameters
    ----------
    results:
    prop: str
    cond: callable
    """
    for r in ensure_list(results):
        ok_(cond(r[prop]),
            msg="r[{prop}]: {value}".format(prop=prop, value=r[prop]))


def ignore_nose_capturing_stdout(func):
    """DEPRECATED and will be removed soon.  Does nothing!

    Originally was intended as a decorator workaround for nose's behaviour
    with redirecting sys.stdout, but now we monkey patch nose now so no test
    should no longer be skipped.

    See issue reported here:
    https://code.google.com/p/python-nose/issues/detail?id=243&can=1&sort=-id&colspec=ID%20Type%20Status%20Priority%20Stars%20Milestone%20Owner%20Summary

    """
    lgr.warning(
        "@ignore_nose_capturing_stdout no longer does anything - nose should "
        "just be monkey patched in setup_package. {} still has it"
        .format(func.__name__)
    )
    return func


def skip_httpretty_on_problematic_pythons(func):
    """As discovered some httpretty bug causes a side-effect
    on other tests on some Pythons.  So we skip the test if such
    problematic combination detected

    References
    https://travis-ci.org/datalad/datalad/jobs/94464988
    http://stackoverflow.com/a/29603206/1265472
    """

    @make_decorator(func)
    def  _wrap_skip_httpretty_on_problematic_pythons(*args, **kwargs):
        if sys.version_info[:3] == (3, 4, 2):
            raise SkipTest("Known to cause trouble due to httpretty bug on this Python")
        return func(*args, **kwargs)
    return  _wrap_skip_httpretty_on_problematic_pythons


@optional_args
def with_parametric_batch(t):
    """Helper to run parametric test with possible combinations of batch and direct
    """
    @wraps(t)
    def  _wrap_with_parametric_batch():
        for batch in (False, True):
                yield t, batch

    return  _wrap_with_parametric_batch


# List of most obscure filenames which might or not be supported by different
# filesystems across different OSs.  Start with the most obscure
OBSCURE_PREFIX = os.getenv('DATALAD_TESTS_OBSCURE_PREFIX', '')
# Those will be tried to be added to the base name if filesystem allows
OBSCURE_FILENAME_PARTS = [' ', '/', '|', ';', '&', '%b5', '{}', "'", '"']
UNICODE_FILENAME = u"ΔЙקم๗あ"

# OSX is exciting -- some I guess FS might be encoding differently from decoding
# so Й might get recoded
# (ref: https://github.com/datalad/datalad/pull/1921#issuecomment-385809366)
if sys.getfilesystemencoding().lower() == 'utf-8':
    if on_osx:
        # TODO: figure it really out
        UNICODE_FILENAME = UNICODE_FILENAME.replace(u"Й", u"")
    if on_windows:
        # TODO: really figure out unicode handling on windows
        UNICODE_FILENAME = ''
    if UNICODE_FILENAME:
        OBSCURE_FILENAME_PARTS.append(UNICODE_FILENAME)
# space before extension, simple extension and trailing space to finish it up
OBSCURE_FILENAME_PARTS += [' ', '.datc', ' ']


@with_tempfile(mkdir=True)
def get_most_obscure_supported_name(tdir, return_candidates=False):
    """Return the most obscure filename that the filesystem would support under TEMPDIR

    Parameters
    ----------
    return_candidates: bool, optional
      if True, return a tuple of (good, candidates) where candidates are "partially"
      sorted from trickiest considered
    TODO: we might want to use it as a function where we would provide tdir
    """
    # we need separate good_base so we do not breed leading/trailing spaces
    initial = good = OBSCURE_PREFIX
    system = platform.system()

    OBSCURE_FILENAMES = []
    def good_filename(filename):
        OBSCURE_FILENAMES.append(candidate)
        try:
            # Windows seems to not tollerate trailing spaces and
            # ATM we do not distinguish obscure filename and dirname.
            # So here we will test for both - being able to create dir
            # with obscure name and obscure filename under
            os.mkdir(opj(tdir, filename))
            with open(opj(tdir, filename, filename), 'w') as f:
                f.write("TEST LOAD")
            return True
        except:
            lgr.debug("Filename %r is not supported on %s under %s",
                      filename, system, tdir)
            return False

    # incrementally build up the most obscure filename from parts
    for part in OBSCURE_FILENAME_PARTS:
        candidate = good + part
        if good_filename(candidate):
            good = candidate

    if good == initial:
        raise RuntimeError("Could not create any of the files under %s among %s"
                       % (tdir, OBSCURE_FILENAMES))
    lgr.debug("Tested %d obscure filename candidates. The winner: %r", len(OBSCURE_FILENAMES), good)
    if return_candidates:
        return good, OBSCURE_FILENAMES[::-1]
    else:
        return good


OBSCURE_FILENAME, OBSCURE_FILENAMES = get_most_obscure_supported_name(return_candidates=True)


@optional_args
def with_testsui(t, responses=None, interactive=True):
    """Switch main UI to be 'tests' UI and possibly provide answers to be used"""

    @wraps(t)
    def  _wrap_with_testsui(*args, **kwargs):
        from datalad.ui import ui
        old_backend = ui.backend
        try:
            ui.set_backend('tests' if interactive else 'tests-noninteractive')
            if responses:
                ui.add_responses(responses)
            ret = t(*args, **kwargs)
            if responses:
                responses_left = ui.get_responses()
                assert not len(responses_left), "Some responses were left not used: %s" % str(responses_left)
            return ret
        finally:
            ui.set_backend(old_backend)

    if not interactive and responses is not None:
        raise ValueError("Non-interactive UI cannot provide responses")

    return  _wrap_with_testsui

with_testsui.__test__ = False


def assert_no_errors_logged(func, skip_re=None):
    """Decorator around function to assert that no errors logged during its execution"""
    @wraps(func)
    def  _wrap_assert_no_errors_logged(*args, **kwargs):
        with swallow_logs(new_level=logging.ERROR) as cml:
            out = func(*args, **kwargs)
            if cml.out:
                if not (skip_re and re.search(skip_re, cml.out)):
                    raise AssertionError(
                        "Expected no errors to be logged, but log output is %s"
                        % cml.out
                    )
        return out

    return  _wrap_assert_no_errors_logged


def get_mtimes_and_digests(target_path):
    """Return digests (md5) and mtimes for all the files under target_path"""
    from datalad.utils import find_files
    from datalad.support.digests import Digester
    digester = Digester(['md5'])

    # bother only with existing ones for this test, i.e. skip annexed files without content
    target_files = [
        f for f in find_files('.*', topdir=target_path, exclude_vcs=False, exclude_datalad=False)
        if exists(f)
    ]
    # let's leave only relative paths for easier analysis
    target_files_ = [relpath(f, target_path) for f in target_files]

    digests = {frel: digester(f) for f, frel in zip(target_files, target_files_)}
    mtimes = {frel: os.stat(f).st_mtime for f, frel in zip(target_files, target_files_)}
    return digests, mtimes


def get_datasets_topdir():
    """Delayed parsing so it could be monkey patched etc"""
    from datalad.consts import DATASETS_TOPURL
    return RI(DATASETS_TOPURL).hostname


def assert_repo_status(path, annex=None, untracked_mode='normal', **kwargs):
    """Compare a repo status against (optional) exceptions.

    Anything file/directory that is not explicitly indicated must have
    state 'clean', i.e. no modifications and recorded in Git.

    Parameters
    ----------
    path: str or Repo
      in case of a str: path to the repository's base dir;
      Note, that passing a Repo instance prevents detecting annex. This might
      be useful in case of a non-initialized annex, a GitRepo is pointing to.
    annex: bool or None
      explicitly set to True or False to indicate, that an annex is (not)
      expected; set to None to autodetect, whether there is an annex.
      Default: None.
    untracked_mode: {'no', 'normal', 'all'}
      If and how untracked content is reported. The specification of untracked
      files that are OK to be found must match this mode. See `Repo.status()`
    **kwargs
      Files/directories that are OK to not be in 'clean' state. Each argument
      must be one of 'added', 'untracked', 'deleted', 'modified' and each
      value must be a list of filenames (relative to the root of the
      repository, in POSIX convention).
    """
    r = None
    if isinstance(path, AnnexRepo):
        if annex is None:
            annex = True
        # if `annex` was set to False, but we find an annex => fail
        assert_is(annex, True)
        r = path
    elif isinstance(path, GitRepo):
        if annex is None:
            annex = False
        # explicitly given GitRepo instance doesn't make sense with
        # 'annex' True
        assert_is(annex, False)
        r = path
    else:
        # 'path' is an actual path
        try:
            r = AnnexRepo(path, init=False, create=False)
            if annex is None:
                annex = True
            # if `annex` was set to False, but we find an annex => fail
            assert_is(annex, True)
        except Exception:
            # Instantiation failed => no annex
            try:
                r = GitRepo(path, init=False, create=False)
            except Exception:
                raise AssertionError("Couldn't find an annex or a git "
                                     "repository at {}.".format(path))
            if annex is None:
                annex = False
            # explicitly given GitRepo instance doesn't make sense with
            # 'annex' True
            assert_is(annex, False)

    status = r.status(untracked=untracked_mode)
    # for any file state that indicates some kind of change (all but 'clean)
    for state in ('added', 'untracked', 'deleted', 'modified'):
        oktobefound = sorted(r.pathobj.joinpath(ut.PurePosixPath(p))
                             for p in kwargs.get(state, []))
        state_files = sorted(k for k, v in status.items()
                             if v.get('state', None) == state)
        eq_(state_files, oktobefound,
            'unexpected content of state "%s": %r != %r'
            % (state, state_files, oktobefound))


def get_convoluted_situation(path, repocls=AnnexRepo):
    from datalad.api import create

    #if 'APPVEYOR' in os.environ:
    #    # issue only happens on appveyor, Python itself implodes
    #    # cannot be reproduced on a real windows box
    #    raise SkipTest(
    #        'get_convoluted_situation() causes appveyor to crash, '
    #        'reason unknown')
    repo = repocls(path, create=True)
    # use create(force) to get an ID and config into the empty repo
    ds = Dataset(path).create(force=True)
    # base content
    create_tree(
        ds.path,
        {
            '.gitignore': '*.ignored',
            'subdir': {
                'file_clean': 'file_clean',
                'file_deleted': 'file_deleted',
                'file_modified': 'file_clean',
            },
            'subdir-only-ignored': {
                '1.ignored': '',
            },
            'file_clean': 'file_clean',
            'file_deleted': 'file_deleted',
            'file_staged_deleted': 'file_staged_deleted',
            'file_modified': 'file_clean',
        }
    )
    if isinstance(ds.repo, AnnexRepo):
        create_tree(
            ds.path,
            {
                'subdir': {
                    'file_dropped_clean': 'file_dropped_clean',
                },
                'file_dropped_clean': 'file_dropped_clean',
            }
        )
    ds.save()
    if isinstance(ds.repo, AnnexRepo):
        # some files straight in git
        create_tree(
            ds.path,
            {
                'subdir': {
                    'file_ingit_clean': 'file_ingit_clean',
                    'file_ingit_modified': 'file_ingit_clean',
                },
                'file_ingit_clean': 'file_ingit_clean',
                'file_ingit_modified': 'file_ingit_clean',
            }
        )
        ds.save(to_git=True)
        ds.drop([
            'file_dropped_clean',
            opj('subdir', 'file_dropped_clean')],
            check=False)
    # clean and proper subdatasets
    ds.create('subds_clean')
    ds.create(opj('subdir', 'subds_clean'))
    ds.create('subds_unavailable_clean')
    ds.create(opj('subdir', 'subds_unavailable_clean'))
    # uninstall some subdatasets (still clean)
    ds.uninstall([
        'subds_unavailable_clean',
        opj('subdir', 'subds_unavailable_clean')],
        check=False)
    assert_repo_status(ds.path)
    # make a dirty subdataset
    ds.create('subds_modified')
    ds.create(opj('subds_modified', 'someds'))
    ds.create(opj('subds_modified', 'someds', 'dirtyds'))
    # make a subdataset with additional commits
    ds.create(opj('subdir', 'subds_modified'))
    pdspath = opj(ds.path, 'subdir', 'subds_modified', 'progressedds')
    ds.create(pdspath)
    create_tree(
        pdspath,
        {'file_clean': 'file_ingit_clean'}
    )
    Dataset(pdspath).save()
    assert_repo_status(pdspath)
    # staged subds, and files
    create(opj(ds.path, 'subds_added'))
    ds.repo.add_submodule('subds_added')
    create(opj(ds.path, 'subdir', 'subds_added'))
    ds.repo.add_submodule(opj('subdir', 'subds_added'))
    # some more untracked files
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_untracked': 'file_untracked',
                'file_added': 'file_added',
            },
            'file_untracked': 'file_untracked',
            'file_added': 'file_added',
            'dir_untracked': {
                'file_untracked': 'file_untracked',
            },
            'subds_modified': {
                'someds': {
                    "dirtyds": {
                        'file_untracked': 'file_untracked',
                    },
                },
            },
        }
    )
    ds.repo.add(['file_added', opj('subdir', 'file_added')])
    # untracked subdatasets
    create(opj(ds.path, 'subds_untracked'))
    create(opj(ds.path, 'subdir', 'subds_untracked'))
    # deleted files
    os.remove(opj(ds.path, 'file_deleted'))
    os.remove(opj(ds.path, 'subdir', 'file_deleted'))
    # staged deletion
    ds.repo.remove('file_staged_deleted')
    # modified files
    if isinstance(ds.repo, AnnexRepo):
        ds.repo.unlock(['file_modified', opj('subdir', 'file_modified')])
        create_tree(
            ds.path,
            {
                'subdir': {
                    'file_ingit_modified': 'file_ingit_modified',
                },
                'file_ingit_modified': 'file_ingit_modified',
            }
        )
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_modified': 'file_modified',
            },
            'file_modified': 'file_modified',
        }
    )
    return ds


def get_deeply_nested_structure(path):
    """ Here is what this does (assuming UNIX, locked):
    |  .
    |  ├── directory_untracked
    |  │   └── link2dir -> ../subdir
    |  ├── OBSCURE_FILENAME_file_modified
    |  ├── link2dir -> subdir
    |  ├── link2subdsdir -> subds_modified/subdir
    |  ├── link2subdsroot -> subds_modified
    |  ├── subdir
    |  │   ├── annexed_file.txt -> ../.git/annex/objects/...
    |  │   ├── file_modified
    |  │   ├── git_file.txt
    |  │   └── link2annex_files.txt -> annexed_file.txt
    |  └── subds_modified
    |      ├── link2superdsdir -> ../subdir
    |      ├── subdir
    |      │   └── annexed_file.txt -> ../.git/annex/objects/...
    |      └── subds_lvl1_modified
    |          └── OBSCURE_FILENAME_directory_untracked
    |              └── untracked_file

    When a system has no symlink support, the link2... components are not
    included.
    """
    ds = Dataset(path).create()
    (ds.pathobj / 'subdir').mkdir()
    (ds.pathobj / 'subdir' / 'annexed_file.txt').write_text(u'dummy')
    ds.save()
    (ds.pathobj / 'subdir' / 'git_file.txt').write_text(u'dummy')
    ds.save(to_git=True)
    # a subtree of datasets
    subds = ds.create('subds_modified')
    # another dataset, plus an additional dir in it
    ds.create(opj('subds_modified', 'subds_lvl1_modified'))
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_modified': 'file_modified',
            },
            OBSCURE_FILENAME + u'file_modified_': 'file_modified',
        }
    )
    create_tree(
        str(ds.pathobj / 'subds_modified' / 'subds_lvl1_modified'),
        {OBSCURE_FILENAME + u'_directory_untracked': {"untraced_file": ""}}
    )
    (ut.Path(subds.path) / 'subdir').mkdir()
    (ut.Path(subds.path) / 'subdir' / 'annexed_file.txt').write_text(u'dummy')
    subds.save()
    (ds.pathobj / 'directory_untracked').mkdir()

    if not has_symlink_capability():
        return ds

    # symlink farm #1
    # symlink to annexed file
    (ds.pathobj / 'subdir' / 'link2annex_files.txt').symlink_to(
        'annexed_file.txt')
    # symlink to directory within the dataset
    (ds.pathobj / 'link2dir').symlink_to('subdir')
    # upwards pointing symlink to directory within the same dataset
    (ds.pathobj / 'directory_untracked' / 'link2dir').symlink_to(
        opj('..', 'subdir'))
    # symlink pointing to a subdataset mount in the same dataset
    (ds.pathobj / 'link2subdsroot').symlink_to('subds_modified')
    # symlink to a dir in a subdataset (across dataset boundaries)
    (ds.pathobj / 'link2subdsdir').symlink_to(
        opj('subds_modified', 'subdir'))
    # symlink to a dir in a superdataset (across dataset boundaries)
    (ut.Path(subds.path) / 'link2superdsdir').symlink_to(
        opj('..', 'subdir'))
    return ds


def maybe_adjust_repo(repo):
    """Put repo into an adjusted branch if it is not already.
    """
    if not repo.is_managed_branch():
        repo.call_annex(["upgrade"])
        repo.config.reload(force=True)
        repo.adjust()


@with_tempfile
@with_tempfile
def has_symlink_capability(p1, p2):

    path = ut.Path(p1)
    target = ut.Path(p2)
    return utils.check_symlink_capability(path, target)


def skip_wo_symlink_capability(func):
    """Skip test when environment does not support symlinks

    Perform a behavioral test instead of top-down logic, as on
    windows this could be on or off on a case-by-case basis.
    """
    @wraps(func)
    @attr('skip_wo_symlink_capability')
    def  _wrap_skip_wo_symlink_capability(*args, **kwargs):
        if not has_symlink_capability():
            raise SkipTest("no symlink capabilities")
        return func(*args, **kwargs)
    return  _wrap_skip_wo_symlink_capability


_TESTS_ADJUSTED_TMPDIR = None


def skip_if_adjusted_branch(func):
    """Skip test if adjusted branch is used by default on TMPDIR file system.
    """
    @wraps(func)
    @attr('skip_if_adjusted_branch')
    def _wrap_skip_if_adjusted_branch(*args, **kwargs):
        global _TESTS_ADJUSTED_TMPDIR
        if _TESTS_ADJUSTED_TMPDIR is None:
            @with_tempfile
            def _check(path):
                ds = Dataset(path).create(force=True)
                return ds.repo.is_managed_branch()
            _TESTS_ADJUSTED_TMPDIR = _check()

        if _TESTS_ADJUSTED_TMPDIR:
            raise SkipTest("Test incompatible with adjusted branch default")
        return func(*args, **kwargs)
    return _wrap_skip_if_adjusted_branch


def get_ssh_port(host):
    """Get port of `host` in ssh_config.

    Our tests depend on the host being defined in ssh_config, including its
    port. This method can be used by tests that want to check handling of an
    explicitly specified

    Note that if `host` does not match a host in ssh_config, the default value
    of 22 is returned.

    Parameters
    ----------
    host : str

    Returns
    -------
    port (int)

    Raises
    ------
    SkipTest if port cannot be found.
    """
    out = ''
    runner = WitlessRunner()
    try:
        res = runner.run(["ssh", "-G", host], protocol=StdOutErrCapture)
        out = res["stdout"]
        err = res["stderr"]
    except Exception as exc:
        err = str(exc)

    port = None
    for line in out.splitlines():
        if line.startswith("port "):
            try:
                port = int(line.split()[1])
            except Exception as exc:
                err = str(exc)
            break

    if port is None:
        raise SkipTest("port for {} could not be determined: {}"
                       .format(host, err))
    return port


#
# Context Managers
#


def patch_config(vars):
    """Patch our config with custom settings. Returns mock.patch cm

    Only the merged configuration from all sources (global, local, dataset)
    will be patched. Source-constrained patches (e.g. only committed dataset
    configuration) are not supported.
    """
    return patch.dict(dl_cfg._merged_store, vars)


@contextmanager
def set_date(timestamp):
    """Temporarily override environment variables for git/git-annex dates.

    Parameters
    ----------
    timestamp : int
        Unix timestamp.
    """
    git_ts = "@{} +0000".format(timestamp)
    with patch.dict("os.environ",
                    {"GIT_COMMITTER_DATE": git_ts,
                     "GIT_AUTHOR_DATE": git_ts,
                     "GIT_ANNEX_VECTOR_CLOCK": str(timestamp),
                     "DATALAD_FAKE__DATES": "0"}):
        yield


@contextmanager
def set_annex_version(version):
    """Override the git-annex version.

    This temporarily masks the git-annex version present in external_versions
    and make AnnexRepo forget its cached version information.
    """
    from datalad.support.annexrepo import AnnexRepo
    ar_vers = AnnexRepo.git_annex_version
    with patch.dict(
            "datalad.support.annexrepo.external_versions._versions",
            {"cmd:annex": version}):
        try:
            AnnexRepo.git_annex_version = None
            yield
        finally:
            AnnexRepo.git_annex_version = ar_vers

#
# Test tags
#
# To be explicit, and not "loose" some tests due to typos, decided to make
# explicit decorators for common types

from nose.plugins.attrib import attr


def integration(f):
    """Mark test as an "integration" test which generally is not needed to be run
    
    Generally tend to be slower.
    Should be used in combination with @slow and @turtle if that is the case.
    """
    return attr('integration')(f)


def slow(f):
    """Mark test as a slow, although not necessarily integration or usecase test

    Rule of thumb cut-off to mark as slow is 10 sec
    """
    return attr('slow')(f)


def turtle(f):
    """Mark test as very slow, meaning to not run it on Travis due to its
    time limit

    Rule of thumb cut-off to mark as turtle is 2 minutes
    """
    return attr('turtle')(f)


def usecase(f):
    """Mark test as a usecase user ran into and which (typically) caused bug report
    to be filed/troubleshooted

    Should be used in combination with @slow and @turtle if slow.
    """
    return attr('usecase')(f)
