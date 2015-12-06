# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for S3 downloader"""

from os.path import join as opj

from ..base import DownloadError, AccessDeniedError
from ..aws import S3Downloader

from ..providers import Providers, Credential  # to test against crcns

from ...tests.utils import SkipTest
from ...tests.utils import with_tempfile
from ...tests.utils import assert_false
from ...tests.utils import assert_in
from ...tests.utils import use_cassette

from .test_http import check_download_external_url

@use_cassette('fixtures/vcr_cassettes/test_s3_download_basic.yaml', record_mode='once')
def test_s3_download_basic():
    for url, success_str, failed_str in [
        ('s3://datalad-test0-versioned/2versions-nonversioned1.txt', 'version2', 'version1'),
        ('s3://datalad-test0-versioned/2versions-nonversioned1.txt?versionId=V4Dqhu0QTEtxmvoNkCHGrjVZVomR1Ryo', 'version2', 'version1'),
        ('s3://datalad-test0-versioned/2versions-nonversioned1.txt?versionId=null', 'version1', 'version2'),
    ]:
        yield check_download_external_url, url, failed_str, success_str
test_s3_download_basic.tags = ['network']


