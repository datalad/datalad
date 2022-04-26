# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target on GitHub"""


from datalad.api import create_sibling_github
from datalad.tests.utils_pytest import (
    skip_if_no_network,
    with_tempfile,
)

from .test_create_sibling_ghlike import check4real


@skip_if_no_network
@with_tempfile
def test_github(path=None):
    check4real(
        create_sibling_github,
        path,
        'github',
        'https://api.github.com',
        'repos/dataladtester/{reponame}',
    )
