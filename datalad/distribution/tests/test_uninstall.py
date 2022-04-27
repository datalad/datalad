# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test uninstall action

"""

import pytest

from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_raises,
    with_tempfile,
)


@pytest.mark.filterwarnings("ignore: The `uninstall` command is deprecated")
@with_tempfile()
def test_uninstall_uninstalled(path=None):
    ds = Dataset(path)
    assert_raises(ValueError, ds.uninstall)
