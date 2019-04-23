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
import mock

import github as gh

from ..exceptions import AccessDeniedError
from ...tests.utils import assert_raises, assert_equal, eq_, assert_in

from ...utils import swallow_logs

from .. import github_
from ..github_ import get_repo_url


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
    github_passwd = 'fake'
    github_organization = 'fakeorg'
    rinfo = [
        # (ds, reponame) pairs
        ("/fakeds1", "fakeds1"),
        ("/fakeds2", "fakeds2"),
    ]
    existing = '???'
    access_protocol = '???'
    dryrun = False
    args = (
            github_login,
            github_passwd,
            github_organization,
            rinfo,
            existing,
            access_protocol,
            dryrun,
    )

    # with default mock, no attempts would be made and an exception will be raised
    with mock.patch.object(github_, '_gen_github_entity'):
        assert_raises(RuntimeError, github_._make_github_repos, *args)

    def _gen_github_entity(*args):
        return [("entity1", "cred1")]

    with mock.patch.object(github_, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(github_, '_make_github_repo'):
        res = github_._make_github_repos(*args)
    eq_(len(res), 2)
    # first entries are our datasets
    eq_(res[0][0], "/fakeds1")
    eq_(res[1][0], "/fakeds2")
    assert(all(len(x) > 1 for x in res))  # there is more than just a dataset

    #
    # Now test the logic whenever first credential fails and we need to get
    # to the next one
    #
    class FakeCred:
        def __init__(self, name):
            self.name = name

    # Let's test not blowing up whenever first credential is not good enough
    def _gen_github_entity(*args):
        return [
            ("entity1", FakeCred("cred1")),
            ("entity2", FakeCred("cred2")),
            ("entity3", FakeCred("cred3"))
        ]

    def _make_github_repo(github_login, entity, reponame, *args):
        if entity == 'entity1':
            raise gh.BadCredentialsException("very bad status", "some data")
        return reponame

    with mock.patch.object(github_, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(github_, '_make_github_repo', _make_github_repo), \
            swallow_logs(new_level=logging.INFO) as cml:
        res = github_._make_github_repos(*args)
        assert_in('Authentication failed using cred1', cml.out)
        eq_(res, [('/fakeds1', 'fakeds1'), ('/fakeds2', 'fakeds2')])

    def _make_github_repo(github_login, entity, reponame, *args):
        # Always throw an exception
        raise gh.BadCredentialsException("very bad status", "some data")

    with mock.patch.object(github_, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(github_, '_make_github_repo', _make_github_repo):
        with assert_raises(AccessDeniedError) as cme:
            github_._make_github_repos(*args)
        assert_in("Tried 3 times", str(cme.exception))