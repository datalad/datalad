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


from ..support.s3 import get_versioned_url
from .utils import use_cassette
from .utils import ok_startswith

from nose.tools import eq_, assert_raises
from datalad.tests.utils import skip_if_no_network
from ..downloaders.tests.utils import get_test_providers

skip_if_no_network()  # ATM we don't ship fixtures, so if no network -- no network!


@use_cassette('s3_test_version_url')
def test_version_url():
    get_test_providers('s3://openfmri/tarballs')  # to verify having credentials to access openfmri via S3
    for url_pref in ('http://openfmri.s3.amazonaws.com', 'https://s3.amazonaws.com/openfmri'):
        eq_(get_versioned_url(url_pref + "/tarballs/ds001_raw.tgz"),
            url_pref + "/tarballs/ds001_raw.tgz?versionId=null")

        eq_(get_versioned_url("http://openfmri.s3.amazonaws.com/tarballs/ds001_raw.tgz?param=1"),
            "http://openfmri.s3.amazonaws.com/tarballs/ds001_raw.tgz?param=1&versionId=null")

    # something is wrong there
    #print(get_versioned_url("http://openfmri.s3.amazonaws.com/ds001/demographics.txt"))

    eq_(get_versioned_url("someurl"), "someurl")  # should just return original one
    assert_raises(RuntimeError, get_versioned_url, "someurl", guarantee_versioned=True)

    # TODO: on a bucket without versioning
    url = "http://datalad-test0-nonversioned.s3.amazonaws.com/2versions-removed-recreated.txt"
    eq_(get_versioned_url(url), url)
    eq_(get_versioned_url(url, return_all=True), [url])

    assert_raises(NotImplementedError, get_versioned_url, "s3://buga")

    urls = get_versioned_url("http://datalad-test0-versioned.s3.amazonaws.com/2versions-removed-recreated.txt",
                             return_all=True, verify=True)
    eq_(len(set(urls)), len(urls))  # all unique
    for url in urls:
        # so we didn't grab other files along with the same prefix
        ok_startswith(url, 'http://datalad-test0-versioned.s3.amazonaws.com/2versions-removed-recreated.txt?versionId=')


@use_cassette('s3_test_version_url_deleted')
def test_version_url_deleted():
    get_test_providers('s3://openneuro/')  # to verify having credentials to access
    # openfmri via S3
    # it existed and then was removed
    fpath = "ds000158/ds158_R1.0.1/compressed/ds000158_R1.0.1_sub001-055.zip"
    url = "http://openneuro.s3.amazonaws.com/%s" % fpath
    turl = "http://openneuro.s3.amazonaws.com/%s?versionId=null" % fpath
    eq_(get_versioned_url(url), turl)
    # too heavy for verification!
    #eq_(get_versioned_url(url, verify=True), turl)