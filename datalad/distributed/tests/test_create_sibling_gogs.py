# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target on GOGS"""

from datalad.api import (
    Dataset,
    create_sibling_gogs,
)
from datalad.tests.utils_pytest import (
    assert_raises,
    skip_if_no_network,
    with_tempfile,
)

from .test_create_sibling_ghlike import check4real


@with_tempfile
def test_invalid_call(path=None):
    ds = Dataset(path).create()
    # no API url given
    assert_raises(ValueError, ds.create_sibling_gogs, 'bogus')


@skip_if_no_network
@with_tempfile
def test_gogs(path=None):
    # try.gogs.io will only handle 10 repos, but we need one
    # and could handle 10 concurrent test runs
    check4real(
        create_sibling_gogs,
        path,
        'gogs',
        'https://try.gogs.io',
        'api/v1/repos/dataladtester/{reponame}',
    )
