# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for S3 downloader"""

import os
from unittest.mock import patch

import pytest

from ...downloaders.base import DownloadError
from ...support import path as op
from ...support.exceptions import AccessDeniedError
from ...tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_raises,
    integration,
    skip_if_no_module,
    skip_if_no_network,
    swallow_outputs,
    turtle,
    use_cassette,
    with_tempfile,
    with_testsui,
)
from ...utils import md5sum
from ..providers import Providers  # to test against crcns
from ..s3 import (
    S3Authenticator,
    S3Downloader,
)
from .test_http import check_download_external_url
from .utils import get_test_providers

skip_if_no_module('boto3')
skip_if_no_network()  # TODO: provide persistent vcr fixtures for the tests

url_2versions_nonversioned1 = 's3://datalad-test0-versioned/2versions-nonversioned1.txt'
url_2versions_nonversioned1_ver1 = url_2versions_nonversioned1 + '?versionId=null'
url_2versions_nonversioned1_ver2 = url_2versions_nonversioned1 + '?versionId=V4Dqhu0QTEtxmvoNkCHGrjVZVomR1Ryo'
url_1version_bucketwithdot = 's3://datalad.test1/version1.txt'

url_dandi1 = 's3://dandiarchive/dandiarchive/dandiarchive/data/d8dd3e2b-8f74-494b-9370-9e3a6c69e2b0.csv.gz?versionId=9P7aMTvTT5wynPBOtiQqkV.wvV8zcpLf'


# disabled due to https://github.com/datalad/datalad/issues/7465
# @use_cassette('test_s3_download_basic')
@pytest.mark.parametrize("url,success_str,failed_str", [
    (url_2versions_nonversioned1, 'version2', 'version1'),
    (url_2versions_nonversioned1_ver2, 'version2', 'version1'),
    (url_2versions_nonversioned1_ver1, 'version1', 'version2'),
    (url_1version_bucketwithdot, 'version1', 'nothing'),
])
def test_s3_download_basic(url, success_str, failed_str):
    check_download_external_url(url, failed_str, success_str)


# TODO: redo smart way with mocking, to avoid unnecessary CPU waste
@use_cassette('test_s3_mtime')
@with_tempfile
def test_mtime(tempfile=None):
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
def test_reuse_session(tempfile=None, mocked_auth=None):
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

    def return_false(*args, **kwargs):
        return False

    with assert_raises(DownloadError):
        with patch.object(downloader, '_establish_session', return_false):
            with patch.object(downloader, '_download', deny_access):
                downloader.download("doesn't matter")


@use_cassette('test_anonymous_s3')
def test_anonymous_s3(tmp_path):
    downloader = S3Downloader(authenticator=S3Authenticator())
    downloader.download(
        "s3://openneuro.org/ds000001/dataset_description.json",
        path=str(tmp_path / "dataset_description.json"),
    )
    assert (tmp_path / "dataset_description.json").exists()



@with_tempfile
def test_boto_host_specification(tempfile=None):
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


# disabled due to https://github.com/datalad/datalad/issues/7464
def disabled_test_restricted_bucket_on_NDA():
    get_test_providers('s3://NDAR_Central_4/', reload=True)  # to verify having credentials to access
    for url, success_str, failed_str in [
        ("s3://NDAR_Central_4/submission_23075/README", 'BIDS', 'error'),
        ("s3://NDAR_Central_4/submission_23075/dataset_description.json", 'DA041147', 'error'),
    ]:
        check_download_external_url(url, failed_str, success_str)


# disabled due to https://github.com/datalad/datalad/issues/7464
@use_cassette('test_download_multiple_NDA')
@with_tempfile(mkdir=True)
def disabled_test_download_multiple_NDA(outdir=None):
    # This would smoke/integration test logic for composite credential testing expiration
    # of the token while reusing session from first url on the 2nd one
    urls = [
        "s3://NDAR_Central_4/submission_23075/README",
        "s3://NDAR_Central_4/submission_23075/dataset_description.json",
    ]
    providers = get_test_providers(urls[0], reload=True)  # to verify having credentials to access

    for url in urls:
        ret = providers.download(url, outdir)


# not really to be ran as part of the tests since it does
# largely nothing but wait for token to expire!
# It is still faster than waiting for real case to crash
@turtle  # over 900 sec since that is the min duration for token
@integration
@with_tempfile(mkdir=True)
def _test_expiring_token(outdir):
    url = "s3://datalad-test0-versioned/1version-removed-recreated.txt"
    outpath = op.join(outdir, "output")
    providers = get_test_providers(url, reload=True)
    downloader = providers.get_provider(url).get_downloader(url)

    from time import (
        sleep,
        time,
    )

    from datalad.downloaders.credentials import (
        AWS_S3,
        CompositeCredential,
        UserPassword,
    )
    from datalad.support.keyring_ import MemoryKeyring
    from datalad.tests.utils_pytest import ok_file_has_content
    credential = downloader.credential  # AWS_S3('datalad-test-s3')

    # We will replace credential with a CompositeCredential which will
    # mint new token after expiration
    # crap -- duration must be no shorter than 900, i.e. 15 minutes --
    # too long to wait for a test!
    duration = 900

    generated = []
    def _gen_session_token(_, key_id=None, secret_id=None):
        # TODO: RF for boto3
        from boto.sts.connection import STSConnection
        sts = STSConnection(aws_access_key_id=key_id,
                            aws_secret_access_key=secret_id)
        # Note: without force_new=True it will not re-request a token and would
        # just return old one if not expired yet.  Testing below might fail
        # if not entirely new
        token = sts.get_session_token(duration=duration, force_new=True)
        generated.append(token)
        return dict(key_id=token.access_key, secret_id=token.secret_key,
                    session=token.session_token,
                    expiration=token.expiration)

    class CustomS3(CompositeCredential):
        _CREDENTIAL_CLASSES = (UserPassword, AWS_S3)
        _CREDENTIAL_ADAPTERS = (_gen_session_token,)

    keyring = MemoryKeyring()
    downloader.credential = new_credential = CustomS3("testexpire", keyring=keyring)
    # but reuse our existing credential for the first part:
    downloader.credential._credentials[0] = credential

    # now downloader must use the token generator
    assert not generated  # since we have not called it yet

    # do it twice so we reuse session and test that we do not
    # re-mint a new token
    t0 = time()  # not exactly when we generated, might be a bit racy?
    for i in range(2):
        downloader.download(url, outpath)
        ok_file_has_content(outpath, "version1")
        os.unlink(outpath)
    # but we should have asked for a new token only once
    assert len(generated) == 1
    assert downloader.credential is new_credential  # we did not reset it

    # sleep for a while and now do a number of downloads during which
    # token should get refreshed etc

    # -3 since we have offset -2 hardcoded to refresh a bit ahead of time
    to_sleep = duration - (time() - t0) - 3
    print("Sleeping for %d seconds. Token should expire at %s" %
          (to_sleep, generated[0].expiration))
    sleep(to_sleep)

    for i in range(5):
        # should have not been regenerated yet
        # -2 is our hardcoded buffer
        if time() - t0 < duration - 2:
            assert len(generated) == 1
        downloader.download(url, outpath)
        ok_file_has_content(outpath, "version1")
        os.unlink(outpath)
        sleep(1)
    assert len(generated) == 2
