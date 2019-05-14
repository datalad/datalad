# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test Dataset class @datasetmethod bindings without possible side effects
from needed otherwise datalad.api imports.

This one to be effective should be tested first or in isolation from other
test files
"""

from ..dataset import Dataset
from ...tests.utils import (
    assert_raises,
    with_tempfile,
)


@with_tempfile(mkdir=True)
def test_datasetmethod_bound(path):
    ds = Dataset(path)
    # should be automagically imported/picked up if not bound already
    assert ds.add  # simplest, intfspec only 2 entries
    assert ds.download_url  # 3 entries, with dash
    assert ds.create_sibling_github  # 3 entries, 2 dashes
    assert ds.aggregate_metadata  # module name is called "aggregate"
    assert ds.drop  # some fancy parametrization
    assert ds.get  # some fancy parametrization
    # plugins
    assert ds.addurls
    assert ds.wtf
    # if we ask for some really not known API - kaboom
    with assert_raises(AttributeError):
        ds.kaboommethod()
