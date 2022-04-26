# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target on GIN"""


from datalad.api import create_sibling_gin
from datalad.tests.utils_pytest import (
    assert_in_results,
    skip_if_no_network,
    with_tempfile,
)

from .test_create_sibling_ghlike import check4real


def check_push(ds):
    # create a file and push it to GIN to see of the
    # access is set up properly
    (ds.pathobj / 'file').write_text('some')
    ds.save()
    assert_in_results(
        ds.push(to='gin', result_renderer='disabled'),
        action='copy',
        status='ok',
        path=str(ds.pathobj / 'file')
    )


@skip_if_no_network
@with_tempfile
def test_gin(path=None):
    check4real(
        create_sibling_gin,
        path,
        'gin',
        'https://gin.g-node.org',
        # when testing locally, you might want to use your
        # own GIN account to not have to fiddle with the key
        # setup
        #'api/v1/repos/mih/{reponame}',
        'api/v1/repos/dataladtester/{reponame}',
        access_protocol='https-ssh',
        moretests=check_push,
    )
