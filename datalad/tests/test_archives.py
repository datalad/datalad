#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:

import os
from os.path import join as opj, exists, lexists, isdir

from .utils import assert_true, assert_false, eq_, \
     with_tree, swallow_outputs, swallow_logs

from ..support.archives import decompress_file

tree_simplearchive = dict(
    tree=(
        ('simple.tar.gz', (
            ('2copy.txt', '2 load'),
            ('3.txt', '3 load'))),),
    prefix='datalad-')


@with_tree(**tree_simplearchive)
def check_decompress_file(leading_directories, path):
    outdir = opj(path, 'simple-extracted')

    with swallow_outputs() as cmo:
        decompress_file(opj(path, 'simple.tar.gz'), outdir,
                        leading_directories=leading_directories)
        eq_(cmo.out, "")
        eq_(cmo.err, "")

    if leading_directories == 'strip':
        assert_false(exists(opj(outdir, 'simple')))
        testdir = outdir
    elif leading_directories is None:
        assert_true(exists(opj(outdir, 'simple')))
        testdir = opj(outdir, 'simple')
    else:
        raise ValueError("Dunno about this strategy: %s" % leading_directories)

    assert_true(exists(opj(testdir, '3.txt')))
    assert_true(exists(opj(testdir, '2copy.txt')))
    with open(opj(testdir, '3.txt')) as f:
        eq_(f.read(), '3 load')


def test_decompress_file():
    yield check_decompress_file, None
    yield check_decompress_file, 'strip'
