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

from os.path import join as opj
from ..utils import rotree, swallow_outputs, swallow_logs, setup_exceptionhook, md5sum
from ..support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_raises, assert_equal
from .utils import with_tempfile, assert_in, with_tree
from .utils import SkipTest


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
    if not ar.is_crippled_fs():
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