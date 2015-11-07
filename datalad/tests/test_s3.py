# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test S3 supporting functionality

"""

from ..support.s3 import get_versioned_url, S3_TEST_CREDENTIAL

from nose.tools import eq_, assert_raises
from nose import SkipTest
import keyring

from .utils import use_cassette


@use_cassette('fixtures/vcr_cassettes/s3_test0.yaml')
def test_version_url():
    if not keyring.get_password(S3_TEST_CREDENTIAL, 'secret_id'):
        raise SkipTest("Do not have access to S3 key/secret.  Test skipped")
    eq_(get_versioned_url("http://openfmri.s3.amazonaws.com/tarballs/ds001_raw.tgz"),
        "http://openfmri.s3.amazonaws.com/tarballs/ds001_raw.tgz?versionId=null")

    eq_(get_versioned_url("http://openfmri.s3.amazonaws.com/tarballs/ds001_raw.tgz?param=1"),
        "http://openfmri.s3.amazonaws.com/tarballs/ds001_raw.tgz?param=1&versionId=null")

    # something is wrong there
    #print(get_versioned_url("http://openfmri.s3.amazonaws.com/ds001/demographics.txt"))

    eq_(get_versioned_url("someurl"), "someurl")  # should just return original one
    assert_raises(RuntimeError, get_versioned_url, "someurl", guarantee_versioned=True)
    # TODO: on a bucket without versioning

    assert_raises(NotImplementedError, get_versioned_url, "s3://buga")

    urls = get_versioned_url("http://datalad-test0.s3.amazonaws.com/2versions-removed-recreated.txt",
                             return_all=True, verify=True)
    eq_(len(set(urls)), len(urls))  # all unique
    for url in urls:
        # so we didn't grab other files along with the same prefix
        assert(url.startswith('http://datalad-test0.s3.amazonaws.com/2versions-removed-recreated.txt?versionId='))
