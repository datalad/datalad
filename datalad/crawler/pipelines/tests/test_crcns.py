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
from ..crcns import get_metadata

from datalad.tests.utils import skip_if_no_network
from datalad.tests.utils import ok_startswith


def test_smoke_pipelines():
    yield _test_smoke_pipelines, pipeline, ['bogus', "bogusgroup"]
    yield _test_smoke_pipelines, superdataset_pipeline, []


@skip_if_no_network
def test_get_metadata():
    all_meta = get_metadata()
    assert len(all_meta) > 50  # so we have for all datasets
    # and each one of them should be a string (xml)
    assert all(x.startswith('<?xml') for x in all_meta.values())

    # but we could request one specific one
    aa1_meta = get_metadata('aa-1')
    ok_startswith(aa1_meta, '<?xml')
