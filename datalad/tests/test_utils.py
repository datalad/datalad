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
import pdb
from mock import patch
from contextlib import nested

from os.path import join as opj
from ..utils import (rotree, swallow_outputs, swallow_logs, setup_exceptionhook,
                    is_interactive)

from nose import SkipTest
from nose.tools import ok_, eq_, assert_false, assert_raises, assert_equal
from .utils import with_tempfile, assert_in, on_windows
from .. import utils
from ..cmd import Runner
from ..support.annexrepo import AnnexRepo


@with_tempfile(mkdir=True)
def test_rotree(d):
    d2 = opj(d, 'd1', 'd2')  # deep nested directory
    f = opj(d2, 'f1')
    os.makedirs(d2)
    with open(f, 'w') as f_:
        f_.write("LOAD")
    rotree(d)
    # we shouldn't be able to delete anything
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

@with_tempfile
def test_windows_gc_issue(path):
    if not on_windows:
        raise SkipTest
    else:
        ar = AnnexRepo(path)
        for i in range(10):
            try:
                with swallow_outputs() as cm:
                    x = str(list(range(1000))) + '\n'
                    ar.cmd_call_wrapper.run(['echo', x], log_online=True, log_stdout=False)
            except WindowsError, e:
                assert False, "Issue #147 probably not solved: %s" % e


def _check_setup_exceptionhook(interactive):
    old_exceptionhook = sys.excepthook

    post_mortem_tb = []
    def our_post_mortem(tb):
        post_mortem_tb.append(tb)

    with nested(
            patch('sys.excepthook'), 
            patch('datalad.utils.is_interactive', lambda: interactive),
            patch('pdb.post_mortem', our_post_mortem)):
        setup_exceptionhook()
        our_exceptionhook = sys.excepthook
        ok_(old_exceptionhook != our_exceptionhook)

        with swallow_logs() as cml, swallow_outputs() as cmo:
            # we need to call our_exceptionhook explicitly b/c nose
            # swallows all Exceptions and hook never gets executed
            try:
                raise RuntimeError
            except RuntimeError:
                type_, value_, tb_ = sys.exc_info()
            our_exceptionhook(type_, value_, tb_)
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
