# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
from unittest.mock import patch
from datalad.tests.utils import (
    assert_true,
    assert_false,
    assert_raises,
    eq_,
    with_tree,
    with_tempfile,
    swallow_outputs,
    on_windows,
    ok_file_has_content,
    ok_generator,
    OBSCURE_FILENAME,
    SkipTest,
    skip_if,
)

from datalad.dochelpers import exc_str
from datalad.support.archives import (
    ArchivesCache,
    compress_files,
    decompress_file,
    ExtractedArchive,
)
from datalad.support.archive_utils_patool import unixify_path
from datalad.support.exceptions import MissingExternalDependency
from datalad.support.external_versions import external_versions
from datalad.support import path as op
from datalad import cfg as dl_cfg

fn_in_archive_obscure = OBSCURE_FILENAME
fn_archive_obscure = fn_in_archive_obscure.replace('a', 'b')
# Debian sid version of python (3.7.5rc1) introduced a bug in mimetypes
# Reported to cPython: https://bugs.python.org/issue38449
import mimetypes
mimedb = mimetypes.MimeTypes(strict=False)
if None in mimedb.guess_type(fn_archive_obscure + '.tar.gz'):
    from . import lgr
    lgr.warning("Buggy Python mimetypes, replacing ; in archives test filename")
    # fails to detect due to ;
    fn_archive_obscure = fn_archive_obscure.replace(';', '-')
    # verify
    assert None not in mimedb.guess_type(fn_archive_obscure + '.tar.gz')
fn_archive_obscure_ext = fn_archive_obscure + '.tar.gz'

tree_simplearchive = dict(
    tree=(
        (fn_archive_obscure_ext, (
            (fn_in_archive_obscure, '2 load'),
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
    outdir = op.join(path, 'simple-extracted')

    with swallow_outputs() as cmo:
        decompress_file(op.join(path, fn_archive_obscure_ext), outdir,
                        leading_directories=leading_directories)
        eq_(cmo.out, "")
        eq_(cmo.err, "")

    path_archive_obscure = op.join(outdir, fn_archive_obscure)
    if leading_directories == 'strip':
        assert_false(op.exists(path_archive_obscure))
        testpath = outdir
    elif leading_directories is None:
        assert_true(op.exists(path_archive_obscure))
        testpath = path_archive_obscure
    else:
        raise NotImplementedError("Dunno about this strategy: %s"
                                  % leading_directories)

    assert_true(op.exists(op.join(testpath, '3.txt')))
    assert_true(op.exists(op.join(testpath, fn_in_archive_obscure)))
    with open(op.join(testpath, '3.txt')) as f:
        eq_(f.read(), '3 load')


def test_decompress_file():
    yield check_decompress_file, None
    yield check_decompress_file, 'strip'
    yield assert_raises, NotImplementedError, check_decompress_file, "unknown"


@with_tree((('empty', ''),
            ('d1', (
                ('d2', (
                    ('f1', 'f1 load'),
                    ),),
            ))))
@with_tempfile()
def check_compress_dir(ext, path, name):
    archive = name + ext
    compress_files([os.path.basename(path)], archive,
                   path=os.path.dirname(path))
    assert_true(op.exists(archive))
    name_extracted = name + "_extracted"
    decompress_file(archive, name_extracted, leading_directories='strip')
    assert_true(op.exists(op.join(name_extracted, 'empty')))
    assert_true(op.exists(op.join(name_extracted, 'd1', 'd2', 'f1')))


def test_compress_dir():
    yield check_compress_dir, '.tar.xz'
    yield check_compress_dir, '.tar.gz'
    yield check_compress_dir, '.tgz'
    yield check_compress_dir, '.tbz2'
    yield check_compress_dir, '.tar'
    yield check_compress_dir, '.zip'
    yield check_compress_dir, '.7z'


# space in the filename to test for correct quotations etc
_filename = 'fi le.dat'


@skip_if("cmd:7z" not in external_versions,
         msg="Known to fail if p7zip is not installed")
@with_tree(((_filename, 'content'),))
@with_tempfile()
def check_compress_file(ext, annex, path, name):
    # we base the archive name on the filename, in order to also
    # be able to properly test compressors where the corresponding
    # archive format has no capability of storing a filename
    # (i.e. where the archive name itself determines the filename
    # of the decompressed file, like .xz)
    archive = op.join(name, _filename + ext)
    compress_files([_filename], archive,
                   path=path)
    assert_true(op.exists(archive))
    if annex:
        # It should work even when file is annexed and is a symlink to the
        # key
        from datalad.support.annexrepo import AnnexRepo
        repo = AnnexRepo(path, init=True)
        repo.add(_filename)
        repo.commit(files=[_filename], msg="commit")

    dir_extracted = name + "_extracted"
    try:
        decompress_file(archive, dir_extracted)
    except MissingExternalDependency as exc:
        raise SkipTest(exc_str(exc))
    _filepath = op.join(dir_extracted, _filename)

    ok_file_has_content(_filepath, 'content')


def test_compress_file():
    for annex in True, False:
        yield check_compress_file, '.xz', annex
        yield check_compress_file, '.gz', annex
        yield check_compress_file, '.zip', annex
        yield check_compress_file, '.7z', annex


@with_tree(**tree_simplearchive)
def test_ExtractedArchive(path):
    archive = op.join(path, fn_archive_obscure_ext)
    earchive = ExtractedArchive(archive)
    assert_false(op.exists(earchive.path))
    # no longer the case -- just using hash for now
    # assert_in(os.path.basename(archive), earchive.path)

    fpath = op.join(fn_archive_obscure,  # lead directory
                    fn_in_archive_obscure)
    extracted = earchive.get_extracted_filename(fpath)
    eq_(extracted, op.join(earchive.path, fpath))
    assert_false(op.exists(extracted))  # not yet

    extracted_ = earchive.get_extracted_file(fpath)
    eq_(extracted, extracted_)
    assert_true(op.exists(extracted))  # now it should

    extracted_files = earchive.get_extracted_files()
    ok_generator(extracted_files)
    eq_(sorted(extracted_files),
        sorted([
            # ['bbc/3.txt', 'bbc/abc']
            op.join(fn_archive_obscure, fn_in_archive_obscure),
            op.join(fn_archive_obscure, '3.txt')
        ]))

    earchive.clean()
    if not dl_cfg.get('datalad.tests.temp.keep'):
        assert_false(op.exists(earchive.path))

#@with_tree(**tree_simplearchive)
#@with_tree(**tree_simplearchive)
def test_ArchivesCache():
    # we don't actually need to test archives handling itself
    path1 = "/zuba/duba"
    path2 = "/zuba/duba2"
    # should not be able to create a persistent cache without topdir
    assert_raises(ValueError, ArchivesCache, persistent=True)
    cache = ArchivesCache()  # by default -- non persistent

    archive1_path = op.join(path1, fn_archive_obscure_ext)
    archive2_path = op.join(path2, fn_archive_obscure_ext)
    cached_archive1_path = cache[archive1_path].path
    assert_false(cache[archive1_path].path == cache[archive2_path].path)
    assert_true(cache[archive1_path] is cache[archive1_path])
    cache.clean()
    assert_false(op.exists(cached_archive1_path))
    assert_false(op.exists(cache.path))

    # test del
    cache = ArchivesCache()  # by default -- non persistent
    assert_true(op.exists(cache.path))
    cache_path = cache.path
    del cache
    assert_false(op.exists(cache_path))


def _test_get_leading_directory(ea, return_value, target_value, kwargs={}):
    with patch.object(ExtractedArchive, 'get_extracted_files', return_value=return_value):
        eq_(ea.get_leading_directory(**kwargs), target_value)


def test_get_leading_directory():
    ea = ExtractedArchive('/some/bogus', '/some/bogus')
    yield _test_get_leading_directory, ea, [], None
    yield _test_get_leading_directory, ea, ['file.txt'], None
    yield _test_get_leading_directory, ea, ['file.txt', op.join('d', 'f')], None
    yield _test_get_leading_directory, ea, [op.join('d', 'f'), op.join('d', 'f2')], 'd'
    yield _test_get_leading_directory, ea, [op.join('d', 'f'), op.join('d', 'f2')], 'd', {'consider': 'd'}
    yield _test_get_leading_directory, ea, [op.join('d', 'f'), op.join('d', 'f2')], None, {'consider': 'dd'}
    yield _test_get_leading_directory, ea, [op.join('d', 'f'), op.join('d2', 'f2')], None
    yield _test_get_leading_directory, ea, [op.join('d', 'd2', 'f'), op.join('d', 'd2', 'f2')], op.join('d', 'd2')
    yield _test_get_leading_directory, ea, [op.join('d', 'd2', 'f'), op.join('d', 'd2', 'f2')], 'd', {'depth': 1}
    # with some parasitic files
    yield _test_get_leading_directory, ea, [op.join('d', 'f'), op.join('._d')], 'd', {'exclude': ['\._.*']}
    yield _test_get_leading_directory, ea, [op.join('d', 'd1', 'f'), op.join('d', '._d'), '._x'], op.join('d', 'd1'), {'exclude': ['\._.*']}

