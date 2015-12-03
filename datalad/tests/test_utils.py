# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test testing utilities

"""

import os
import shutil
import sys
import logging
from mock import patch
from six import PY3

from collections import OrderedDict

from ..utils import updated
from ..utils import get_local_file_url
from os.path import join as opj, isabs, abspath, exists
from ..utils import rotree, swallow_outputs, swallow_logs, setup_exceptionhook, md5sum
from ..utils import get_local_file_url, get_url_path
from ..utils import getpwd, chpwd
from ..utils import auto_repr
from ..support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_raises, assert_equal
from .utils import with_tempfile, assert_in, with_tree
from .utils import SkipTest
from .utils import assert_cwd_unchanged, skip_if_on_windows
from .utils import assure_dict_from_str, assure_list_from_str

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


def test_swallow_logs():
    lgr = logging.getLogger('datalad')
    with swallow_logs(new_level=9) as cm:
        eq_(cm.out, '')
        lgr.log(8, "very heavy debug")
        eq_(cm.out, '')  # not even visible at level 9
        lgr.log(9, "debug1")
        eq_(cm.out, 'debug1\n')  # not even visible at level 9
        lgr.info("info")
        eq_(cm.out, 'debug1\ninfo\n')  # not even visible at level 9


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
            except Exception as e: #RuntimeError:
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
                assert_in('We cannot setup exception hook', cml.out)

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

def test_get_local_file_url_linux():
    assert_equal(get_local_file_url('/a'), 'file:///a')
    assert_equal(get_local_file_url('/a/b/c'), 'file:///a/b/c')
    assert_equal(get_local_file_url('/a~'), 'file:///a%7E')
    assert_equal(get_local_file_url('/a b/'), 'file:///a%20b/')

@skip_if_on_windows
def test_get_url_path_on_fileurls():
    assert_equal(get_url_path('file:///a'), '/a')
    assert_equal(get_url_path('file:///a/b'), '/a/b')
    assert_equal(get_url_path('file:///a/b#id'), '/a/b')
    assert_equal(get_url_path('file:///a/b?whatever'), '/a/b')


def test_get_local_file_url_windows():
    raise SkipTest("TODO")

@assert_cwd_unchanged
def test_getpwd_basic():
    pwd = getpwd()
    ok_(isabs(pwd))
    eq_(os.getcwd(), abspath(pwd))


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
