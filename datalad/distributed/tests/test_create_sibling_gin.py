# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target on GIN"""


from datalad.api import create_sibling_gin
from datalad.tests.utils import (
    skip_if_no_network,
    with_tempfile,
)

from .test_create_sibling_ghlike import check4real


@skip_if_no_network
@with_tempfile
def test_gin(path):
    check4real(
        create_sibling_gin,
        path,
        'gin',
        'https://gin.g-node.org',
        'api/v1/repos/dataladtester/{reponame}',
    )
