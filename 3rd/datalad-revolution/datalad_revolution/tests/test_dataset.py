# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test RevolutionDataset"""


from datalad.api import rev_create as create

from datalad.tests.utils import (
    assert_true,
    assert_is_instance,
    assert_false,
    assert_is,
    with_tempfile,
)

from ..annexrepo import RevolutionAnnexRepo as AnnexRepo
from ..annexrepo import RevolutionGitRepo as GitRepo


@with_tempfile
def test_repo(path):
    """Test repo property of RevolutionDataset"""

    ds = create(path)
    subds = create("subds", dataset=ds)

    assert_true(subds.is_installed())
    assert_is_instance(subds.repo, (AnnexRepo, GitRepo))

    subds.uninstall()

    assert_false(subds.is_installed())
    assert_is(subds.repo, None)
