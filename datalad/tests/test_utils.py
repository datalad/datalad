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

from os.path import join as opj, isabs, abspath
from ..utils import rotree, swallow_outputs, swallow_logs, setup_exceptionhook, md5sum
from ..utils import traverse_and_do, rm_misses, ls_tree
from ..utils import get_local_file_url, get_url_path
from ..utils import getpwd, chpwd
from ..support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_raises, assert_equal
from .utils import with_tempfile, assert_in, with_tree
from .utils import SkipTest
from .utils import ok_startswith
from .utils import on_windows
from .utils import assert_cwd_unchanged, skip_if_on_windows

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


@with_tree([
    ('loaded.txt', 'abracadabra'),
    ('empty.txt', ''),
    ('d1', (
        ('loaded2.txt', '1 f load'),
        ('d2',
            (('empty', ''),
             )),
        )),
    ('d3', (
        ('empty', ''),
        ('d2',
            (('empty', ''),
             )),
        )),
    ('d4', (
        ('loaded3', 'load'),
        )),
    ])
def test_traverse_and_do(d):
    # shouldn't blow if just ran without any callables and say that there is some load
    ok_(traverse_and_do(d))
    # but should report empty for
    eq_(traverse_and_do(opj(d, 'd1', 'd2')), False)
    eq_(traverse_and_do(opj(d, 'd3')), False)
    # but not upstairs for d1 since of loaded2.txt
    ok_(traverse_and_do(opj(d, 'd1')))
    ok_(traverse_and_do(opj(d, 'd4')))

    #
    # Verify that it seems to be calling callbacks appropriately
    #
    def cb_dummy_noargs(d_):
        ok_(d_ is not None)

    def cb_dummy_kwargs(d_, misses_files=None, misses_dirs=None):
        ok_(d_ is not None)
        ok_(isinstance(misses_files, list))
        ok_(isinstance(misses_dirs, list))
        for f in misses_files:
            ok_startswith(f, 'empty')

    ok_(traverse_and_do(d,
                        do_all=cb_dummy_noargs,
                        do_none=cb_dummy_noargs,
                        do_some=cb_dummy_noargs))

    ok_(traverse_and_do(d,
                        do_all=cb_dummy_kwargs,
                        do_none=cb_dummy_kwargs,
                        do_some=cb_dummy_kwargs,
                        pass_misses=True))

    # more thorough tests
    def cb_any(d_, misses_files=None, misses_dirs=None):
        ok_(d_ is not None)
        if d_ == d:
            eq_(misses_files, ['empty.txt'])
            eq_(misses_dirs, ['d3'])
        elif d_ == opj(d, 'd1'):
            # indeed we have empty d2 but loaded.txt
            eq_(misses_files, [])
            eq_(misses_dirs, ['d2'])
        else:
            raise ValueError("Must not be called for %d" % d_)

    def cb_all(d_, misses_files=None, misses_dirs=None):
        ok_(d_ is not None)
        if d_ == opj(d, 'd4'):
            eq_(misses_files, [])
            eq_(misses_dirs, [])
        else:
            raise ValueError("Must not be called for %s" % d_)

    def cb_none(d_, misses_files=None, misses_dirs=None):
        ok_(d_ is not None)
        if d_ in (opj(d, 'd1', 'd2'), opj(d, 'd3', 'd2')):
            eq_(misses_files, ['empty'])
            eq_(misses_dirs, [])
        elif d_ == opj(d, 'd3'):
            eq_(misses_files, ['empty'])
            eq_(misses_dirs, ['d2'])
        else:
            raise ValueError("Must not be called for %s" % d_)

    ok_(traverse_and_do(d,
                        do_all=cb_all,
                        do_none=cb_none,
                        do_some=cb_any,
                        pass_misses=True))


    # And now let's do some desired action -- clean it up!
    ok_(traverse_and_do(d,
                        do_none=rm_misses,
                        do_some=rm_misses,
                        pass_misses=True))
    # And check what is left
    eq_(ls_tree(d),
        ['d1', opj('d1', 'loaded2.txt'), 'd4', opj('d4', 'loaded3'), 'loaded.txt'])


@with_tree([
    ('empty.txt', ''),
    ('d1', (
        ('d2',
            (('empty', ''),
             )),
        )),
    ('d3', (
        ('empty', ''),
        ('d2',
            (('empty', ''),
             )),
        )),
    ('d4', (
        ('empty', ''),
        )),
    ])
def test_traverse_and_do_fully_empty(d):
    # And now let's do some desired action -- clean it up!
    ok_(not traverse_and_do(d,
                            do_none=rm_misses,
                            do_some=rm_misses,
                            pass_misses=True))
    # And check that nothing is left behind
    eq_(ls_tree(d), [])


@with_tree([
    ('loaded.txt', 'abracadabra'),
    ('empty.txt', ''),
    ('d1', (
        ('loaded2.txt', '1 f load'),
        ('d2',
            (('empty', ''),
             )),
        )),
    ('d3', (
        ('empty', ''),
        ('d2',
            (('empty', ''),
             )),
        )),
    ('d4', (
        ('loaded3', 'load'),
        )),
    ])
def test_traverse_and_do_annex_repo(d):
    from ..support.annexrepo import AnnexRepo
    ar = AnnexRepo(d)
    kw = {'matcher': ar.file_has_content,
          'pass_all_files': True}
    # since none of the files was added to annex yet -- should be all "empty"
    # for the beast
    ok_(not traverse_and_do(d, **kw))
    # but should report empty for
    eq_(traverse_and_do(opj(d, 'd1', 'd2')), False)
    eq_(traverse_and_do(opj(d, 'd3')), False)
    # but not upstairs for d1 since of loaded2.txt
    ok_(traverse_and_do(opj(d, 'd1')))
    ok_(traverse_and_do(opj(d, 'd4')))

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
    try:
        chpwd(sdir)
        pwd = getpwd()
        eq_(pwd, sdir)
        chpwd('s1')
        eq_(getpwd(), opj(sdir, 's1'))
        chpwd('.')
        eq_(getpwd(), opj(sdir, 's1'))
        chpwd('..')
        eq_(getpwd(), sdir)
    finally:
        chpwd(pwd_orig)

