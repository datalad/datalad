# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target github"""

from os.path import join as opj

from datalad import cfg

# this must import ok with and without pygithub
from datalad.api import (
    create_sibling_github,
    Dataset,
)
from datalad.utils import (
    assure_list,
    chpwd,
)
from datalad.tests.utils import (
    assert_equal,
    assert_false,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_true,
    eq_,
    skip_if_no_network,
    SkipTest,
    use_cassette as use_cassette_,
    with_memory_keyring,
    with_tempfile,
    with_testsui,
)
from datalad.support.exceptions import (
    MissingExternalDependency,
)
try:
    import github as gh
except ImportError:
    # make sure that the command complains too
    assert_raises(MissingExternalDependency, create_sibling_github, 'some')
    raise SkipTest


# Keep fixtures local to this test file
from datalad.support import path as op

FIXTURES_PATH = op.join(op.dirname(__file__), 'vcr_cassettes')


def use_cassette(name, *args, **kwargs):
    """Adapter to store fixtures locally

    TODO: RF so could be used in other places as well
    """
    return use_cassette_(op.join(FIXTURES_PATH, name + '.yaml'), *args, **kwargs)


@with_tempfile
def test_invalid_call(path):
    # no dataset
    assert_raises(ValueError, create_sibling_github, 'bogus', dataset=path)
    ds = Dataset(path).create()
    # no user
    assert_raises(gh.BadCredentialsException,
                  ds.create_sibling_github,
                  'bogus',
                  github_login='disabledloginfortesting')


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


# Ran on Yarik's laptop, so would use his available token
@skip_if_no_network
@use_cassette('github_yarikoptic')
def test_integration1_yarikoptic():
    # use case 1 - oauthtoken is known to git config, no 2FA (although irrelevant)
    check_integration1(
        'yarikoptic',
        oauthtokens='does not matter - vcr has "token"'
    )


@skip_if_no_network
@use_cassette('github_datalad_tester')
@with_testsui(responses=[
    'datalad-tester',
    'secret-password',
    'yes',      # Generate a GitHub token?
    '2FA code', # VCR tape has a real one
    'local',    # Where to store the token?
])
def test_integration1_datalad_tester():
    # use case 2 - nothing is known, 2FA, would generate 'DataLad token', and save it
    check_integration1('datalad-tester')


@skip_if_no_network
@use_cassette('github_datalad_tester_org')
@with_testsui(responses=[
     'secret-password',
     'yes',      # Generate a GitHub token?
     '2FA code', # VCR tape has a real one
     'local',    # Where to store the token?
])
def test_integration1_datalad_tester_org():
    # similar to use case 2 but into another organization,
    # providing login into the call
    check_integration1(
        'datalad-tester',
        organization='datalad-tester-org',
        # we do provide into the call as well
        kwargs={
            'github_login': 'datalad-tester'
        },
        # and we will give a number of tokens to "reject"
        oauthtokens=['fake1', 'fake2']
    )


@with_memory_keyring  # so that there is no leakage of credentials/side effects
@with_tempfile(mkdir=True)
def check_integration1(login, keyring,
                       path,
                       organization=None,
                       kwargs={},
                       oauthtokens=None):
    kwargs = kwargs.copy()
    if organization:
        kwargs['github_organization'] = organization

    ds = Dataset(path).create()
    if oauthtokens:
        for oauthtoken in assure_list(oauthtokens):
            ds.config.add('hub.oauthtoken', oauthtoken, where='local')

    # so we do not pick up local repo configuration/token
    repo_name = 'test_integration1'
    with chpwd(path):
        # ATM all the github goodness does not care about "this dataset"
        # so force "process wide" cfg to pick up our defined above oauthtoken
        cfg.reload(force=True)
        # everything works just nice, no conflicts etc
        res = ds.create_sibling_github(repo_name, **kwargs)

        if organization:
            url_fmt = 'https://{login}@github.com/{organization}/{repo_name}.git'
        else:
            url_fmt = 'https://github.com/{login}/{repo_name}.git'
        eq_(res, [(ds, url_fmt.format(**locals()), False)])

        # but if we rerun - should kaboom since already has this sibling:
        with assert_raises(ValueError) as cme:
            ds.create_sibling_github(repo_name, **kwargs)
        assert_in("already has a configured sibling", str(cme.exception))

        # but we can give it a new name, but it should kaboom since the remote one
        # exists already
        with assert_raises(ValueError) as cme:
            ds.create_sibling_github(repo_name, name="github2", **kwargs)
        assert_in("already exists on", str(cme.exception))
        # we should not leave the broken sibling behind
        assert_not_in('github2', ds.repo.get_remotes())

        # If we ask to reconfigure - should proceed normally
        ds.create_sibling_github(repo_name, existing='reconfigure', **kwargs)
    cfg.reload(force=True)
