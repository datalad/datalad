# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target github"""

import mock

from os.path import join as opj
# this must with with and without pygithub
from datalad.api import create_sibling_github
from datalad.api import Dataset
from datalad.support.exceptions import (
    AccessDeniedError,
    MissingExternalDependency,
)
from datalad.tests.utils import (
    eq_,
    swallow_logs,
    with_tempfile,
)
from nose.tools import assert_raises, assert_in, assert_true, assert_false, \
    assert_not_in, assert_equal
from nose import SkipTest

from ..create_sibling_github import get_repo_url

import logging

try:
    import github as gh
except ImportError:
    # make sure that the command complains too
    assert_raises(MissingExternalDependency, create_sibling_github, 'some')
    raise SkipTest


@with_tempfile
def test_invalid_call(path):
    # no dataset
    assert_raises(ValueError, create_sibling_github, 'bogus', dataset=path)
    ds = Dataset(path).create()
    # no user
    assert_raises(gh.BadCredentialsException, ds.create_sibling_github, 'bogus', github_login='disabledloginfortesting')


@with_tempfile
def test_dont_trip_over_missing_subds(path):
    ds1 = Dataset(opj(path, 'ds1')).create()
    ds2 = Dataset(opj(path, 'ds2')).create()
    subds2 = ds1.install(
        source=ds2.path, path='subds2',
        result_xfm='datasets', return_type='item-or-list')
    assert_true(subds2.is_installed())
    assert_in('subds2', ds1.subdatasets(result_xfm='relpaths'))
    subds2.uninstall()
    assert_in('subds2', ds1.subdatasets(result_xfm='relpaths'))
    assert_false(subds2.is_installed())
    # see if it wants to talk to github (and fail), or if it trips over something
    # before
    assert_raises(gh.BadCredentialsException,
        ds1.create_sibling_github, 'bogus', recursive=True,
        github_login='disabledloginfortesting')
    # inject remote config prior run
    assert_not_in('github', ds1.repo.get_remotes())
    # fail on existing
    ds1.repo.add_remote('github', 'http://nothere')
    assert_raises(ValueError,
        ds1.create_sibling_github, 'bogus', recursive=True,
        github_login='disabledloginfortesting')
    # talk to github when existing is OK
    assert_raises(gh.BadCredentialsException,
        ds1.create_sibling_github, 'bogus', recursive=True,
        github_login='disabledloginfortesting', existing='reconfigure')
    # return happy emptiness when all is skipped
    assert_equal(
        ds1.create_sibling_github(
            'bogus', recursive=True,
            github_login='disabledloginfortesting', existing='skip'),
        [])


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
    from .. import create_sibling_github as csgh
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
    with mock.patch.object(csgh, '_gen_github_entity'):
        assert_raises(RuntimeError, csgh._make_github_repos, *args)

    def _gen_github_entity(*args):
        return [("entity1", "cred1")]

    with mock.patch.object(csgh, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(csgh, '_make_github_repo'):
        res = csgh._make_github_repos(*args)
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

    with mock.patch.object(csgh, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(csgh, '_make_github_repo', _make_github_repo), \
            swallow_logs(new_level=logging.INFO) as cml:
        res = csgh._make_github_repos(*args)
        assert_in('Authentication failed using cred1', cml.out)
        eq_(res, [('/fakeds1', 'fakeds1'), ('/fakeds2', 'fakeds2')])

    def _make_github_repo(github_login, entity, reponame, *args):
        # Always throw an exception
        raise gh.BadCredentialsException("very bad status", "some data")

    with mock.patch.object(csgh, '_gen_github_entity', _gen_github_entity), \
            mock.patch.object(csgh, '_make_github_repo', _make_github_repo):
        with assert_raises(AccessDeniedError) as cme:
            csgh._make_github_repos(*args)
        assert_in("Tried 3 times", str(cme.exception))