# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target on Gitea"""


from datalad.api import create_sibling_gitea
from datalad.tests.utils_pytest import (
    skip_if_no_network,
    with_tempfile,
)

from .test_create_sibling_ghlike import check4real


@skip_if_no_network
@with_tempfile
def test_gitea(path=None):
    check4real(
        create_sibling_gitea,
        path,
        'gitea',
        'https://try.gitea.io',
        'api/v1/repos/dataladtester/{reponame}',
    )
