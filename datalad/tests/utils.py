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
import inspect
import shutil
import stat
import os
import re
import tempfile
import platform
import multiprocessing
import logging
import random
import socket
from six import PY2, text_type, iteritems
from six import binary_type
from fnmatch import fnmatch
import time
from mock import patch

from six.moves.SimpleHTTPServer import SimpleHTTPRequestHandler
from six.moves.BaseHTTPServer import HTTPServer
from six import reraise
from six.moves import map

from functools import wraps
from os.path import exists, realpath, join as opj, pardir, split as pathsplit, curdir
from os.path import relpath

from nose.tools import \
    assert_equal, assert_not_equal, assert_raises, assert_greater, assert_true, assert_false, \
    assert_in, assert_not_in, assert_in as in_, assert_is, \
    raises, ok_, eq_, make_decorator

from nose.tools import assert_set_equal
from nose.tools import assert_is_instance
from nose import SkipTest

from ..cmd import Runner
from ..utils import *
from ..support.exceptions import CommandNotAvailableError
from ..support.vcr_ import *
from ..support.keyring_ import MemoryKeyring
from ..dochelpers import exc_str, borrowkwargs
from ..cmdline.helpers import get_repo_instance
from ..consts import ARCHIVES_TEMP_DIR
from . import _TEMP_PATHS_GENERATED

# temp paths used by clones
_TEMP_PATHS_CLONES = set()


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


def create_tree_archive(path, name, load, overwrite=False, archives_leading_dir=True):
    """Given an archive `name`, create under `path` with specified `load` tree
    """
    from ..support.archives import compress_files
    dirname = file_basename(name)
    full_dirname = opj(path, dirname)
    os.makedirs(full_dirname)
    create_tree(full_dirname, load, archives_leading_dir=archives_leading_dir)
    # create archive
    if archives_leading_dir:
        compress_files([dirname], name, path=path, overwrite=overwrite)
    else:
        compress_files(list(map(basename, glob.glob(opj(full_dirname, '*')))),
                       opj(pardir, name),
                       path=opj(path, dirname),
                       overwrite=overwrite)
    # remove original tree
    shutil.rmtree(full_dirname)


def create_tree(path, tree, archives_leading_dir=True):
    """Given a list of tuples (name, load) create such a tree

    if load is a tuple itself -- that would create either a subtree or an archive
    with that content and place it into the tree if name ends with .tar.gz
    """
    lgr.log(5, "Creating a tree under %s", path)
    if not exists(path):
        os.makedirs(path)

    if isinstance(tree, dict):
        tree = tree.items()

    for name, load in tree:
        full_name = opj(path, name)
        if isinstance(load, (tuple, list, dict)):
            if name.endswith('.tar.gz') or name.endswith('.tar') or name.endswith('.zip'):
                create_tree_archive(path, name, load, archives_leading_dir=archives_leading_dir)
            else:
                create_tree(full_name, load, archives_leading_dir=archives_leading_dir)
        else:
            #encoding = sys.getfilesystemencoding()
            #if isinstance(full_name, text_type):
            #    import pydb; pydb.debugger()
            with open(full_name, 'w') as f:
                if PY2 and isinstance(load, text_type):
                    load = load.encode('utf-8')
                f.write(load)

#
# Addition "checkers"
#

import git
import os
from os.path import exists, join
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileNotInAnnexError
from ..utils import chpwd, getpwd


def ok_clean_git(path, annex=None, head_modified=[], index_modified=[],
                 untracked=[], ignore_submodules=False):
    """Verify that under given path there is a clean git repository

    it exists, .git exists, nothing is uncommitted/dirty/staged

    Note
    ----
    Parameters head_modified and index_modified currently work
    in pure git or indirect mode annex only and are ignored otherwise!
    Implementation is yet to do!

    Parameters
    ----------
    path: str or Repo
      in case of a str: path to the repository's base dir;
      Note, that passing a Repo instance prevents detecting annex. This might be
      useful in case of a non-initialized annex, a GitRepo is pointing to.
    annex: bool or None
      explicitly set to True or False to indicate, that an annex is (not)
      expected; set to None to autodetect, whether there is an annex.
      Default: None.
    ignore_submodules: bool
      if True, submodules are not inspected
    """
    # TODO: See 'Note' in docstring

    if isinstance(path, AnnexRepo):
        if annex is None:
            annex = True
        # if `annex` was set to False, but we find an annex => fail
        assert_is(annex, True)
        r = path
    elif isinstance(path, GitRepo):
        if annex is None:
            annex = False
        # explicitly given GitRepo instance doesn't make sense with 'annex' True
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

    eq_(sorted(r.untracked_files), sorted(untracked))

    if annex and r.is_direct_mode():
        if head_modified or index_modified:
            lgr.warning("head_modified and index_modified are not quite valid "
                        "concepts in direct mode! Looking for any change "
                        "(staged or not) instead.")
            status = r.get_status(untracked=False, submodules=not ignore_submodules)
            modified = []
            for s in status:
                modified.extend(status[s])
            eq_(sorted(head_modified + index_modified),
                sorted(f for f in modified))
        else:
            ok_(not r.is_dirty(untracked_files=not untracked,
                               submodules=not ignore_submodules))
    else:
        repo = r.repo

        if repo.index.entries.keys():
            ok_(repo.head.is_valid())

            if not head_modified and not index_modified:
                # get string representations of diffs with index to ease
                # troubleshooting
                head_diffs = [str(d) for d in repo.index.diff(repo.head.commit)]
                index_diffs = [str(d) for d in repo.index.diff(None)]
                eq_(head_diffs, [])
                eq_(index_diffs, [])
            else:
                if head_modified:
                    # we did ask for interrogating changes
                    head_modified_ = [d.a_path for d in repo.index.diff(repo.head.commit)]
                    eq_(head_modified_, head_modified)
                if index_modified:
                    index_modified_ = [d.a_path for d in repo.index.diff(None)]
                    eq_(index_modified_, index_modified)


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
        repo.add(file_repo_path, commit=True, _datalad_msg=True)
    else:
        repo.add(file_repo_path, git=True, _datalad_msg=True)
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
    file_repo_dir = os.path.relpath(path, repo.path)
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
    assert exists(path), 'path %s does not exist' % path


def ok_file_has_content(path, content, strip=False, re_=False, **kwargs):
    """Verify that file exists and has expected content"""
    ok_exists(path)
    with open(path, 'r') as f:
        content_ = f.read()

        if strip:
            content_ = content_.strip()

        if re_:
            assert_re_in(content, content_, **kwargs)
        else:
            assert_equal(content, content_, **kwargs)


#
# Decorators
#


@optional_args
def with_tree(t, tree=None, archives_leading_dir=True, delete=True, **tkwargs):

    @wraps(t)
    def newfunc(*arg, **kw):
        tkwargs_ = get_tempfile_kwargs(tkwargs, prefix="tree", wrapped=t)
        d = tempfile.mkdtemp(**tkwargs_)
        create_tree(d, tree, archives_leading_dir=archives_leading_dir)
        try:
            return t(*(arg + (d,)), **kw)
        finally:
            if delete:
                rmtemp(d)
    return newfunc


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
        lgr.debug("HTTP: " + format % args)


def _multiproc_serve_path_via_http(hostname, path_to_serve_from, queue): # pragma: no cover
    chpwd(path_to_serve_from)
    httpd = HTTPServer((hostname, 0), SilentHTTPHandler)
    queue.put(httpd.server_port)
    httpd.serve_forever()


@optional_args
def serve_path_via_http(tfunc, *targs):
    """Decorator which serves content of a directory via http url
    """

    @wraps(tfunc)
    def newfunc(*args, **kwargs):

        if targs:
            # if a path is passed into serve_path_via_http, then it's in targs
            assert len(targs) == 1
            path = targs[0]

        elif len(args) > 1:
            args, path = args[:-1], args[-1]
        else:
            args, path = (), args[0]

        # There is a problem with Haskell on wheezy trying to
        # fetch via IPv6 whenever there is a ::1 localhost entry in
        # /etc/hosts.  Apparently fixing that docker image reliably
        # is not that straightforward, although see
        # http://jasonincode.com/customizing-hosts-file-in-docker/
        # so we just force to use 127.0.0.1 while on wheezy
        #hostname = '127.0.0.1' if on_debian_wheezy else 'localhost'
        hostname = '127.0.0.1'

        queue = multiprocessing.Queue()
        multi_proc = multiprocessing.Process(
            target=_multiproc_serve_path_via_http,
            args=(hostname, path, queue))
        multi_proc.start()
        port = queue.get(timeout=300)
        url = 'http://{}:{}/'.format(hostname, port)
        lgr.debug("HTTP: serving {} under {}".format(path, url))

        try:
            # Such tests don't require real network so if http_proxy settings were
            # provided, we remove them from the env for the duration of this run
            env = os.environ.copy()
            env.pop('http_proxy', None)
            with patch.dict('os.environ', env, clear=True):
                return tfunc(*(args + (path, url)), **kwargs)
        finally:
            lgr.debug("HTTP: stopping server under %s" % path)
            multi_proc.terminate()

    return newfunc


@optional_args
def with_memory_keyring(t):
    """Decorator to use non-persistant MemoryKeyring instance
    """
    @wraps(t)
    def newfunc(*args, **kwargs):
        keyring = MemoryKeyring()
        with patch("datalad.downloaders.credentials.keyring_", keyring):
            return t(*(args + (keyring,)), **kwargs)

    return newfunc


@optional_args
def without_http_proxy(tfunc):
    """Decorator to remove http*_proxy env variables for the duration of the test
    """

    @wraps(tfunc)
    def newfunc(*args, **kwargs):
        # Such tests don't require real network so if http_proxy settings were
        # provided, we remove them from the env for the duration of this run
        env = os.environ.copy()
        env.pop('http_proxy', None)
        env.pop('https_proxy', None)
        with patch.dict('os.environ', env, clear=True):
            return tfunc(*args, **kwargs)

    return newfunc


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
    def newfunc(*arg, **kw):
        with make_tempfile(wrapped=t, **tkwargs) as filename:
            return t(*(arg + (filename,)), **kw)

    return newfunc


def _get_resolved_flavors(flavors):
    #flavors_ = (['local', 'clone'] + (['local-url'] if not on_windows else [])) \
    #           if flavors == 'auto' else flavors
    flavors_ = (['local', 'clone', 'local-url', 'network'] if not on_windows
                else ['network', 'network-clone']) \
               if flavors == 'auto' else flavors

    if not isinstance(flavors_, list):
        flavors_ = [flavors_]

    if os.environ.get('DATALAD_TESTS_NONETWORK'):
        flavors_ = [x for x in flavors_ if not x.startswith('network')]
    return flavors_

def _get_repo_url(path):
    """Return ultimate URL for this repo"""

    if path.startswith('http') or path.startswith('git'):
        # We were given a URL, so let's just return it
        return path

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
    _TEMP_PATHS_CLONES.add(tdir)
    return tdir


if not on_windows:
    local_testrepo_flavors = ['local'] # 'local-url'
else:
    local_testrepo_flavors = ['network-clone']

from .utils_testrepos import BasicAnnexTestRepo, BasicGitTestRepo, \
    SubmoduleDataset, NestedDataset, InnerSubmodule

_TESTREPOS = None

def _get_testrepos_uris(regex, flavors):
    global _TESTREPOS
    # we should instantiate those whenever test repos actually asked for
    # TODO: just absorb all this lazy construction within some class
    if not _TESTREPOS:
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
        if not on_windows:
            _basic_annex_test_repo.create()
            _basic_git_test_repo.create()
            _submodule_annex_test_repo.create()
            _nested_submodule_annex_test_repo.create()
            _inner_submodule_annex_test_repo.create()
    uris = []
    for name, spec in iteritems(_TESTREPOS):
        if not re.match(regex, name):
            continue
        uris += [spec[x] for x in set(spec.keys()).intersection(flavors)]

        # additional flavors which might have not been
        if 'clone' in flavors and 'clone' not in spec:
            uris.append(clone_url(spec['local']))

        if 'network-clone' in flavors and 'network-clone' not in spec:
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
    def newfunc(*arg, **kw):
        # TODO: would need to either avoid this "decorator" approach for
        # parametric tests or again aggregate failures like sweepargs does
        flavors_ = _get_resolved_flavors(flavors)

        testrepos_uris = _get_testrepos_uris(regex, flavors_)
        # we should always have at least one repo to test on, unless explicitly only
        # network was requested by we are running without networked tests
        if not (os.environ.get('DATALAD_TESTS_NONETWORK') and flavors == ['network']):
            assert(testrepos_uris)
        else:
            if not testrepos_uris:
                raise SkipTest("No non-networked repos to test on")

        ntested = 0
        for uri in testrepos_uris:
            if count and ntested >= count:
                break
            ntested += 1
            if __debug__:
                lgr.debug('Running %s on %s' % (t.__name__, uri))
            try:
                t(*(arg + (uri,)), **kw)
            finally:
                if uri in _TEMP_PATHS_CLONES:
                    _TEMP_PATHS_CLONES.discard(uri)
                    rmtemp(uri)
                pass  # might need to provide additional handling so, handle
    return newfunc
with_testrepos.__test__ = False


@optional_args
def with_fake_cookies_db(func, cookies={}):
    """mock original cookies db with a fake one for the duration of the test
    """
    from ..support.cookies import cookies_db

    @wraps(func)
    def newfunc(*args, **kwargs):
        try:
            orig_cookies_db = cookies_db._cookies_db
            cookies_db._cookies_db = cookies.copy()
            return func(*args, **kwargs)
        finally:
            cookies_db._cookies_db = orig_cookies_db
    return newfunc


def skip_if_no_network(func=None):
    """Skip test completely in NONETWORK settings

    If not used as a decorator, and just a function, could be used at the module level
    """

    def check_and_raise():
        if os.environ.get('DATALAD_TESTS_NONETWORK'):
            raise SkipTest("Skipping since no network settings")

    if func:
        @wraps(func)
        def newfunc(*args, **kwargs):
            check_and_raise()
            return func(*args, **kwargs)
        # right away tag the test as a networked test
        tags = getattr(newfunc, 'tags', [])
        newfunc.tags = tags + ['network']
        return newfunc
    else:
        check_and_raise()


def skip_if_on_windows(func):
    """Skip test completely under Windows
    """
    @wraps(func)
    def newfunc(*args, **kwargs):
        if on_windows:
            raise SkipTest("Skipping on Windows")
        return func(*args, **kwargs)
    return newfunc


@optional_args
def skip_if(func, cond=True, msg=None):
    """Skip test for specific condition
    """
    @wraps(func)
    def newfunc(*args, **kwargs):
        if cond:
            raise SkipTest(msg if msg else "condition was True")
        return func(*args, **kwargs)
    return newfunc


def skip_ssh(func):
    """Skips SSH tests if on windows or if environment variable
    DATALAD_TESTS_SSH was not set
    """
    @wraps(func)
    def newfunc(*args, **kwargs):
        if on_windows:
            raise SkipTest("SSH currently not available on windows.")
        test_ssh = os.environ.get('DATALAD_TESTS_SSH', '').lower()
        if test_ssh in ('', '0', 'false', 'no'):
            raise SkipTest("Run this test by setting DATALAD_TESTS_SSH")
        return func(*args, **kwargs)
    return newfunc


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
    def newfunc(*args, **kwargs):
        cwd_before = os.getcwd()
        pwd_before = getpwd()
        exc_info = None
        try:
            func(*args, **kwargs)
        except:
            exc_info = sys.exc_info()
        finally:
            try:
                cwd_after = os.getcwd()
            except OSError as e:
                lgr.warning("Failed to getcwd: %s" % e)
                cwd_after = None

        if cwd_after != cwd_before:
            chpwd(pwd_before)
            if not ok_to_chdir:
                lgr.warning(
                    "%s changed cwd to %s. Mitigating and changing back to %s"
                    % (func, cwd_after, pwd_before))
                # If there was already exception raised, we better re-raise
                # that one since it must be more important, so not masking it
                # here with our assertion
                if exc_info is None:
                    assert_equal(cwd_before, cwd_after,
                                 "CWD changed from %s to %s" % (cwd_before, cwd_after))

        if exc_info is not None:
            reraise(*exc_info)

    return newfunc

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
    def newfunc(*args, **kwargs):
        pwd_before = getpwd()
        try:
            chpwd(newdir)
            func(*args, **kwargs)
        finally:
            chpwd(pwd_before)


    return newfunc


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


def assert_status(label, results):
    """Verify that each status dict in the results has a given status label

    `label` can be a sequence, in which case status must be one of the items
    in this sequence.
    """
    label = assure_list(label)
    for r in assure_list(results):
        assert_in('status', r)
        assert_in(r['status'], label)


def assert_message(message, results):
    """Verify that each status dict in the results has a message

    This only tests the message template string, and not a formatted message
    with args expanded.
    """
    for r in assure_list(results):
        assert_in('message', r)
        m = r['message'][0] if isinstance(r['message'], tuple) else r['message']
        assert_equal(m, message)


def assert_result_count(results, n, **kwargs):
    """Verify specific number of results (matching criteria, if any)"""
    count = 0
    for r in assure_list(results):
        if not len(kwargs):
            count += 1
        elif all(k in r and r[k] == v for k, v in kwargs.items()):
            count += 1
    assert_equal(n, count)


def assert_in_results(results, **kwargs):
    """Verify that the particular combination of keys and values is found in
    one of the results"""
    found = False
    for r in assure_list(results):
        if all(k in r and r[k] == v for k, v in kwargs.items()):
            found = True
    assert found


def assert_not_in_results(results, **kwargs):
    """Verify that the particular combination of keys and values is not in any
    of the results"""
    for r in assure_list(results):
        assert any(k not in r or r[k] != v for k, v in kwargs.items())


def assert_result_values_equal(results, prop, values):
    """Verify that the values of all results for a given key in the status dicts
    match the given sequence"""
    assert_equal(
        [r[prop] for r in results],
        values)


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
        except AttributeError as e:
            # Use args instead of .message which is PY2 specific
            message = e.args[0] if e.args else ""
            if message.find('StringIO') > -1 and message.find('fileno') > -1:
                pass
            else:
                raise
    return newfunc


def skip_httpretty_on_problematic_pythons(func):
    """As discovered some httpretty bug causes a side-effect
    on other tests on some Pythons.  So we skip the test if such
    problematic combination detected

    References
    https://travis-ci.org/datalad/datalad/jobs/94464988
    http://stackoverflow.com/a/29603206/1265472
    """

    @make_decorator(func)
    def newfunc(*args, **kwargs):
        if sys.version_info[:3] == (3, 4, 2):
            raise SkipTest("Known to cause trouble due to httpretty bug on this Python")
        return func(*args, **kwargs)
    return newfunc


@optional_args
def with_batch_direct(t):
    """Helper to run parametric test with possible combinations of batch and direct
    """
    @wraps(t)
    def newfunc():
        for batch in (False, True):
            for direct in (False, True) if not on_windows else (True,):
                yield t, batch, direct

    return newfunc


def dump_graph(graph, flatten=False):
    from json import dumps
    if flatten:
        from datalad.metadata import flatten_metadata_graph
        graph = flatten_metadata_graph(graph)
    return dumps(
        graph,
        indent=1,
        default=lambda x: 'non-serializable object skipped')


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
    """Return the most obscure filename that the filesystem would support under TEMPDIR

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


@optional_args
def with_testsui(t, responses=None, interactive=True):
    """Switch main UI to be 'tests' UI and possibly provide answers to be used"""

    @wraps(t)
    def newfunc(*args, **kwargs):
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

    return newfunc

with_testsui.__test__ = False


def assert_no_errors_logged(func, skip_re=None):
    """Decorator around function to assert that no errors logged during its execution"""
    @wraps(func)
    def new_func(*args, **kwargs):
        with swallow_logs(new_level=logging.ERROR) as cml:
            out = func(*args, **kwargs)
            if cml.out:
                if not (skip_re and re.search(skip_re, cml.out)):
                    raise AssertionError(
                        "Expected no errors to be logged, but log output is %s"
                        % cml.out
                    )
        return out

    return new_func


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



#
# Context Managers
#
