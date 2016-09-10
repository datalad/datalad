# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from .utils import _test_smoke_pipelines
from ..crcns import pipeline, superdataset_pipeline


def test_smoke_pipelines():
    yield _test_smoke_pipelines, pipeline, ['bogus', "bogusgroup"]
    yield _test_smoke_pipelines, superdataset_pipeline, []
