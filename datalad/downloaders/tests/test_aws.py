# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for S3 downloader"""

import os
from ..aws import S3Downloader

from ..providers import Providers, Credential  # to test against crcns

from ...tests.utils import swallow_outputs
from ...tests.utils import SkipTest
from ...tests.utils import with_tempfile
from ...tests.utils import assert_equal
from ...tests.utils import assert_in
from ...tests.utils import use_cassette
from ...dochelpers import exc_str

try:
    import boto
except Exception as e:
    raise SkipTest("boto module is not available: %s" % exc_str(e))

from .test_http import check_download_external_url, _get_test_providers

@use_cassette('fixtures/vcr_cassettes/test_s3_download_basic.yaml', record_mode='once')
def test_s3_download_basic():
    for url, success_str, failed_str in [
        ('s3://datalad-test0-versioned/2versions-nonversioned1.txt', 'version2', 'version1'),
        ('s3://datalad-test0-versioned/2versions-nonversioned1.txt?versionId=V4Dqhu0QTEtxmvoNkCHGrjVZVomR1Ryo', 'version2', 'version1'),
        ('s3://datalad-test0-versioned/2versions-nonversioned1.txt?versionId=null', 'version1', 'version2'),
    ]:
        yield check_download_external_url, url, failed_str, success_str
test_s3_download_basic.tags = ['network']


# TODO: redo smart way with mocking, to avoid unnecessary CPU waste
@use_cassette('fixtures/vcr_cassettes/test_s3_mtime.yaml')
@with_tempfile
def test_mtime(tempfile):
    url = 's3://datalad-test0-versioned/2versions-nonversioned1.txt?versionId=V4Dqhu0QTEtxmvoNkCHGrjVZVomR1Ryo'
    with swallow_outputs():
        _get_test_providers().download(url, path=tempfile)
    assert_equal(os.stat(tempfile).st_mtime, 1446873817)
