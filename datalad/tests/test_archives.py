#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:

import os
from os.path import join as opj, exists, lexists, isdir

from .utils import assert_true, assert_false, eq_, \
     with_tree, swallow_outputs, on_windows

from ..support.archives import decompress_file, unixify_path

from .utils import get_most_obscure_supported_name, assert_raises

fn_inarchive_obscure = get_most_obscure_supported_name()
fn_archive_obscure = fn_inarchive_obscure.replace('a', 'b')
fn_archive_obscure_ext = fn_archive_obscure + '.tar.gz'

tree_simplearchive = dict(
    tree=(
        (fn_archive_obscure_ext, (
            (fn_inarchive_obscure, '2 load'),
            ('3.txt', '3 load'))),),
    prefix='datalad-')

if on_windows:

    def test_unixify_path():
        from ..tests.utils import eq_
        eq_(unixify_path(r"a"), "a")
        eq_(unixify_path(r"c:\buga"), "/c/buga")
        eq_(unixify_path(r"c:\buga\duga.dat"), "/c/buga/duga.dat")
        eq_(unixify_path(r"buga\duga.dat"), "buga/duga.dat")


@with_tree(**tree_simplearchive)
def check_decompress_file(leading_directories, path):
    outdir = opj(path, 'simple-extracted')

    with swallow_outputs() as cmo:
        decompress_file(opj(path, fn_archive_obscure_ext), outdir,
                        leading_directories=leading_directories)
        eq_(cmo.out, "")
        eq_(cmo.err, "")

    path_archive_obscure = opj(outdir, fn_archive_obscure)
    if leading_directories == 'strip':
        assert_false(exists(path_archive_obscure))
        testpath = outdir
    elif leading_directories is None:
        assert_true(exists(path_archive_obscure))
        testpath = path_archive_obscure
    else:
        raise NotImplementedError("Dunno about this strategy: %s"
                                  % leading_directories)

    assert_true(exists(opj(testpath, '3.txt')))
    assert_true(exists(opj(testpath, fn_inarchive_obscure)))
    with open(opj(testpath, '3.txt')) as f:
        eq_(f.read(), '3 load')


def test_decompress_file():
    yield check_decompress_file, None
    yield check_decompress_file, 'strip'
    yield assert_raises, NotImplementedError, check_decompress_file, "unknown"
