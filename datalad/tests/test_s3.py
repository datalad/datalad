# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test S3 supporting functionality

"""

from datalad.downloaders.tests.utils import get_test_providers
from datalad.support.network import URL
from datalad.support.s3 import (
    add_version_to_url,
    get_versioned_url,
)
from datalad.tests.utils_pytest import (
    assert_raises,
    eq_,
    ok_startswith,
    skip_if_no_network,
    use_cassette,
)


def test_add_version_to_url():
    base_url = "http://ex.com/f.txt"
    base_url_query = "http://ex.com/f.txt?k=v"
    for replace in True, False:
        eq_(add_version_to_url(URL(base_url), "new.id", replace=replace),
            base_url + "?versionId=new.id")

        eq_(add_version_to_url(URL(base_url_query),
                               "new.id", replace=replace),
            base_url_query + "&versionId=new.id")

        expected = "new.id" if replace else "orig.id"
        eq_(add_version_to_url(URL(base_url + "?versionId=orig.id"),
                               "new.id",
                               replace=replace),
            base_url + "?versionId=" + expected)

        eq_(add_version_to_url(URL(base_url_query + "&versionId=orig.id"),
                               "new.id",
                               replace=replace),
            base_url_query + "&versionId=" + expected)


@skip_if_no_network
@use_cassette('s3_test_version_url')
def test_get_versioned_url():
    get_test_providers('s3://openfmri/tarballs')  # to verify having credentials to access openfmri via S3
    for url_pref in ('http://openfmri.s3.amazonaws.com', 'https://s3.amazonaws.com/openfmri'):
        eq_(get_versioned_url(url_pref + "/tarballs/ds001_raw.tgz"),
            url_pref + "/tarballs/ds001_raw.tgz?versionId=null")

        eq_(get_versioned_url(url_pref + "/tarballs/ds001_raw.tgz?param=1"),
            url_pref + "/tarballs/ds001_raw.tgz?param=1&versionId=null")

        # We don't duplicate the version if it already exists.
        eq_(get_versioned_url(url_pref + "/tarballs/ds001_raw.tgz?versionId=null"),
            url_pref + "/tarballs/ds001_raw.tgz?versionId=null")

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

    # Update a versioned URL with a newer version tag.
    url_3ver = "http://datalad-test0-versioned.s3.amazonaws.com/3versions-allversioned.txt"
    url_3ver_input = url_3ver + "?versionId=b.qCuh7Sg58VIYj8TVHzbRS97EvejzEl"
    eq_(get_versioned_url(url_3ver_input), url_3ver_input)
    eq_(get_versioned_url(url_3ver_input, update=True),
        url_3ver + "?versionId=Kvuind11HZh._dCPaDAb0OY9dRrQoTMn")


@skip_if_no_network
@use_cassette('s3_test_version_url_anon')
def test_get_versioned_url_anon():
    # The one without any authenticator, was crashing.
    # Also it triggered another bug about having . in the bucket name
    url_on = "http://dandiarchive.s3.amazonaws.com/ros3test.nwb"
    url_on_versioned = get_versioned_url(url_on)
    ok_startswith(url_on_versioned, url_on + "?versionId=")


@skip_if_no_network
@use_cassette('s3_test_version_url_deleted')
def test_version_url_deleted():
    get_test_providers('s3://datalad-test0-versioned/', reload=True)  # to verify having credentials to access
    # openfmri via S3
    # it existed and then was removed
    fpath = "1version-removed.txt"
    url = "http://datalad-test0-versioned.s3.amazonaws.com/%s" % fpath
    turl = "http://datalad-test0-versioned.s3.amazonaws.com/%s" \
           "?versionId=eZ5Hgwo8azfBv3QT7aW9dmm2sbLUY.QP" % fpath
    eq_(get_versioned_url(url), turl)
    # too heavy for verification!
    #eq_(get_versioned_url(url, verify=True), turl)
