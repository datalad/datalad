# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the docker-registry:// downloader"""

import os

from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_in,
    eq_,
    integration,
    patch_config,
    skip_if,
    skip_if_no_network,
    slow,
    with_tempfile,
)


@skip_if(os.environ.get("TRAVIS_EVENT_TYPE") != "cron" and
         os.environ.get("GITHUB_EVENT_NAME") != "schedule",
         "run restricted cron due to rate limiting")
@skip_if_no_network
@slow  # ~7s
@integration
@with_tempfile(mkdir=True)
def test_download_docker_blob(path=None):
    from datalad.consts import (
        DATALAD_SPECIAL_REMOTE,
        DATALAD_SPECIAL_REMOTES_UUIDS,
    )
    from datalad.customremotes.base import init_datalad_remote

    with patch_config({"datalad.repo.backend": "SHA256E"}):
        ds = Dataset(path).create()
    ds_repo = ds.repo
    init_datalad_remote(ds_repo, DATALAD_SPECIAL_REMOTE)

    id_ = "f0b02e9d092d905d0d87a8455a1ae3e9bb47b4aa3dc125125ca5cd10d6441c9f"
    outfile = ds_repo.pathobj / "blob"
    url = "https://registry-1.docker.io/v2/library/busybox/blobs/sha256:" + id_
    ds.download_url(urls=[url], path=str(outfile))

    annex_info = ds.repo.get_content_annexinfo(paths=[outfile], init=None)
    eq_(id_, annex_info[outfile]["keyname"])
    assert_in(DATALAD_SPECIAL_REMOTES_UUIDS[DATALAD_SPECIAL_REMOTE],
              ds_repo.whereis([str(outfile)])[0])
