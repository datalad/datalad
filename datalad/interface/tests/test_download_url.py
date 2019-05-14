# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for install-dataset command

"""

__docformat__ = 'restructuredtext'

import os
from os.path import join as opj

from ...api import download_url, Dataset
from ...utils import chpwd
from ...tests.utils import ok_, ok_exists, eq_, assert_cwd_unchanged, \
    assert_in, assert_false, assert_message, assert_result_count, \
    with_tempfile
from ...tests.utils import assert_not_in
from ...tests.utils import with_tree
from ...tests.utils import serve_path_via_http


def test_download_url_exceptions():
    res0 = download_url(['url1', 'url2'], path=__file__,
                        save=False, on_failure='ignore')
    assert_result_count(res0, 1, status='error')
    assert_message('When specifying multiple urls, --path should point to '
                   'an existing directory. Got %r',
                   res0)

    res1 = download_url('http://example.com/bogus',
                        save=False, on_failure='ignore')
    assert_result_count(res1, 1, status='error')
    msg = res1[0]['message']
    # when running under bogus proxy, on older systems we could get
    # no URL reported in the message
    if 'Cannot connect to proxy.' not in msg:
        assert_in('http://example.com/bogus', msg)


@assert_cwd_unchanged
@with_tree(tree=[
    ('file1.txt', 'abc'),
    ('file2.txt', 'abc'),
])
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_return(toppath, topurl, outdir):
    files = ['file1.txt', 'file2.txt']
    urls = [opj(topurl, f) for f in files]
    outfiles = [opj(outdir, f) for f in files]

    out1 = download_url(urls[0], path=outdir, save=False)
    assert_result_count(out1, 1)
    eq_(out1[0]['path'], outfiles[0])

    # can't overwrite
    out2 = download_url(urls, path=outdir, on_failure='ignore', save=False)
    assert_result_count(out2, 1, status='error')
    assert_in('file1.txt already exists', out2[0]['message'])
    assert_result_count(out2, 1, status='ok')  # only 2nd one
    eq_(out2[1]['path'], outfiles[1])

    out3 = download_url(urls, path=outdir, overwrite=True,
                        on_failure='ignore', save=False)
    assert_result_count(out3, 2, status='ok')
    eq_([r['path'] for r in out3], outfiles)


@with_tree(tree=[
    ('file1.txt', 'abc'),
    ('file2.txt', 'def'),
    ('file3.txt', 'ghi'),
    ('file4.txt', 'jkl'),
    ('file5.txt', 'mno'),
    ('file6.txt', 'pqr'),
])
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_dataset(toppath, topurl, path):
    # Non-dataset directory.
    file1_fullpath = opj(path, "file1.txt")
    with chpwd(path):
        download_url(opj(topurl, "file1.txt"))
        ok_exists(file1_fullpath)
    os.remove(file1_fullpath)

    files_tosave = ['file1.txt', 'file2.txt']
    urls_tosave = [opj(topurl, f) for f in files_tosave]

    ds = Dataset(path).create()

    # By default, files are saved when called in a dataset.
    ds.download_url(urls_tosave)
    for fname in files_tosave:
        ok_(ds.repo.file_has_content(fname))

    eq_(ds.repo.get_urls("file1.txt"),
        [urls_tosave[0]])
    eq_(ds.repo.get_urls("file2.txt"),
        [urls_tosave[1]])

    ds.download_url([opj(topurl, "file3.txt")], save=False)
    assert_false(ds.repo.file_has_content("file3.txt"))

    subdir_path = opj(path, "subdir")
    os.mkdir(subdir_path)
    with chpwd(subdir_path):
        download_url(opj(topurl, "file4.txt"))
        download_url(opj(topurl, "file5.txt"), path="five.txt")
        ds.download_url(opj(topurl, "file6.txt"))
    # download_url calls within a subdirectory save the file there
    ok_(ds.repo.file_has_content(opj("subdir", "file4.txt")))
    ok_(ds.repo.file_has_content(opj("subdir", "five.txt")))
    # ... unless the dataset is provided.
    ok_(ds.repo.file_has_content("file6.txt"))


@with_tree(tree={"archive.tar.gz": {'file1.txt': 'abc'}})
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_archive(toppath, topurl, path):
    ds = Dataset(path).create()
    ds.download_url([opj(topurl, "archive.tar.gz")], archive=True)
    ok_(ds.repo.file_has_content(opj("archive", "file1.txt")))
    assert_not_in(opj(ds.path, "archive.tar.gz"),
                  ds.repo.format_commit("%B"))
