# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test uninstall action

"""

from datalad.distribution.dataset import Dataset
from datalad.tests.utils import (
    assert_raises,
    with_tempfile,
)


@with_tempfile()
def test_uninstall_uninstalled(path):
    ds = Dataset(path)
    assert_raises(ValueError, ds.uninstall)
