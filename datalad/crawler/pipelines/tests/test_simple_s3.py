# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from glob import glob

from datalad.crawler.pipelines.tests.utils import _test_smoke_pipelines as _tsp
from ....utils import chpwd
from ....utils import _path_
from ....tests.utils import eq_
from ....tests.utils import assert_false
from ....tests.utils import with_tempfile
from ....tests.utils import use_cassette
from ....tests.utils import externals_use_cassette
from ....tests.utils import skip_if_no_network
from ..simple_s3 import pipeline
from datalad.api import crawl_init
from datalad.api import crawl
from datalad.api import create
from datalad.support.annexrepo import AnnexRepo
from datalad.downloaders.tests.utils import get_test_providers

from logging import getLogger
lgr = getLogger('datalad.crawl.tests')


def test_smoke_pipelines():
    yield _tsp, pipeline, ["b"]
    # to_http everywhere just to make it faster by avoiding initiating datalad
    # special remote
    yield _tsp, pipeline, ["b"], dict(to_http=True, prefix="prefix")
    yield _tsp, pipeline, ["b"], dict(to_http=True)
    yield _tsp, pipeline, ["b"], dict(to_http=True, archive=True)
    yield _tsp, pipeline, ["b"], dict(to_http=True, directory="subdataset", prefix="some/")


@with_tempfile
@use_cassette('test_simple_s3_test0_nonversioned_crawl')
@skip_if_no_network
def test_drop(path):
    get_test_providers('s3://datalad-test0-nonversioned')  # to verify having s3 credentials
    create(path)
    # unfortunately this doesn't work without force dropping since I guess vcr
    # stops and then gets queried again for the same tape while testing for
    # drop :-/
    with externals_use_cassette('test_simple_s3_test0_nonversioned_crawl_ext'), \
         chpwd(path):
        crawl_init(template="simple_s3",
                   args=dict(
                       bucket="datalad-test0-nonversioned",
                       drop=True,
                       drop_force=True  # so test goes faster
                   ),
                   save=True
                   )
        crawl()
    # test that all was dropped
    repo = AnnexRepo(path, create=False)
    files = glob(_path_(path, '*'))
    eq_(len(files), 8)
    for f in files:
        assert_false(repo.file_has_content(f))
