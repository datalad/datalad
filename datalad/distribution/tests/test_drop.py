# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test drop command
"""

from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import IncompleteResultsError
from datalad.tests.utils import (
    assert_status,
    assert_in,
    assert_raises,
    with_tree,
)


@with_tree({"foo": "foo"})
def test_drop_file_need_nocheck(path):
    ds = Dataset(path).create(force=True)
    ds.save()
    with assert_raises(IncompleteResultsError) as cme:
        ds.drop("foo")
    # The --force suggestion from git-annex-drop is translated to --nocheck.
    assert_in("--nocheck", str(cme.exception))
    assert_status("ok", ds.drop("foo", check=False, on_failure="ignore"))
