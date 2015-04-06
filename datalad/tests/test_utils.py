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

import os, shutil
from os.path import join as opj
from ..utils import rotree

from nose.tools import ok_, eq_, assert_false, assert_raises
from .utils import with_tempfile, traverse_for_content, with_tree


@with_tempfile(mkdir=True)
def test_rotree(d):
    d2 = opj(d, 'd1', 'd2') # deep nested directory
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

@with_tree([
    ('loaded.txt', 'abracadabra'),
    ('empty.ascii', ''),
    ('d1', (
        ('loaded2.txt', '1 f load'),
        ('d2',
            (('empty', ''),
             )),
        )),
    ('d3', (
        ('empty.txt', ''),
        ('d2',
            (('empty', ''),
             )),
        ))
    ])
def test_traverse_for_content(d):
    # shouldn't blow if just ran without any callables and say that there is some load
    ok_(traverse_for_content(d))
    # but should report empty for
    eq_(traverse_for_content(opj(d, 'd1', 'd2')), False)
    eq_(traverse_for_content(opj(d, 'd3')), False)
    # but not upstairs for d1 since of loaded2.txt
    ok_(traverse_for_content(opj(d, 'd1')))

    # Verify that it seems to be calling callbacks appropriately
    def cb_dummy_noargs(d):
        ok_(d is not None)
        pass
    def cb_dummy_kwargs(d, empty_files=None, empty_dirs=None):
        ok_(d is not None)
        ok_(isinstance(empty_files, list))
        ok_(isinstance(empty_dirs, list))
        for f in empty_files:
            ok_(f.startswith('empty'))
        pass

    ok_(traverse_for_content(d,
                             do_all=cb_dummy_noargs,
                             do_none=cb_dummy_noargs,
                             do_any=cb_dummy_noargs))

    ok_(traverse_for_content(d,
                             do_all=cb_dummy_kwargs,
                             do_none=cb_dummy_kwargs,
                             do_any=cb_dummy_kwargs,
                             pass_files=True))
