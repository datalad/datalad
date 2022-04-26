# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for shub:// downloader"""

from datalad.downloaders.shub import SHubDownloader
from datalad.support.exceptions import DownloadError
from datalad.tests.utils_pytest import (
    assert_raises,
    ok_file_has_content,
    serve_path_via_http,
    with_tempfile,
)
from datalad.utils import (
    Path,
    create_tree,
)


@with_tempfile(mkdir=True)
@serve_path_via_http
def test_downloader_bad_query(urlpath=None, url=None):
    downloader = SHubDownloader()
    downloader.api_url = url
    with assert_raises(DownloadError):
        downloader.download("shub://org/repo", urlpath)


@with_tempfile(mkdir=True)
@serve_path_via_http
def test_downloader_bad_json(urlpath=None, url=None):
    downloader = SHubDownloader()
    downloader.api_url = url
    create_tree(urlpath,
                tree={"org": {"repo": ''}})
    with assert_raises(DownloadError):
        downloader.download("shub://org/repo", urlpath)


@with_tempfile(mkdir=True)
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_downloader_download(urlpath=None, url=None, path=None):
    path = Path(path)
    downloader = SHubDownloader()
    downloader.api_url = url
    create_tree(urlpath,
                tree={"data": "foo",
                      "org": {"repo":
                              '{{"name":"org/repo","image":"{}"}}'
                              .format(url + "data")}})

    target = str(path / "target")
    downloader.download("shub://org/repo", target)
    ok_file_has_content(target, "foo")

    other_target = str(path / "other-target")
    downloader.download("shub://org/repo", other_target)
