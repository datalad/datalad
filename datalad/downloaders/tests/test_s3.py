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
from unittest.mock import patch

from ..s3 import S3Authenticator
from ..s3 import S3Downloader
from ..providers import Providers  # to test against crcns

from ...tests.utils import (
    assert_equal,
    assert_raises,
    skip_if_no_network,
    SkipTest,
    swallow_outputs,
    use_cassette,
    with_tempfile,
    with_testsui,
)
from ...dochelpers import exc_str
from ...downloaders.base import DownloadError
from ...support.exceptions import AccessDeniedError

from ...utils import (
    md5sum,
)

from ...support import path as op

try:
    import boto
except Exception as e:
    raise SkipTest("boto module is not available: %s" % exc_str(e))

from .utils import get_test_providers
from .test_http import check_download_external_url

skip_if_no_network()  # TODO: provide persistent vcr fixtures for the tests

url_2versions_nonversioned1 = 's3://datalad-test0-versioned/2versions-nonversioned1.txt'
url_2versions_nonversioned1_ver1 = url_2versions_nonversioned1 + '?versionId=null'
url_2versions_nonversioned1_ver2 = url_2versions_nonversioned1 + '?versionId=V4Dqhu0QTEtxmvoNkCHGrjVZVomR1Ryo'
url_1version_bucketwithdot = 's3://datalad.test1/version1.txt'

url_dandi1 = 's3://dandiarchive/dandiarchive/dandiarchive/data/d8dd3e2b-8f74-494b-9370-9e3a6c69e2b0.csv.gz?versionId=9P7aMTvTT5wynPBOtiQqkV.wvV8zcpLf'


@use_cassette('test_s3_download_basic')
def test_s3_download_basic():

    for url, success_str, failed_str in [
        (url_2versions_nonversioned1, 'version2', 'version1'),
        (url_2versions_nonversioned1_ver2, 'version2', 'version1'),
        (url_2versions_nonversioned1_ver1, 'version1', 'version2'),
        (url_1version_bucketwithdot, 'version1', 'nothing')
    ]:
        yield check_download_external_url, url, failed_str, success_str

# TODO: redo smart way with mocking, to avoid unnecessary CPU waste
@use_cassette('test_s3_mtime')
@with_tempfile
def test_mtime(tempfile):
    url = url_2versions_nonversioned1_ver2
    with swallow_outputs():
        # without allow_old=False it might be reusing previous connection
        # which had already vcr tape for it, leading to failure.
        # TODO:  make allow_old configurable and then within tests disallow
        # allow_old
        get_test_providers(url).download(url, path=tempfile, allow_old_session=False)
    assert_equal(os.stat(tempfile).st_mtime, 1446873817)

    # and if url is wrong
    url = 's3://datalad-test0-versioned/nonexisting'
    assert_raises(DownloadError, get_test_providers(url).download, url, path=tempfile, overwrite=True)


@use_cassette('test_s3_reuse_session')
@with_tempfile
# forgot how to tell it not to change return value, so this side_effect beast now
@patch.object(S3Authenticator, 'authenticate', side_effect=S3Authenticator.authenticate, autospec=True)
def test_reuse_session(tempfile, mocked_auth):
    Providers.reset_default_providers()  # necessary for the testing below
    providers = get_test_providers(url_2versions_nonversioned1_ver1)  # to check credentials
    with swallow_outputs():
        providers.download(url_2versions_nonversioned1_ver1, path=tempfile)
    assert_equal(mocked_auth.call_count, 1)

    providers2 = Providers.from_config_files()
    with swallow_outputs():
        providers2.download(url_2versions_nonversioned1_ver2, path=tempfile, overwrite=True)
    assert_equal(mocked_auth.call_count, 1)

    # but if we reload -- everything reloads and we need to authenticate again
    providers2 = Providers.from_config_files(reload=True)
    with swallow_outputs():
        providers2.download(url_2versions_nonversioned1_ver2, path=tempfile, overwrite=True)
    assert_equal(mocked_auth.call_count, 2)

    Providers.reset_default_providers()  # necessary to avoid side-effects from having a vcr'ed connection
    # leaking through default provider's bucket, e.g. breaking test_mtime if ran after this one


def test_parse_url():
    from ..s3 import S3Downloader
    f = S3Downloader._parse_url
    b1 = "s3://bucket.name/file/path?revision=123"
    assert_equal(f(b1, bucket_only=True), 'bucket.name')
    assert_equal(f(b1), ('bucket.name', 'file/path', {'revision': '123'}))
    assert_equal(f("s3://b/f name"), ('b', 'f name', {}))
    assert_equal(f("s3://b/f%20name"), ('b', 'f name', {}))
    assert_equal(f("s3://b/f%2Bname"), ('b', 'f+name', {}))
    assert_equal(f("s3://b/f%2bname?r=%20"), ('b', 'f+name', {'r': '%20'}))


@with_testsui(interactive=True)
def test_deny_access():
    downloader = S3Downloader(authenticator=S3Authenticator())

    def deny_access(*args, **kwargs):
        raise AccessDeniedError

    with assert_raises(DownloadError):
        with patch.object(downloader, '_download', deny_access):
            downloader.download("doesn't matter")


@with_tempfile
def test_boto_host_specification(tempfile):
    # This test relies on a yoh-specific set of credentials to access
    # s3://dandiarchive . Unfortunately it seems that boto (2.49.0-2.1) might
    # have difficulties to establish a proper connection and would blow
    # with
    # The authorization mechanism you have provided is not supported. Please use AWS4-HMAC-SHA256.
    # Some related discussions:
    #   https://github.com/jschneier/django-storages/issues/28 which was closed
    # as superseded by a fix in 2017
    #   https://github.com/jschneier/django-storages/issues/28 .
    # In my case I still needed to resort to the workaround of providing
    # host = 's3.us-east-2.amazonaws.com' to the call.
    #
    # Unfortunately I do not know yet how we could establish such tests without
    # demanding specific credentials. And since we overload HOME for the testing,
    # the only way to run/test this at least when testing on my laptop is:
    credfile = '/home/yoh/.config/datalad/providers/dandi.cfg'
    # Later TODO: manage to reproduce such situation with our dedicated test
    # bucket, and rely on datalad-test-s3 credential
    if not op.exists(credfile):
        raise SkipTest("Test can run only on yoh's setup")
    providers = Providers.from_config_files([credfile])
    with swallow_outputs():
        providers.download(url_dandi1, path=tempfile)
    assert_equal(md5sum(tempfile), '97f4290b2d369816c052607923e372d4')
