# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for download-url command

"""

__docformat__ = 'restructuredtext'

import os
from os.path import join as opj

from datalad.api import (
    Dataset,
    clone,
    download_url,
)
from datalad.tests.utils_pytest import (
    DEFAULT_REMOTE,
    assert_cwd_unchanged,
    assert_false,
    assert_in,
    assert_in_results,
    assert_message,
    assert_not_in,
    assert_result_count,
    create_tree,
    eq_,
    ok_,
    ok_exists,
    serve_path_via_http,
    skip_if_no_network,
    slow,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    Path,
    chpwd,
)


def test_download_url_exceptions():
    res0 = download_url(['url1', 'url2'], path=__file__,
                        save=False, on_failure='ignore')
    assert_result_count(res0, 1, status='error')
    assert_message("When specifying multiple urls, --path should point to "
                   "a directory target (with a trailing separator). Got %r",
                   res0)

    res1 = download_url('http://example.com/bogus',
                        save=False, on_failure='ignore')
    assert_result_count(res1, 1, status='error')
    msg = res1[0]['message']
    # when running under bogus proxy, on older systems we could get
    # no URL reported in the message
    if not (
        'Cannot connect to proxy.' in msg
        or
        'Temporary failure in name resolution' in msg
        or
        'Name or service not known' in msg  # nd80
        or
        'Failed to establish a new session' in msg  # Debian sid @ 20220121
    ):
        assert_in('http://example.com/bogus', msg)


@with_tree(tree={"dir": {}})
def test_download_url_existing_dir_no_slash_exception(path=None):
    with chpwd(path):
        res = download_url('url', path="dir", save=False, on_failure='ignore')
        assert_result_count(res, 1, status='error')
        assert_message("Non-directory path given (no trailing separator) "
                       "but a directory with that name (after adding "
                       "archive suffix) exists",
                       res)


@assert_cwd_unchanged
@with_tree(tree=[
    ('file1.txt', 'abc'),
    ('file2.txt', 'abc'),
])
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_return(toppath=None, topurl=None, outdir=None):
    # Ensure that out directory has trailing slash.
    outdir = opj(outdir, "")
    files = ['file1.txt', 'file2.txt']
    urls = [topurl + f for f in files]
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
    ('file7.txt', 'stu'),
    ('file8.txt', 'vwx'),
])
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_dataset(toppath=None, topurl=None, path=None):
    # Non-dataset directory.
    file1_fullpath = opj(path, "file1.txt")
    with chpwd(path):
        download_url(topurl + "file1.txt")
        ok_exists(file1_fullpath)
    os.remove(file1_fullpath)

    files_tosave = ['file1.txt', 'file2.txt']
    urls_tosave = [topurl + f for f in files_tosave]

    ds = Dataset(opj(path, "ds")).create()

    # By default, files are saved when called in a dataset.
    ds.download_url(urls_tosave)
    for fname in files_tosave:
        ok_(ds.repo.file_has_content(fname))

    eq_(ds.repo.get_urls("file1.txt"),
        [urls_tosave[0]])
    eq_(ds.repo.get_urls("file2.txt"),
        [urls_tosave[1]])

    ds.download_url([topurl + "file3.txt"], save=False)
    assert_false(ds.repo.file_has_content("file3.txt"))

    # Leading paths for target are created if needed.
    subdir_target = opj("l1", "l2", "f")
    ds.download_url([opj(topurl, "file1.txt")], path=subdir_target)
    ok_(ds.repo.file_has_content(subdir_target))

    subdir_path = opj(ds.path, "subdir", "")
    os.mkdir(subdir_path)
    with chpwd(subdir_path):
        download_url(topurl + "file4.txt")
        download_url(topurl + "file5.txt", path="five.txt")
        ds.download_url(topurl + "file6.txt")
        download_url(topurl + "file7.txt", dataset=ds.path)
    # download_url calls within a subdirectory save the file there
    ok_(ds.repo.file_has_content(opj("subdir", "file4.txt")))
    ok_(ds.repo.file_has_content(opj("subdir", "five.txt")))
    # ... unless the dataset instance is provided
    ok_(ds.repo.file_has_content("file6.txt"))
    # ... but a string for the dataset (as it would be from the command line)
    # still uses CWD semantics
    ok_(ds.repo.file_has_content(opj("subdir", "file7.txt")))

    with chpwd(path):
        # We're in a non-dataset path and pass in a string as the dataset. The
        # path is taken as relative to the current working directory, so we get
        # an error when trying to save it.
        assert_in_results(
            download_url(topurl + "file8.txt", dataset=ds.path,
                         on_failure="ignore"),
            status="error",
            action="status")
    assert_false((ds.pathobj / "file8.txt").exists())


@with_tree(tree={"archive.tar.gz": {'file1.txt': 'abc'}})
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_archive(toppath=None, topurl=None, path=None):
    ds = Dataset(path).create()
    ds.download_url([topurl + "archive.tar.gz"], archive=True)
    ok_(ds.repo.file_has_content(opj("archive", "file1.txt")))
    assert_not_in(opj(ds.path, "archive.tar.gz"),
                  ds.repo.format_commit("%B"))
    # we should yield an impossible from add archive content when there is
    # untracked content (gh-#6170)
    create_tree(ds.path, {'this': 'dirty'})
    assert_in_results(
        ds.download_url([topurl + "archive.tar.gz"], archive=True,
                        on_failure='ignore'),
        status='impossible',
        action='add-archive-content',
        message='clean dataset required. Use `datalad status` to inspect '
                'unsaved changes')


@with_tree(tree={"archive.tar.gz": {'file1.txt': 'abc'}})
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_archive_from_subdir(toppath=None, topurl=None, path=None):
    ds = Dataset(path).create()
    subdir_path = opj(ds.path, "subdir", "")
    os.mkdir(subdir_path)
    with chpwd(subdir_path):
        download_url([topurl + "archive.tar.gz"], archive=True)
    ok_(ds.repo.file_has_content(opj("subdir", "archive", "file1.txt")))


@with_tree(tree={"a0.tar.gz": {'f0.txt': 'abc'},
                 "a1.tar.gz": {'f1.txt': 'def'}})
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_archive_trailing_separator(toppath=None, topurl=None, path=None):
    ds = Dataset(path).create()
    # Archives will be extracted in the specified subdirectory, which doesn't
    # need to exist.
    ds.download_url([topurl + "a0.tar.gz"], path=opj("with-slash", ""),
                    archive=True)
    ok_(ds.repo.file_has_content(opj("with-slash", "a0", "f0.txt")))
    # But if the path doesn't have a trailing separator, it will not be
    # considered a directory. The archive will be downloaded to that path and
    # then extracted in the top-level of the dataset.
    ds.download_url([topurl + "a1.tar.gz"], path="no-slash",
                    archive=True)
    ok_(ds.repo.file_has_content(opj("a1", "f1.txt")))


@slow  # 12-14 sec
@skip_if_no_network
@with_tempfile(mkdir=True)
def test_download_url_need_datalad_remote(path=None):
    # publicly available (requires anonymous s3 access, so still needs our special remote)
    url = "s3://dandiarchive/ros3test.hdf5"
    path = Path(path)
    ds_a = Dataset(path / "a").create()
    ds_a.download_url([url], path="foo")
    ds_b = clone(source=ds_a.path, path=str(path / "b"),
                 result_xfm="datasets", return_type="item-or-list")
    ds_b.repo.remove_remote(DEFAULT_REMOTE)
    ds_b.get("foo")
    ok_(ds_b.repo.file_has_content("foo"))
