# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test testing utilities

"""

import inspect
import os
import shutil
import sys
import logging
from mock import patch
from six import PY3
from six import text_type

from operator import itemgetter
from os.path import dirname, normpath, pardir, basename
from os.path import isabs, expandvars, expanduser
from collections import OrderedDict

from ..dochelpers import exc_str
from ..utils import updated
from os.path import join as opj, abspath, exists
from ..utils import rotree, swallow_outputs, swallow_logs, setup_exceptionhook, md5sum
from ..utils import getpwd, chpwd
from ..utils import get_path_prefix
from ..utils import auto_repr
from ..utils import find_files
from ..utils import line_profile
from ..utils import not_supported_on_windows
from ..utils import file_basename
from ..utils import expandpath, is_explicit_path
from ..utils import knows_annex
from ..utils import any_re_search
from ..utils import unique
from ..utils import get_func_kwargs_doc
from ..utils import make_tempfile
from ..utils import on_windows
from ..utils import _path_
from ..utils import get_timestamp_suffix
from ..utils import get_trace
from ..utils import get_dataset_root
from ..utils import better_wraps

from ..support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_equal, assert_true

from .utils import with_tempfile, assert_in, with_tree
from .utils import SkipTest
from .utils import assert_cwd_unchanged, skip_if_on_windows
from .utils import assure_dict_from_str, assure_list_from_str
from .utils import assure_unicode
from .utils import assure_bool
from .utils import assure_list
from .utils import ok_generator
from .utils import assert_not_in
from .utils import assert_raises
from .utils import ok_startswith
from .utils import skip_if_no_module


def test_get_func_kwargs_doc():
    def some_func(arg1, kwarg1=None, kwarg2="bu"):
        return
    eq_(get_func_kwargs_doc(some_func), ['arg1', 'kwarg1', 'kwarg2'])


def test_better_wraps():
    from functools import wraps
    from inspect import getargspec

    def wraps_decorator(func):
        @wraps(func)
        def new_func(*args, **kwargs):
            return func(*args, **kwargs)

        return new_func

    def better_decorator(func):
        @better_wraps(func)
        def new_func(*args, **kwargs):
            return func(*args, **kwargs)

        return new_func

    @wraps_decorator
    def function1(a, b, c):
        return "function1"

    @better_decorator
    def function2(a, b, c):
        return "function2"

    eq_("function1", function1(1, 2, 3))
    eq_(getargspec(function1)[0], [])
    eq_("function2", function2(1, 2, 3))
    eq_(getargspec(function2)[0], ['a', 'b', 'c'])


@with_tempfile(mkdir=True)
def test_rotree(d):
    d2 = opj(d, 'd1', 'd2')  # deep nested directory
    f = opj(d2, 'f1')
    os.makedirs(d2)
    with open(f, 'w') as f_:
        f_.write("LOAD")
    with swallow_logs():
        ar = AnnexRepo(d2)
    rotree(d)
    # we shouldn't be able to delete anything UNLESS in "crippled" situation:
    # root, or filesystem is FAT etc
    # Theoretically annex should declare FS as crippled when ran as root, but
    # see http://git-annex.branchable.com/bugs/decides_that_FS_is_crippled_under_cowbuilder___40__symlinks_supported_etc__41__/#comment-60c3cbe2710d6865fb9b7d6e247cd7aa
    # so explicit 'or'
    if not (ar.is_crippled_fs() or (os.getuid() == 0)):
        assert_raises(OSError, os.unlink, f)
        assert_raises(OSError, shutil.rmtree, d)
        # but file should still be accessible
        with open(f) as f_:
            eq_(f_.read(), "LOAD")
    # make it RW
    rotree(d, False)
    os.unlink(f)
    shutil.rmtree(d)


def test_swallow_outputs():
    with swallow_outputs() as cm:
        eq_(cm.out, '')
        sys.stdout.write("out normal")
        sys.stderr.write("out error")
        eq_(cm.out, 'out normal')
        sys.stdout.write(" and more")
        eq_(cm.out, 'out normal and more')  # incremental
        eq_(cm.err, 'out error')
        eq_(cm.err, 'out error')  # the same value if multiple times


@with_tempfile
def test_swallow_logs(logfile):
    lgr = logging.getLogger('datalad')
    with swallow_logs(new_level=9) as cm:
        eq_(cm.out, '')
        lgr.log(8, "very heavy debug")
        eq_(cm.out, '')  # not even visible at level 9
        lgr.log(9, "debug1")
        eq_(cm.out, '[Level 9] debug1\n')  # not even visible at level 9
        lgr.info("info")
        eq_(cm.out, '[Level 9] debug1\n[INFO] info\n')  # not even visible at level 9
    with swallow_logs(new_level=9, file_=logfile) as cm:
        eq_(cm.out, '')
        lgr.info("next info")
    from datalad.tests.utils import ok_file_has_content
    ok_file_has_content(logfile, "[INFO] next info", strip=True)


def test_swallow_logs_assert():
    lgr = logging.getLogger('datalad.tests')
    with swallow_logs(new_level=9) as cm:
        # nothing was logged so should fail
        assert_raises(AssertionError, cm.assert_logged)
        lgr.info("something")
        cm.assert_logged("something")
        cm.assert_logged(level="INFO")
        cm.assert_logged("something", level="INFO")

        # even with regex = False should match above
        cm.assert_logged("something", regex=False)
        cm.assert_logged(level="INFO", regex=False)
        cm.assert_logged("something", level="INFO", regex=False)

        # different level
        assert_raises(AssertionError,
                      cm.assert_logged, "something", level="DEBUG")
        assert_raises(AssertionError, cm.assert_logged, "else")

        cm.assert_logged("some.hing", level="INFO")  # regex ;-)
        # does match
        assert_raises(AssertionError,
                      cm.assert_logged, "ome.hing", level="INFO")
        # but we can change it
        cm.assert_logged("some.hing", level="INFO", match=False)
    # and we can continue doing checks after we left the cm block
    cm.assert_logged("some.hing", level="INFO", match=False)
    # and we indeed logged something
    cm.assert_logged(match=False)


def _check_setup_exceptionhook(interactive):
    old_exceptionhook = sys.excepthook

    post_mortem_tb = []

    def our_post_mortem(tb):
        post_mortem_tb.append(tb)

    with patch('sys.excepthook'), \
            patch('datalad.utils.is_interactive', lambda: interactive), \
            patch('pdb.post_mortem', our_post_mortem):
        setup_exceptionhook()
        our_exceptionhook = sys.excepthook
        ok_(old_exceptionhook != our_exceptionhook)
        #out = sys.stdout
        with swallow_logs() as cml, swallow_outputs() as cmo:
            # we need to call our_exceptionhook explicitly b/c nose
            # swallows all Exceptions and hook never gets executed
            try:
                raise RuntimeError
            except Exception as e:  # RuntimeError:
                type_, value_, tb_ = sys.exc_info()
            our_exceptionhook(type_, value_, tb_)
            if PY3:
                # Happens under tox environment but not in manually crafted ones -- not yet sure
                # what it is about but --dbg does work with python3 so lettting it skip for now
                raise SkipTest("TODO: Not clear why in PY3 calls cleanup if we try to access the beast")
            assert_in('Traceback (most recent call last)', cmo.err)
            assert_in('in _check_setup_exceptionhook', cmo.err)
            if interactive:
                assert_equal(post_mortem_tb[0], tb_)
            else:
                assert_equal(post_mortem_tb, [])
                # assert_in('We cannot setup exception hook', cml.out)

    eq_(old_exceptionhook, sys.excepthook)


def test_setup_exceptionhook():
    for tval in [True, False]:
        yield _check_setup_exceptionhook, tval


def test_md5sum():
    # just a smoke (encoding/decoding) test for md5sum
    _ = md5sum(__file__)


@with_tree([('1.tar.gz', (('1 f.txt', '1 f load'),))])
def test_md5sum_archive(d):
    # just a smoke (encoding/decoding) test for md5sum
    _ = md5sum(opj(d, '1.tar.gz'))


def test_updated():
    d = {}
    eq_(updated(d, {1: 2}), {1: 2})
    eq_(d, {})

    d = {'a': 'b'}
    eq_(updated(d, ((0, 1), (2, 3))), {0: 1, 'a': 'b', 2: 3})
    eq_(d, {'a': 'b'})

    # and that it would maintain the type
    d = OrderedDict(((99, 0), ('z', 0), ('a', 0)))
    d_ = updated(d, {0: 1})
    ok_(isinstance(d_, OrderedDict))
    eq_(d_, OrderedDict(((99, 0), ('z', 0), ('a', 0), (0, 1))))


def test_get_local_file_url_windows():
    raise SkipTest("TODO")


@assert_cwd_unchanged
def test_getpwd_basic():
    pwd = getpwd()
    ok_(isabs(pwd))
    eq_(os.getcwd(), abspath(pwd))

    # that we do not chdir anywhere if None provided
    with patch('os.chdir') as oschdir:
        with chpwd(None):
            eq_(getpwd(), pwd)
        assert_false(oschdir.called)


@skip_if_on_windows
@with_tempfile(mkdir=True)
@assert_cwd_unchanged
def test_getpwd_symlink(tdir):
    sdir = opj(tdir, 's1')
    pwd_orig = getpwd()
    os.symlink('.', sdir)
    s1dir = opj(sdir, 's1')
    s2dir = opj(sdir, 's2')
    try:
        chpwd(sdir)
        pwd = getpwd()
        eq_(pwd, sdir)
        chpwd('s1')
        eq_(getpwd(), s1dir)
        chpwd('.')
        eq_(getpwd(), s1dir)
        chpwd('..')
        eq_(getpwd(), sdir)
    finally:
        chpwd(pwd_orig)

    # test context handler way of use
    with chpwd(s1dir):
        eq_(getpwd(), s1dir)
    eq_(getpwd(), pwd_orig)

    assert_false(exists(s2dir))
    with assert_raises(OSError):
        with chpwd(s2dir):
            pass
    with chpwd(s2dir, mkdir=True):
        ok_(exists(s2dir))
        eq_(getpwd(), s2dir)


def test_auto_repr():

    class withoutrepr:
        def __init__(self):
            self.a = "does not matter"

    @auto_repr
    class buga:
        def __init__(self):
            self.a = 1
            self.b = list(range(100))
            self.c = withoutrepr()
            self._c = "protect me"

        def some(self):
            return "some"

    assert_equal(repr(buga()), "buga(a=1, b=<<[0, 1, 2, 3, 4, 5, 6, ...>>, c=<withoutrepr>)")
    assert_equal(buga().some(), "some")


def test_assure_list_copy():
    l = [1]
    assert assure_list(l) is l
    assert assure_list(l, copy=True) is not l


def test_assure_list_from_str():
    assert_equal(assure_list_from_str(''), None)
    assert_equal(assure_list_from_str([]), None)
    assert_equal(assure_list_from_str('somestring'), ['somestring'])
    assert_equal(assure_list_from_str('some\nmultiline\nstring'), ['some', 'multiline', 'string'])
    assert_equal(assure_list_from_str(['something']), ['something'])
    assert_equal(assure_list_from_str(['a', 'listof', 'stuff']), ['a', 'listof', 'stuff'])


def test_assure_dict_from_str():
    assert_equal(assure_dict_from_str(''), None)
    assert_equal(assure_dict_from_str({}), None)
    assert_equal(assure_dict_from_str(
            '__ac_name={user}\n__ac_password={password}\nsubmit=Log in\ncookies_enabled='), dict(
             __ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in'))
    assert_equal(assure_dict_from_str(
        dict(__ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in')), dict(
             __ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in'))


def test_assure_bool():
    for values, t in [
        (['True', 1, '1', 'yes', 'on'], True),
        (['False', 0, '0', 'no', 'off'], False)
    ]:
        for v in values:
            eq_(assure_bool(v), t)
    assert_raises(ValueError, assure_bool, "unknown")


def test_any_re_search():
    assert_true(any_re_search('a', 'a'))
    assert_true(any_re_search('a', 'bab'))
    assert_false(any_re_search('^a', 'bab'))
    assert_true(any_re_search(['b', '.ab'], 'bab'))
    assert_false(any_re_search(['^b', 'bab'], 'ab'))


def test_find_files():
    tests_dir = dirname(__file__)
    proj_dir = normpath(opj(dirname(__file__), pardir))

    ff = find_files('.*', proj_dir)
    ok_generator(ff)
    files = list(ff)
    assert(len(files) > 10)  # we have more than 10 test files here
    assert_in(opj(tests_dir, 'test_utils.py'), files)
    # and no directories should be mentioned
    assert_not_in(tests_dir, files)

    ff2 = find_files('.*', proj_dir, dirs=True)
    files2 = list(ff2)
    assert_in(opj(tests_dir, 'test_utils.py'), files2)
    assert_in(tests_dir, files2)

    # now actually matching the path
    ff3 = find_files('.*/test_.*\.py$', proj_dir, dirs=True)
    files3 = list(ff3)
    assert_in(opj(tests_dir, 'test_utils.py'), files3)
    assert_not_in(tests_dir, files3)
    for f in files3:
        ok_startswith(basename(f), 'test_')

from .utils import with_tree
@with_tree(tree={
    '.git': {
        '1': '2'
    },
    'd1': {
        '.git': 'possibly a link from submodule'
    },
    'git': 'just a file'
})
def test_find_files_exclude_vcs(repo):
    ff = find_files('.*', repo, dirs=True)
    files = list(ff)
    assert_equal({basename(f) for f in files}, {'d1', 'git'})
    assert_not_in(opj(repo, '.git'), files)

    ff = find_files('.*', repo, dirs=True, exclude_vcs=False)
    files = list(ff)
    assert_equal({basename(f) for f in files}, {'d1', 'git', '.git', '1'})
    assert_in(opj(repo, '.git'), files)


def test_line_profile():
    skip_if_no_module('line_profiler')

    @line_profile
    def f(j):
        i = j + 1  # xyz
        return i

    with swallow_outputs() as cmo:
        assert_equal(f(3), 4)
        assert_equal(cmo.err, '')
        assert_in('i = j + 1  # xyz', cmo.out)


def test_not_supported_on_windows():
    with patch('datalad.utils.on_windows', True):
        assert_raises(NotImplementedError, not_supported_on_windows)
        assert_raises(NotImplementedError, not_supported_on_windows, "msg")

    with patch('datalad.utils.on_windows', False):
        assert_equal(not_supported_on_windows(), None)
        assert_equal(not_supported_on_windows("msg"), None)


def test_file_basename():
    eq_(file_basename('1'), '1')
    eq_(file_basename('d1/1'), '1')
    eq_(file_basename('/d1/1'), '1')
    eq_(file_basename('1.'), '1.')
    eq_(file_basename('1.tar.gz'), '1')
    eq_(file_basename('1.Tar.gz'), '1')
    eq_(file_basename('1._bak.gz'), '1')
    eq_(file_basename('1.tar.gz', return_ext=True), ('1', 'tar.gz'))
    eq_(file_basename('/tmp/1.tar.gz'), '1')
    eq_(file_basename('/tmp/1.longish.gz'), '1.longish')
    eq_(file_basename('1_R1.1.1.tar.gz'), '1_R1.1.1')
    eq_(file_basename('ds202_R1.1.1.tgz'), 'ds202_R1.1.1')


def test_expandpath():
    eq_(expandpath("some", False), expanduser('some'))
    eq_(expandpath("some", False), expandvars('some'))
    assert_true(isabs(expandpath('some')))
    # this may have to go because of platform issues
    eq_(expandpath("$HOME"), expanduser('~'))


def test_is_explicit_path():
    # by default expanded paths are absolute, hence explicit
    assert_true(is_explicit_path(expandpath('~')))
    assert_false(is_explicit_path("here"))


@with_tempfile
@with_tempfile
def test_knows_annex(here, there):
    from datalad.support.gitrepo import GitRepo
    from datalad.support.annexrepo import AnnexRepo
    GitRepo(path=here, create=True)
    assert_false(knows_annex(here))
    AnnexRepo(path=here, create=True)
    assert_true(knows_annex(here))
    GitRepo.clone(path=there, url=here, create=True)
    assert_true(knows_annex(there))


def test_make_tempfile():
    # check if mkdir, content conflict caught
    with assert_raises(ValueError):
        with make_tempfile(content="blah", mkdir=True):  # pragma: no cover
            pass


def test_unique():
    eq_(unique(range(3)), [0, 1, 2])
    eq_(unique((1, 0, 1, 3, 2, 0, 1)), [1, 0, 3, 2])
    eq_(unique([]), [])
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)]), [(1, 2), (1,), (0, 3)])

    # with a key now
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)], key=itemgetter(0)), [(1, 2), (0, 3)])
    eq_(unique([(1, 2), (1, 3), (1, 2), (0, 3)], key=itemgetter(1)), [(1, 2), (1, 3)])


def test_path_():
    eq_(_path_('a'), 'a')
    if on_windows:
        eq_(_path_('a/b'), r'a\b')
    else:
        p = 'a/b/c'
        assert(_path_(p) is p)  # nothing is done to it whatsoever
        eq_(_path_(p, 'd'), 'a/b/c/d')


def test_get_timestamp_suffix():
    # we need to patch temporarily TZ
    import time
    try:
        with patch.dict('os.environ', {'TZ': 'GMT'}):
            time.tzset()
            assert_equal(get_timestamp_suffix(0), '-1970-01-01T00:00:00+0000')  # skynet DOB
            assert_equal(get_timestamp_suffix(0, prefix="+"), '+1970-01-01T00:00:00+0000')
            # yoh found no way to mock things out and didn't want to provide
            # explicit call to anything to get current time with the timezone, so disabling
            # this test for now besides that it should return smth sensible ;)
            #with patch.object(time, 'localtime', lambda: 1):
            #    assert_equal(get_timestamp_suffix(), '-1970-01-01T00:00:01+0000')  # skynet is 1 sec old
            assert(get_timestamp_suffix().startswith('-'))
    finally:
        time.tzset()


def test_memoized_generator():
    called = [0]

    def g1(n):
        """a generator"""
        called[0] += 1
        for i in range(n):
            yield i

    from ..utils import saved_generator
    ok_generator(g1(3))
    g1_, g2_ = saved_generator(g1(3))
    ok_generator(g1_)
    ok_generator(g2_)
    target = list(g1(3))
    eq_(called[0], 1)
    eq_(target, list(g1_))
    eq_(called[0], 2)
    eq_(target, list(g2_))
    eq_(called[0], 2)  # no new call to make a generator
    # but we can't (ab)use 2nd time
    eq_([], list(g2_))


def test_assure_unicode():
    ok_(isinstance(assure_unicode("m"), text_type))
    ok_(isinstance(assure_unicode('grandchild_äöü東'), text_type))
    ok_(isinstance(assure_unicode(u'grandchild_äöü東'), text_type))
    eq_(assure_unicode('grandchild_äöü東'), u'grandchild_äöü東')


@with_tempfile(mkdir=True)
def test_path_prefix(tdir):
    eq_(get_path_prefix('/d1/d2', '/d1/d2'), '')
    # so we are under /d1/d2 so path prefix is ..
    eq_(get_path_prefix('/d1/d2', '/d1/d2/d3'), '..')
    eq_(get_path_prefix('/d1/d2/d3', '/d1/d2'), 'd3')
    # but if outside -- full path
    eq_(get_path_prefix('/d1/d2', '/d1/d20/d3'), '/d1/d2')
    with chpwd(tdir):
        eq_(get_path_prefix('.'), '')
        eq_(get_path_prefix('d1'), 'd1')
        eq_(get_path_prefix('d1', 'd2'), opj(tdir, 'd1'))
        eq_(get_path_prefix('..'), '..')


def test_get_trace():
    assert_raises(ValueError, get_trace, [], 'bumm', 'doesntmatter')
    eq_(get_trace([('A', 'B')], 'A', 'A'), None)
    eq_(get_trace([('A', 'B')], 'A', 'B'), [])
    eq_(get_trace([('A', 'B')], 'A', 'C'), None)
    eq_(get_trace([('A', 'B'),
                   ('B', 'C')], 'A', 'C'), ['B'])
    # order of edges doesn't matter
    eq_(get_trace([
        ('B', 'C'),
        ('A', 'B')
        ], 'A', 'C'), ['B'])
    # mixed rubbish
    eq_(get_trace([
        (1, 3),
        ('B', 'C'),
        (None, ('schwak', 7)),
        ('A', 'B'),
        ], 'A', 'C'), ['B'])
    # long
    eq_(get_trace([
        ('B', 'C'),
        ('A', 'B'),
        ('distract', 'me'),
        ('C', 'D'),
        ('D', 'E'),
        ], 'A', 'E'), ['B', 'C', 'D'])


@with_tempfile(mkdir=True)
def test_get_dataset_root(path):
    eq_(get_dataset_root('/nonexistent'), None)
    with chpwd(path):
        repo = AnnexRepo(os.curdir, create=True)
        subdir = opj('some', 'deep')
        fname = opj(subdir, 'dummy')
        os.makedirs(subdir)
        with open(fname, 'w') as f:
            f.write('some')
        repo.add(fname)
        # we can find this repo
        eq_(get_dataset_root(os.curdir), os.curdir)
        # and we get the type of path that we fed in
        eq_(get_dataset_root(abspath(os.curdir)), abspath(os.curdir))
        # subdirs are no issue
        eq_(get_dataset_root(subdir), os.curdir)
        # even more subdirs are no issue
        eq_(get_dataset_root(opj(subdir, subdir)), os.curdir)
        # non-dir paths are no issue
        eq_(get_dataset_root(fname), os.curdir)
