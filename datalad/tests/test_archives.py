#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:

import os
from os.path import join as opj, exists, lexists, isdir

from .utils import assert_true, assert_false, eq_, ok_, assert_greater, \
     with_tree, with_tempfile, sorted_files, rmtree, create_archive, \
     md5sum, ok_clean_git, ok_file_under_git

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
    decompress_file(opj(path, 'simple.tar.gz'), outdir,
                    leading_directories=leading_directories)

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
