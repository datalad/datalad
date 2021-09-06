# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for github helpers"""

import logging
import unittest.mock as mock

import github as gh

from datalad.support.exceptions import AccessDeniedError
from datalad.tests.utils import (
    assert_equal,
    assert_greater,
    assert_in,
    assert_raises,
    eq_,
    patch_config,
    skip_if,
    skip_if_no_network,
)
from ...consts import (
    CONFIG_HUB_TOKEN_FIELD,
)
from datalad.utils import swallow_logs

from .. import github_
from ..github_ import (
    _gen_github_entity,
    _get_github_cred,
    _gh_exception,
    _token_str,
    get_repo_url,
)


skip_if_no_github_cred = skip_if(cond=not _get_github_cred().is_known)


def test_get_repo_url():
    from collections import namedtuple
    FakeRepo = namedtuple('FakeRepo', ('clone_url', 'ssh_url'))
    https_url1 = 'https://github.com/user1/repo'
    ssh_ri1 = 'git@github.com/user1/repo1'
    repo1 = FakeRepo(https_url1, ssh_ri1)

    assert_equal(get_repo_url(repo1, 'ssh', None), ssh_ri1)
    assert_equal(get_repo_url(repo1, 'ssh', 'user2'), ssh_ri1)  # no support for changing
    assert_equal(get_repo_url(repo1, 'https', None), https_url1)
    assert_equal(get_repo_url(repo1, 'https', 'user2'), 'https://user2@github.com/user1/repo')


def test__make_github_repos():
    github_login = 'test'
    github_organization = 'fakeorg'
    rinfo = [
        # (ds, reponame) pairs
        ("/fakeds1", "fakeds1"),
        ("/fakeds2", "fakeds2"),
    ]
    existing = '???'
    access_protocol = '???'
    private = False
    dryrun = False
    args = (
            github_login,
            github_organization,
            rinfo,
            existing,
            access_protocol,
            private,
            dryrun,
    )

    # with default mock, no attempts would be made and an exception will be raised
    with mock.patch.object(github_, '_gen_github_entity'):
        assert_raises(RuntimeError, list, github_._make_github_repos_(*args))

    def _gen_github_entity(*args):
        return [("entity1", "cred1")]

    with mock.patch.object(github_, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(github_, '_make_github_repo'):
        res = list(github_._make_github_repos_(*args))
    eq_(len(res), 2)

    #
    # Now test the logic whenever first token fails and we need to get
    # to the next one
    #
    # Let's test not blowing up whenever first credential is not good enough
    def _gen_github_entity(*args):
        return [
            ("entity%d" % i, _token_str("%dtokensomethinglong" % i))
            for i in range(1, 4)
        ]

    def _make_github_repo(github_login, entity, reponame, *args):
        if entity == 'entity1':
            raise _gh_exception(gh.BadCredentialsException,
                                "very bad status", "some data")
        return dict(status='ok')

    with mock.patch.object(github_, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(github_, '_make_github_repo', _make_github_repo), \
            swallow_logs(new_level=logging.INFO) as cml:
        res = list(github_._make_github_repos_(*args))
        assert_in('Failed to create repository while using token 1to...: BadCredentialsException(very bad status', cml.out)
        eq_(res,
            [dict(status='ok', ds='/fakeds1'), dict(status='ok', ds='/fakeds2')])

    def _make_github_repo(github_login, entity, reponame, *args):
        # Always throw an exception
        raise _gh_exception(gh.BadCredentialsException,
                            "very bad status", "some data")

    with mock.patch.object(github_, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(github_, '_make_github_repo', _make_github_repo):
        with assert_raises(AccessDeniedError) as cme:
            list(github_._make_github_repos_(*args))
        assert_in("Tried 3 times", str(cme.exception))


@skip_if_no_network
@skip_if_no_github_cred
def test__gen_github_entity_organization():
    # to test effectiveness of the fix, we need to provide some
    # token which would not work
    with patch_config({CONFIG_HUB_TOKEN_FIELD: "ed51111111111111111111111111111111111111"}):
        org_cred = next(_gen_github_entity(None, 'datalad-collection-1'))
    assert len(org_cred) == 2, "we return organization and credential"
    org, _ = org_cred
    assert org
    repos = list(org.get_repos())
    repos_names = [r.name for r in repos]
    assert_greater(len(repos), 3)  # we have a number of those
    assert_in('datasets.datalad.org', repos_names)
