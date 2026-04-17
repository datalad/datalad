# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target on GIN"""

import logging
import os
from os.path import basename
from unittest.mock import (
    MagicMock,
    patch,
)

import pytest
import requests

from datalad.api import (
    Dataset,
    create_sibling_gin,
)
from datalad.downloaders.http import DEFAULT_USER_AGENT
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_in,
    assert_in_results,
    assert_raises,
    assert_result_count,
    assert_status,
    eq_,
    slow,
    with_tempfile,
)


@slow  # could take 60-120 seconds, we should not time out
@with_tempfile
def test_invalid_call(path=None):
    # no dataset
    assert_raises(ValueError, create_sibling_gin, 'bogus', dataset=path)
    ds = Dataset(path).create()
    # without authorization
    # force disable any configured token
    with patch('datalad.distributed.create_sibling_ghlike.Token', None):
        assert_raises(ValueError, ds.create_sibling_gin, 'bogus')
    # unsupported name
    assert_raises(
        ValueError,
        ds.create_sibling_gin, 'bo  gus', credential='some')

    # conflicting sibling name
    ds.siblings('add', name='gin', url='http://example.com',
                result_renderer='disabled')
    res = ds.create_sibling_gin(
        'bogus', name='gin', credential='some', on_failure='ignore',
        dry_run=True)
    assert_status('error', res)
    assert_in_results(
        res,
        status='error',
        message=('already has a configured sibling "%s"', 'gin'))


@with_tempfile
def test_dryrun(path=None):
    ds = Dataset(path).create()
    # see that the correct request would be made
    res = ds.create_sibling_gin('bogus', credential='some', dry_run=True)
    assert_result_count(res, 1)
    res = res[0]
    eq_(res['request_url'], 'https://gin.g-node.org/api/v1/user/repos')
    # we dont care much which user-agent, but there should be one
    assert_in('user-agent', res['request_headers'])
    # only a placeholder no-token makes it into the request
    assert_in('NO-TOKEN-AVAILABLE', res['request_headers']['authorization'])
    # correct name
    eq_(res['request_data']['name'], 'bogus')
    # public by default
    eq_(res['request_data']['private'], False)
    # it is important that we do not tell the portal to generate some
    # repo content
    eq_(res['request_data']['auto_init'], False)

    # org repo
    res = ds.create_sibling_gin('strangeorg/bogus', credential='some',
                                dry_run=True)
    assert_result_count(res, 1)
    res = res[0]
    eq_(res['request_data']['name'], 'bogus')
    eq_(res['request_url'],
        'https://gin.g-node.org/api/v1/org/strangeorg/repos')

    # recursive name, building
    subds = ds.create('subds')
    res = ds.create_sibling_gin(
        'bogus', recursive=True, credential='some', dry_run=True)
    eq_(res[-1]['request_data']['name'], 'bogus-subds')

    # ignore unavailable datasets
    ds.drop('subds', what='all', reckless='kill', recursive=True)
    res = ds.create_sibling_gin(
        'bogus', recursive=True, credential='some', dry_run=True)
    eq_(len(res), 1)


def check4real(testcmd, testdir, credential, api, delete_endpoint,
            access_protocol='https', moretests=None):
    token_var = f'DATALAD_CREDENTIAL_{credential.upper()}_TOKEN'
    if token_var not in os.environ:
        raise SkipTest(f'No {credential} access token available')

    ds = Dataset(testdir).create()
    assert_raises(
        ValueError,
        testcmd,
        'somerepo',
        dataset=ds,
        api=api,
        credential='bogus',
    )

    reponame = basename(testdir).replace('datalad_temp_test', 'dltst')
    try:
        res = testcmd(
            reponame,
            dataset=ds,
            api=api,
            credential=credential,
            name='ghlike-sibling',
            access_protocol=access_protocol,
        )
        assert_in_results(
            res,
            status='ok',
            preexisted=False,
            reponame=reponame,
            private=False)
        assert_in_results(
            res,
            status='ok',
            action='configure-sibling',
            name='ghlike-sibling',
        )
        # now do it again
        ds.siblings('remove', name='ghlike-sibling', result_renderer='disabled')
        res = testcmd(
            reponame, dataset=ds, api=api, credential=credential,
            access_protocol=access_protocol,
            on_failure='ignore')
        assert_result_count(res, 1)
        assert_in_results(
            res,
            status='impossible',
            message="repository already exists",
            preexisted=True,
        )
        # existing=skip must not "fix" this:
        # https://github.com/datalad/datalad/issues/5941
        res = testcmd(reponame, dataset=ds, api=api, existing='skip',
                      access_protocol=access_protocol,
                      credential=credential, on_failure='ignore')
        assert_result_count(res, 1)
        assert_in_results(
            res,
            status='error',
            preexisted=True,
        )
        # but existing=reconfigure does
        res = testcmd(reponame, dataset=ds, api=api, existing='reconfigure',
                      access_protocol=access_protocol,
                      credential=credential)
        assert_result_count(res, 2)
        assert_in_results(
            res,
            status='notneeded',
            preexisted=True,
        )
        assert_in_results(
            res,
            action='configure-sibling',
            status='ok',
        )
        if moretests:
            moretests(ds)
    finally:
        token = os.environ[token_var]
        resp = requests.delete(
            '{}/{}'.format(api, delete_endpoint.format(reponame=reponame)),
            headers={
                'user-agent': DEFAULT_USER_AGENT,
                'authorization':
                    f'token {token}',
            },
        )
        # A 404 here means the repo was never created (e.g. creation
        # failed with 401/500) -- just warn so we don't mask the real error.
        if resp.status_code == 404:
            logging.getLogger(__name__).warning(
                "Cleanup DELETE returned 404 for %s (repo likely never created)",
                reponame)
        else:
            resp.raise_for_status()


def _mock_response(status_code):
    """Create a mock requests.Response with given status code."""
    r = MagicMock()
    r.status_code = status_code
    return r


@pytest.mark.ai_generated
def test_is_repo_already_exists_ghlike():
    from datalad.distributed.create_sibling_ghlike import _GitHubLike
    obj = _GitHubLike.__new__(_GitHubLike)

    # base: 422 + 'already exist' in message -> True
    r = _mock_response(requests.codes.unprocessable)
    assert obj._is_repo_already_exists(r, {'message': 'already exist'})

    # base: 422 without 'already exist' -> False
    assert not obj._is_repo_already_exists(r, {'message': 'other error'})
    assert not obj._is_repo_already_exists(r, {})

    # base: wrong status code -> False
    r = _mock_response(requests.codes.conflict)
    assert not obj._is_repo_already_exists(r, {'message': 'already exist'})


@pytest.mark.ai_generated
def test_is_repo_already_exists_github():
    from datalad.distributed.create_sibling_github import _GitHub
    obj = _GitHub.__new__(_GitHub)

    # GitHub: 422 + errors array with 'already exist' -> True
    r = _mock_response(requests.codes.unprocessable)
    assert obj._is_repo_already_exists(
        r, {'errors': [{'message': 'already exist'}]})

    # GitHub: 422 + errors without 'already exist' -> False
    assert not obj._is_repo_already_exists(
        r, {'errors': [{'message': 'other'}]})
    assert not obj._is_repo_already_exists(r, {'errors': []})
    assert not obj._is_repo_already_exists(r, {})

    # GitHub: wrong status code -> False
    r = _mock_response(requests.codes.conflict)
    assert not obj._is_repo_already_exists(
        r, {'errors': [{'message': 'already exist'}]})


@pytest.mark.ai_generated
def test_is_repo_already_exists_gitea():
    from datalad.distributed.create_sibling_gitea import _Gitea
    obj = _Gitea.__new__(_Gitea)

    # Gitea: 409 + 'already exist' in message -> True
    r = _mock_response(requests.codes.conflict)
    assert obj._is_repo_already_exists(r, {'message': 'already exist'})

    # Gitea: 409 without 'already exist' -> False
    assert not obj._is_repo_already_exists(r, {'message': 'other'})
    assert not obj._is_repo_already_exists(r, {})

    # Gitea: wrong status code -> False
    r = _mock_response(requests.codes.unprocessable)
    assert not obj._is_repo_already_exists(r, {'message': 'already exist'})
