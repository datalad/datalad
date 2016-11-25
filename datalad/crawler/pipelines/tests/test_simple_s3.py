# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import join as opj

from datalad.crawler.pipelines.tests.utils import _test_smoke_pipelines as _tsp
from ...nodes.annex import initiate_dataset
from ....utils import chpwd
from ....utils import _path_
from ....tests.utils import with_tree
from ....tests.utils import eq_, assert_not_equal, ok_, assert_raises
from ....tests.utils import with_tempfile
from ....tests.utils import serve_path_via_http
from ....tests.utils import ok_file_has_content
from ....tests.utils import ok_file_under_git
from ..simple_s3 import pipeline


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