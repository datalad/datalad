# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ....support.annexrepo import AnnexRepo

from ....utils import chpwd
from ....utils import swallow_logs
from ....tests.utils import eq_, assert_not_equal, ok_, assert_raises
from ....tests.utils import with_tempfile

from ..nda import pipeline, bucket_pipeline, collection_pipeline

from logging import getLogger
lgr = getLogger('datalad.crawl.tests')


@with_tempfile(mkdir=True)
def test_smoke_pipelines(d):
    # Just to verify that we can correctly establish the pipelines
    AnnexRepo(d, create=True)
    with chpwd(d):
        with swallow_logs():
            for p in [pipeline('bogus'), bucket_pipeline(), collection_pipeline()]:
                ok_(len(p) > 1)
