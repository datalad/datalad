# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import exists
from requests.exceptions import InvalidURL

from ....utils import chpwd
from ....dochelpers import exc_str
from ....tests.utils import assert_true, assert_raises, assert_false
from ....tests.utils import SkipTest
from ....tests.utils import with_tempfile, skip_if_no_network, use_cassette
from ....tests.utils import skip_if_url_is_not_available
from datalad.crawler.pipelines.tests.utils import _test_smoke_pipelines
from datalad.crawler.pipelines.fcptable import *
from datalad.crawler.pipeline import run_pipeline


import logging
from logging import getLogger
lgr = getLogger('datalad.crawl.tests')

from ..fcptable import pipeline, superdataset_pipeline

TOPURL = "http://fcon_1000.projects.nitrc.org/fcpClassic/FcpTable.html"

def test_smoke_pipelines():
    yield _test_smoke_pipelines, pipeline, ['bogus']
    yield _test_smoke_pipelines, superdataset_pipeline, []


@use_cassette('test_fcptable_dataset')
@skip_if_no_network
@with_tempfile(mkdir=True)
def _test_dataset(dataset, error, create, skip, tmpdir):

    with chpwd(tmpdir):

        if create:
            with open("README.txt", 'w') as f:
                f.write(" ")

        pipe = [
            crawl_url(TOPURL),
            [
                assign({'dataset': dataset}),
                skip_if({'dataset': 'Cleveland CCF|Durham_Madden|NewYork_Test-Retest_Reliability'}, re=True),
                sub({'response': {'<div class="tableParam">([^<]*)</div>': r'\1'}}),
                find_dataset(dataset),
                extract_readme,
            ]
        ]

        if error:
            assert_raises((InvalidURL, RuntimeError), run_pipeline, pipe)
            return

        try:
            run_pipeline(pipe)
        except InvalidURL as exc:
            raise SkipTest(
                "This version of requests considers %s to be invalid.  "
                "See https://github.com/kennethreitz/requests/issues/3683#issuecomment-261947670 : %s"
                % (TOPURL, exc_str(exc)))

        if skip:
            assert_false(exists("README.txt"))
            return
        assert_true(exists("README.txt"))

        f = open("README.txt", 'r')
        contents = f.read()
        assert_true("Author(s)" and "Details" in contents)


def test_dataset():
    raise SkipTest('Bring back when NITRC is back (gh-1472)')

    skip_if_url_is_not_available(TOPURL, regex='service provider outage')
    yield _test_dataset, 'Baltimore', None, False, False
    yield _test_dataset, 'AnnArbor_b', None, False, False
    yield _test_dataset, 'Ontario', None, False, False
    yield _test_dataset, 'Boston', RuntimeError, False, False
    yield _test_dataset, "AnnArbor_b", None, True, False
    yield _test_dataset, "Cleveland CCF", None, False, True

