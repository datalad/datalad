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

from os.path import join as opj
from ..utils import (rotree, swallow_outputs, swallow_logs, setup_exceptionhook,
                    is_interactive)

from nose.tools import ok_, eq_, assert_false, assert_raises, assert_equal
from .utils import with_tempfile, assert_in


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


def test_setup_exceptionhook():
    old_exceptionhook = sys.excepthook
    setup_exceptionhook()
    our_exceptionhook = sys.excepthook
    ok_(old_exceptionhook != our_exceptionhook)

    post_mortem_tb = []
    def our_post_mortem(tb):
        post_mortem_tb.append(tb)
 
    pdb.post_mortem = our_post_mortem
    _tb = None
    with swallow_outputs() as cmo:
        # we need to call our_exceptionhook explicitly b/c nose
        # swallows all Exceptions and hook never gets executed
        # TODO throw real exception and use real args for type
        # value and traceback (tb) for this call:
        our_exceptionhook(None, None, _tb)
        assert_in('None', cmo.err)

    assert_equal(post_mortem_tb[0], _tb)
