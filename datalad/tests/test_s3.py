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

from nose.tools import eq_, assert_raises
from datalad.tests.utils import skip_if_no_network
from ..downloaders.tests.utils import get_test_providers

skip_if_no_network()  # ATM we don't ship fixtures, so if no network -- no network!


@use_cassette('s3_test0')
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
        assert(url.startswith('http://datalad-test0-versioned.s3.amazonaws.com/2versions-removed-recreated.txt?versionId='))
