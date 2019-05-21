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

import os, os.path as op
import shutil
import sys
import logging
from mock import patch
from six import PY3
from six import text_type
import six.moves.builtins as __builtin__

from operator import itemgetter
from os.path import dirname, normpath, pardir, basename
from os.path import isabs, expandvars, expanduser
from collections import OrderedDict

from ..utils import updated
from os.path import join as opj, abspath, exists
from ..utils import (
    rotree, swallow_outputs, swallow_logs, setup_exceptionhook, md5sum
)
from ..utils import getpwd, chpwd
from ..utils import get_path_prefix
from ..utils import auto_repr
from ..utils import find_files
from ..utils import is_interactive
from ..utils import line_profile
from ..utils import not_supported_on_windows
from ..utils import file_basename
from ..utils import expandpath, is_explicit_path
from ..utils import assure_unicode
from ..utils import knows_annex
from ..utils import any_re_search
from ..utils import unique
from ..utils import all_same
from ..utils import partition
from ..utils import get_func_kwargs_doc
from ..utils import make_tempfile
from ..utils import on_windows
from ..utils import _path_
from ..utils import get_timestamp_suffix
from ..utils import get_trace
from ..utils import get_dataset_root
from ..utils import better_wraps
from ..utils import path_startswith
from ..utils import path_is_subpath
from ..utils import dlabspath
from ..utils import safe_print
from ..utils import generate_chunks
from ..utils import disable_logger
from ..utils import import_modules, import_module_from_file
from ..utils import get_open_files
from ..utils import map_items
from ..utils import unlink
from ..utils import CMD_MAX_ARG
from ..utils import create_tree
from ..utils import never_fail

from ..support.annexrepo import AnnexRepo

from nose.tools import (
    assert_equal,
    assert_false,
    assert_greater,
    assert_true,
    eq_,
    ok_,
)
from datalad.tests.utils import nok_, assert_re_in

from .utils import with_tempfile, assert_in, with_tree
from .utils import SkipTest
from .utils import assert_cwd_unchanged, skip_if_on_windows
from .utils import assure_dict_from_str, assure_list_from_str
from .utils import assure_unicode
from .utils import as_unicode
from .utils import assure_bool
from .utils import assure_iter
from .utils import assure_list
from .utils import ok_generator
from .utils import assert_not_in
from .utils import assert_raises
from .utils import ok_startswith
from .utils import skip_if_no_module
from .utils import (
    probe_known_failure, skip_known_failure, known_failure, known_failure_v6,
    known_failure_direct_mode, skip_if,
    ok_file_has_content
)


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
    # see http://git-annex.branchable.com/bugs/decides_that_FS_is_crippled_
    # under_cowbuilder___40__symlinks_supported_etc__41__/#comment-60c3cbe2710d6865fb9b7d6e247cd7aa
    # so explicit 'or'
    if not (ar.is_crippled_fs() or (os.getuid() == 0)):
        assert_raises(OSError, os.unlink, f)          # OK to use os.unlink
        assert_raises(OSError, unlink, f)   # and even with waiting and trying!
        assert_raises(OSError, shutil.rmtree, d)
        # but file should still be accessible
        with open(f) as f_:
            eq_(f_.read(), "LOAD")
    # make it RW
    rotree(d, False)
    unlink(f)
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
        # not even visible at level 9
        eq_(cm.out, '[Level 9] debug1\n[INFO] info\n')
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


def test_disable_logger():

    # get a logger hierarchy:
    lgr_top = logging.getLogger('datalad')
    lgr_middle = logging.getLogger('datalad.tests')
    lgr_bottom = logging.getLogger('datalad.tests.utils')

    with swallow_logs(new_level=logging.DEBUG) as cml:
        with disable_logger():  # default: 'datalad':
            lgr_top.debug("log sth at top level")
            lgr_middle.debug("log sth at mid level")
            lgr_bottom.debug("log sth at bottom level")
        # nothing logged:
        assert_raises(AssertionError, cml.assert_logged)

    # again, but pass in the logger at mid level:
    with swallow_logs(new_level=logging.DEBUG) as cml:
        with disable_logger(lgr_middle):
            lgr_top.debug("log sth at top level")
            lgr_middle.debug("log sth at mid level")
            lgr_bottom.debug("log sth at bottom level")
        # top level unaffected:
        cml.assert_logged("log sth at top level", level="DEBUG", regex=False)
        # but both of the lower ones don't log anything:
        assert_raises(AssertionError, cml.assert_logged, "log sth at mid level")
        assert_raises(AssertionError, cml.assert_logged, "log sth at bottom level")


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
        with swallow_logs() as cml, swallow_outputs() as cmo:
            # we need to call our_exceptionhook explicitly b/c nose
            # swallows all Exceptions and hook never gets executed
            try:
                raise RuntimeError
            except Exception as e:  # RuntimeError:
                type_, value_, tb_ = sys.exc_info()
            our_exceptionhook(type_, value_, tb_)
            if PY3:
                # Happens under tox environment but not in manually crafted
                # ones -- not yet sure what it is about but --dbg does work
                # with python3 so lettting it skip for now
                raise SkipTest(
                    "TODO: Not clear why in PY3 calls cleanup if we try to "
                    "access the beast"
                )
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


@assert_cwd_unchanged(ok_to_chdir=True)
@with_tempfile(mkdir=True)
def test_getpwd_change_mode(tdir):
    from datalad import utils
    if utils._pwd_mode != 'PWD':
        raise SkipTest("Makes sense to be tested only in PWD mode, "
                       "but we seems to be beyond that already")
    # The evil plain chdir call
    os.chdir(tdir)
    # Just testing the logic of switching to cwd mode and issuing a warning
    with swallow_logs(new_level=logging.WARNING) as cml:
        pwd = getpwd()
        eq_(pwd, os.path.realpath(pwd))  # might have symlinks, thus realpath
    assert_in("symlinks in the paths will be resolved", cml.out)
    eq_(utils._pwd_mode, 'cwd')


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

    class WithoutReprClass:
        def __init__(self):
            self.a = "does not matter"

    @auto_repr
    class buga:
        def __init__(self):
            self.a = 1
            self.b = list(range(100))
            self.c = WithoutReprClass()
            self._c = "protect me"

        def some(self):
            return "some"

    assert_equal(
        repr(buga()),
        "buga(a=1, b=<<[0, 1, 2, 3, 4, 5, 6, ...>>, c=<WithoutReprClass>)"
    )
    assert_equal(buga().some(), "some")


def test_assure_iter():
    s = {1}
    assert assure_iter(None, set) == set()
    assert assure_iter(1, set) == s
    assert assure_iter(1, list) == [1]
    assert assure_iter(s, set) is s
    assert assure_iter(s, set, copy=True) is not s


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
    target_dict = dict(
        __ac_name='{user}', __ac_password='{password}',
        cookies_enabled='', submit='Log in'
    )
    string = '__ac_name={user}\n__ac_password={password}\nsubmit=Log ' \
               'in\ncookies_enabled='
    assert_equal(assure_dict_from_str(string), target_dict)
    assert_equal(assure_dict_from_str(
        target_dict),
        target_dict)


def test_assure_bool():
    for values, t in [
        (['True', 1, '1', 'yes', 'on'], True),
        (['False', 0, '0', 'no', 'off'], False)
    ]:
        for v in values:
            eq_(assure_bool(v), t)
    assert_raises(ValueError, assure_bool, "unknown")


def test_generate_chunks():
    ok_generator(generate_chunks([1], 1))
    eq_(list(generate_chunks([1], 1)), [[1]])
    eq_(list(generate_chunks([1], 2)), [[1]])
    eq_(list(generate_chunks([1, 2, 3], 2)), [[1, 2], [3]])
    # type is preserved
    eq_(list(generate_chunks((1, 2, 3), 2)), [(1, 2), (3,)])
    # no hangers
    eq_(list(generate_chunks((1, 2, 3, 4), 2)), [(1, 2), (3, 4)])
    assert_raises(AssertionError, list, generate_chunks([1], 0))


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
    eq_(unique(range(3), reverse=True), [0, 1, 2])
    eq_(unique((1, 0, 1, 3, 2, 0, 1)), [1, 0, 3, 2])
    eq_(unique((1, 0, 1, 3, 2, 0, 1), reverse=True), [3, 2, 0, 1])
    eq_(unique([]), [])
    eq_(unique([], reverse=True), [])
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)]), [(1, 2), (1,), (0, 3)])
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)], reverse=True),
        [(1,), (1, 2), (0, 3)])

    # with a key now
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)],
               key=itemgetter(0)), [(1, 2), (0, 3)])
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)],
               key=itemgetter(0), reverse=True), [(1, 2), (0, 3)])

    eq_(unique([(1, 2), (1, 3), (1, 2), (0, 3)],
               key=itemgetter(1)), [(1, 2), (1, 3)])
    eq_(unique([(1, 2), (1, 3), (1, 2), (0, 3)],
               key=itemgetter(1), reverse=True), [(1, 2), (0, 3)])


def test_all_same():
    ok_(all_same([0, 0, 0]))
    ok_(not all_same([0, 0, '0']))
    ok_(not all_same([]))

    def never_get_to_not_needed():
        yield 'a'
        yield 'a'
        yield 'b'
        raise ValueError("Should not get here since on b should return")

    ok_(not all_same(never_get_to_not_needed()))

    def gen1(n):
        for x in range(n):
            yield 'a'
    ok_(not all_same(gen1(0)))
    ok_(all_same(gen1(1)))
    ok_(all_same(gen1(2)))
    ok_(all_same(gen1(10)))


def test_partition():
    def fn(*args, **kwargs):
        left, right = partition(*args, **kwargs)
        return list(left), list(right)

    eq_(fn([False, True, False]),
        ([False, False], [True]))

    eq_(fn([1, 5, 4, 10], lambda x: x > 4),
        ([1, 4], [5, 10]))

    eq_(fn([1, 5, 4, 10], lambda x: x < 0),
        ([1, 5, 4, 10], []))


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
            # skynet DOB
            assert_equal(get_timestamp_suffix(0), '-1970-01-01T00:00:00+0000')
            assert_equal(get_timestamp_suffix(0, prefix="+"),
                         '+1970-01-01T00:00:00+0000')
            # yoh found no way to mock things out and didn't want to provide
            # explicit call to anything to get current time with the timezone,
            # so disabling this test for now besides that it should return smth
            # sensible ;)
            #with patch.object(time, 'localtime', lambda: 1):
            #    assert_equal(get_timestamp_suffix(),
            #  '-1970-01-01T00:00:01+0000')  # skynet is 1 sec old
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
    # now, non-utf8
    # Decoding could be deduced with high confidence when the string is
    # really encoded in that codepage
    mom_koi8r = u"мама".encode('koi8-r')
    eq_(assure_unicode(mom_koi8r), u"мама")
    eq_(assure_unicode(mom_koi8r, confidence=0.9), u"мама")
    mom_iso8859 = u'mamá'.encode('iso-8859-1')
    eq_(assure_unicode(mom_iso8859), u'mamá')
    eq_(assure_unicode(mom_iso8859, confidence=0.5), u'mamá')
    # but when we mix, it does still guess something allowing to decode:
    mixedin = mom_koi8r + u'東'.encode('iso2022_jp') + u'東'.encode('utf-8')
    ok_(isinstance(assure_unicode(mixedin), text_type))
    # but should fail if we request high confidence result:
    with assert_raises(ValueError):
        assure_unicode(mixedin, confidence=0.9)
    # For other, non string values, actually just returns original value
    # TODO: RF to actually "assure" or fail??  For now hardcoding that assumption
    assert assure_unicode(1) is 1


def test_as_unicode():
    eq_(as_unicode('grandchild_äöü東'), u'grandchild_äöü東')
    eq_(as_unicode(None), u"")
    eq_(as_unicode(1), u"1")
    # NOTE: u? is because result is different between PY2 (prefixes unicode repr
    # while in PY3 is no longer needed!  So aggregation result would differ between
    # PY2 and PY3
    # Didn't manage to make it work in PY2
    #TODO assert_re_in(u'\[1, .s., u?.東.\]', as_unicode([1, "s", u"東"]))
    eq_(as_unicode("01"), u"01")  # no some kind of conversion/stripping of numerals
    with assert_raises(TypeError) as cme:
        as_unicode(1, list)
    assert_in("1 is not of any of known or provided", str(cme.exception))


@with_tempfile(mkdir=True)
def test_path_prefix(path):
    eq_(get_path_prefix('/d1/d2', '/d1/d2'), '')
    # so we are under /d1/d2 so path prefix is ..
    eq_(get_path_prefix('/d1/d2', '/d1/d2/d3'), '..')
    eq_(get_path_prefix('/d1/d2/d3', '/d1/d2'), 'd3')
    # but if outside -- full path
    eq_(get_path_prefix('/d1/d2', '/d1/d20/d3'), '/d1/d2')
    with chpwd(path):
        eq_(get_path_prefix('.'), '')
        eq_(get_path_prefix('d1'), 'd1')
        eq_(get_path_prefix('d1', 'd2'), opj(path, 'd1'))
        eq_(get_path_prefix('..'), '..')


def test_get_trace():
    assert_raises(ValueError, get_trace, [], 'boom', 'does_not_matter')
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


def test_path_startswith():
    ok_(path_startswith('/a/b', '/a'))
    ok_(path_startswith('/a/b', '/a/b'))
    ok_(path_startswith('/a/b', '/a/b/'))
    ok_(path_startswith('/a/b/', '/a/b'))
    ok_(path_startswith('/a/b', '/'))
    ok_(path_startswith('/aaa/b/c', '/aaa'))
    nok_(path_startswith('/aaa/b/c', '/aa'))
    nok_(path_startswith('/a/b', '/a/c'))
    nok_(path_startswith('/a/b/c', '/a/c'))
    # must not mix relative and abs
    assert_raises(ValueError, path_startswith, 'a/b', '/a')
    assert_raises(ValueError, path_startswith, '/a/b', 'a')


def test_path_is_subpath():
    ok_(path_is_subpath('/a/b', '/a'))
    ok_(path_is_subpath('/a/b/c', '/a'))
    nok_(path_is_subpath('/a/b', '/a/b'))
    nok_(path_is_subpath('/a/b', '/a/b/'))
    nok_(path_is_subpath('/a/b/', '/a/b'))
    ok_(path_is_subpath('/a/b', '/'))
    ok_(path_is_subpath('/aaa/b/c', '/aaa'))
    nok_(path_is_subpath('/aaa/b/c', '/aa'))
    nok_(path_is_subpath('/a/b', '/a/c'))
    nok_(path_is_subpath('/a/b/c', '/a/c'))
    # must not mix relative and abs
    assert_raises(ValueError, path_is_subpath, 'a/b', '/a')
    assert_raises(ValueError, path_is_subpath, '/a/b', 'a')


def test_safe_print():
    """Just to test that we are getting two attempts to print"""

    called = [0]

    def _print(s):
        assert_equal(s, "bua")
        called[0] += 1
        if called[0] == 1:
            raise UnicodeEncodeError('crap', u"", 0, 1, 'whatever')

    with patch.object(__builtin__, 'print', _print):
        safe_print("bua")
    assert_equal(called[0], 2)


def test_probe_known_failure():

    # Note: we can't test the switch "datalad.tests.knownfailures.probe"
    # directly, since it was evaluated in the decorator already. So we need
    # to have different assertions in this test based on config and have it
    # tested across builds, which use different settings for that switch.

    @probe_known_failure
    def not_failing():
        pass

    @probe_known_failure
    def failing():
        raise AssertionError("Failed")

    from datalad import cfg
    switch = cfg.obtain("datalad.tests.knownfailures.probe")

    if switch:
        # if probing is enabled the failing is considered to be expected and
        # therefore the decorated function doesn't actually fail:
        failing()
        # in opposition a function that doesn't fail raises an AssertionError:
        assert_raises(AssertionError, not_failing)
    else:
        # if probing is disabled it should just fail/pass as is:
        assert_raises(AssertionError, failing)
        not_failing()


def test_skip_if():

    def dummy():
        raise AssertionError

    assert_raises(AssertionError, dummy)
    # if cond is False, call the decorated function:
    assert_raises(AssertionError, skip_if(cond=False, method='raise')(dummy))
    # raises SkipTest if cond is True
    assert_raises(SkipTest, skip_if(cond=True, method='raise')(dummy))
    # but with method 'pass', there is neither SkipTest nor AssertionError.
    # Instead the function call is just skipped:
    skip_if(cond=True, method='pass')(dummy)
    # But if condition is False, the original function is still called:
    assert_raises(AssertionError, skip_if(cond=False, method='pass')(dummy))


def test_skip_known_failure():

    # Note: we can't test the switch "datalad.tests.knownfailures.skip"
    # directly, since it was evaluated in the decorator already. So we need
    # to have different assertions in this test based on config and have it
    # tested across builds, which use different settings for that switch.

    @skip_known_failure
    def failing():
        raise AssertionError("Failed")

    from datalad import cfg
    switch = cfg.obtain("datalad.tests.knownfailures.skip")

    if switch:
        # if skipping is enabled, we shouldn't see the exception:
        failing()
    else:
        # if it's disabled, failing() is executed and therefore exception
        # is raised:
        assert_raises(AssertionError, failing)


def test_known_failure():

    @known_failure
    def failing():
        raise AssertionError("Failed")

    from datalad import cfg

    skip = cfg.obtain("datalad.tests.knownfailures.skip")
    probe = cfg.obtain("datalad.tests.knownfailures.probe")

    if skip:
        # skipping takes precedence over probing
        failing()
    elif probe:
        # if we probe a known failure it's okay to fail:
        failing()
    else:
        # not skipping and not probing results in the original failure:
        assert_raises(AssertionError, failing)


def test_known_failure_v6():

    @known_failure_v6
    def failing():
        raise AssertionError("Failed")

    from datalad import cfg

    v6 = cfg.obtain("datalad.repo.version") == 6
    skip = cfg.obtain("datalad.tests.knownfailures.skip")
    probe = cfg.obtain("datalad.tests.knownfailures.probe")

    if v6:
        if skip:
            # skipping takes precedence over probing
            failing()
        elif probe:
            # if we probe a known failure it's okay to fail:
            failing()
        else:
            # not skipping and not probing results in the original failure:
            assert_raises(AssertionError, failing)

    else:
        # behaves as if it wasn't decorated at all, no matter what
        assert_raises(AssertionError, failing)


def test_known_failure_direct_mode():

    @known_failure_direct_mode
    def failing():
        raise AssertionError("Failed")

    from datalad import cfg

    direct = cfg.obtain("datalad.repo.direct")
    skip = cfg.obtain("datalad.tests.knownfailures.skip")
    probe = cfg.obtain("datalad.tests.knownfailures.probe")

    if direct:
        if skip:
            # skipping takes precedence over probing
            failing()
        elif probe:
            # if we probe a known failure it's okay to fail:
            failing()
        else:
            # not skipping and not probing results in the original failure:
            assert_raises(AssertionError, failing)

    else:
        # behaves as if it wasn't decorated at all, no matter what
        assert_raises(AssertionError, failing)


from datalad.utils import read_csv_lines


@with_tempfile(content="h1 h2\nv1 2\nv2 3")
def test_read_csv_lines_basic(infile):
    # Just a basic test, next one with unicode
    gen = read_csv_lines(infile)
    ok_generator(gen)
    eq_(
        list(gen),
        [
            {u'h1': u'v1', u'h2': u'2'},
            {u'h1': u'v2', u'h2': u'3'},
        ]
    )


@with_tempfile(content=u"h1\th2\nv1\tдата".encode('utf-8'))
def test_read_csv_lines_tsv_unicode(infile):
    # Just a basic test, next one with unicode
    gen = read_csv_lines(infile)
    ok_generator(gen)
    eq_(
        list(gen),
        [
            {u'h1': u'v1', u'h2': u'дата'},
        ]
    )


@with_tempfile(content=u"h1\nv1\nv2")
def test_read_csv_lines_one_column(infile):
    # Just a basic test, next one with unicode
    eq_(
        list(read_csv_lines(infile)),
        [
            {u'h1': u'v1'},
            {u'h1': u'v2'},
        ]
    )


def _get_testm_tree(ind):
    """Generate a fake package with submodules

    We need to increment index for different tests since otherwise e.g.
    import_modules fails to import submodule if first import_module_from_file
    imports that one
    """
    return {
        'dltestm%d' % ind: {
            '__init__.py': '',
            'dlsub1': {'__init__.py': 'var = 1'},
            'dlsub2.py': 'var = 2'}
    }

@with_tree(tree=_get_testm_tree(1))
def test_import_modules(topdir):
    try:
        sys.path.append(topdir)
        mods = import_modules(['dlsub1', 'bogus'], 'dltestm1')
    finally:
        sys.path.pop(sys.path.index(topdir))
    eq_(len(mods), 1)
    eq_(mods[0].__name__, 'dltestm1.dlsub1')


@with_tree(tree=_get_testm_tree(2))
def test_import_module_from_file(topdir):
    with assert_raises(AssertionError):
        # we support only submodule files ending with .py ATM. TODO
        import_module_from_file(op.join(topdir, 'dltestm2', 'dlsub1'))

    dlsub2_path = op.join(topdir, 'dltestm2', 'dlsub2.py')
    mod = import_module_from_file(dlsub2_path)
    eq_(mod.__name__, 'dlsub2')  # we are not asking to import as submod of the dltestm1
    assert_in('dlsub2', sys.modules)

    try:
        sys.path.append(topdir)
        import dltestm2
        mod = import_module_from_file(dlsub2_path, pkg=dltestm2)
        eq_(mod.__name__, 'dltestm2.dlsub2')
        assert_in('dltestm2.dlsub2', sys.modules)
    finally:
        sys.path.pop(sys.path.index(topdir))


def test_import_modules_fail():
    # test that we log failures correctly
    failures = []
    import_modules(['bogus'], 'datalad', 'Fail {package}.{module}', failures.append)
    eq_(len(failures), 1)
    ok_startswith(failures[0], "Fail datalad.bogus: No module")


# Should be the last one since as discovered in NICEMAN might screw up coverage
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


@with_tempfile(mkdir=True)
def test_dlabspath(path):
    # initially ran into on OSX https://github.com/datalad/datalad/issues/2406
    opath = opj(path, "origin")
    os.makedirs(opath)
    lpath = opj(path, "linked")
    os.symlink('origin', lpath)
    for d in opath, lpath:
        # regardless under which directory, all results should not resolve
        # anything
        eq_(d, dlabspath(d))
        # in the root of ds
        with chpwd(d):
            eq_(dlabspath("bu"), opj(d, "bu"))
            eq_(dlabspath("./bu"), opj(d, "./bu"))  # we do not normpath by default
            eq_(dlabspath("./bu", norm=True), opj(d, "bu"))


@with_tree({'1': 'content', 'd': {'2': 'more'}})
def test_get_open_files(p):
    skip_if_no_module('psutil')
    eq_(get_open_files(p), {})
    f1 = opj(p, '1')
    subd = opj(p, 'd')
    with open(f1) as f:
        # since lsof does not care about PWD env var etc, paths
        # will not contain symlinks, we better realpath them
        # all before comparison
        eq_(get_open_files(p, log_open=40)[op.realpath(f1)].pid,
            os.getpid())

    assert not get_open_files(subd)
    # if we start a process within that directory, should get informed
    from subprocess import Popen, PIPE
    from time import time
    t0 = time()
    proc = Popen([sys.executable, '-c',
                  r'import sys; sys.stdout.write("OK\n"); sys.stdout.flush();'
                  r'import time; time.sleep(10)'],
                 stdout=PIPE,
                 cwd=subd)
    # Assure that it started and we read the OK
    eq_(assure_unicode(proc.stdout.readline().strip()), u"OK")
    assert time() - t0 < 5 # that we were not stuck waiting for process to finish
    eq_(get_open_files(p)[op.realpath(subd)].pid, proc.pid)
    eq_(get_open_files(subd)[op.realpath(subd)].pid, proc.pid)
    proc.terminate()
    assert not get_open_files(subd)


def test_map_items():
    def add10(x):
        return x + 10
    eq_(map_items(add10, {2: 3}), {12: 13})

    class Custom(object):
        """For testing with custom items possibly of varying length etc"""
        def __init__(self, items):
            self._items = list(items)

        def items(self):
            return self._items

    c = Custom([(1,), (2, 3), (4, 5, 6)])
    c_mapped = map_items(add10, c)
    assert type(c) is type(c_mapped)
    eq_(c_mapped.items(), [(11,), (12, 13), (14, 15, 16)])


def test_CMD_MAX_ARG():
    # 100 is arbitrarily large small integer ;)
    # if fails -- we are unlikely to be able to work on this system
    # and something went really wrong!
    assert_greater(CMD_MAX_ARG, 100)


@with_tempfile(mkdir=True)
def test_create_tree(path):
    content = u"мама мыла раму"
    create_tree(path, OrderedDict([
        ('1', content),
        ('sd', OrderedDict(
            [
            # right away an obscure case where we have both 1 and 1.gz
                ('1', content*2),
                ('1.gz', content*3),
            ]
        )),
    ]))
    ok_file_has_content(op.join(path, '1'), content)
    ok_file_has_content(op.join(path, 'sd', '1'), content*2)
    ok_file_has_content(op.join(path, 'sd', '1.gz'), content*3, decompress=True)


def test_never_fail():

    @never_fail
    def iamok(arg):
        return arg
    eq_(iamok(1), 1)

    @never_fail
    def ifail(arg):
        raise ValueError
    eq_(ifail(1), None)

    with patch.dict('os.environ', {'DATALAD_ALLOW_FAIL': '1'}):
        # decision to create failing or not failing function
        # is done at the time of decoration
        @never_fail
        def ifail2(arg):
            raise ValueError

        assert_raises(ValueError, ifail2, 1)


@with_tempfile
def test_is_interactive(fout):
    # must not fail if one of the streams is no longer open:
    # https://github.com/datalad/datalad/issues/3267
    from ..cmd import Runner

    bools = ["False", "True"]

    def get_interactive(py_pre="", **run_kwargs):
        out, err = Runner().run(
            [sys.executable,
             "-c",
             py_pre +
             'from datalad.utils import is_interactive; '
             'f = open(%r, "w"); '
             'f.write(str(is_interactive())); '
             'f.close()'
             % fout
             ],
            **run_kwargs
        )
        with open(fout) as f:
            out = f.read()
        assert_in(out, bools)
        return bool(bools.index(out))

    # we never request for pty in our Runner, so can't be interactive
    eq_(get_interactive(), False)
    # and it must not crash if smth is closed
    for o in ('stderr', 'stdin', 'stdout'):
        eq_(get_interactive("import sys; sys.%s.close(); " % o), False)

