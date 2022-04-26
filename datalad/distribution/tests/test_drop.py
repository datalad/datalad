# ex: set sts=4 ts=4 sw=4 et:
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
from datalad.tests.utils_pytest import (
    assert_in,
    assert_raises,
    assert_status,
    with_tree,
)


@with_tree({"foo": "foo"})
def test_drop_file_need_nocheck(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    with assert_raises(IncompleteResultsError) as cme:
        ds.drop("foo")
    # The --force suggestion from git-annex-drop is translated to --reckless.
    assert_in("--reckless", str(cme.value))
    assert_status("ok", ds.drop("foo", reckless='kill', on_failure="ignore"))
