# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target on Gitea"""

import pytest
import requests

from datalad.api import create_sibling_gitea
from datalad.tests.utils_pytest import (
    skip_if_no_network,
    skip_if_url_is_not_available,
    with_tempfile,
)

from .test_create_sibling_ghlike import check4real


@skip_if_no_network
@pytest.mark.flaky(retries=3, delay=5, only_on=[requests.exceptions.HTTPError])
@with_tempfile
def test_gitea(path=None):
    # demo.gitea.com is Gitea's public demo instance: no SLA, reset
    # regularly, and unreachable for long stretches. Its outage is not a
    # failure of this code base (gh-7912).
    skip_if_url_is_not_available('https://demo.gitea.com/api/v1/version')
    check4real(
        create_sibling_gitea,
        path,
        'gitea',
        'https://demo.gitea.com',
        'api/v1/repos/dataladtester/{reponame}',
    )
