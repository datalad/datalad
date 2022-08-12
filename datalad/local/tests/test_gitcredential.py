# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test git-credential wrapper and helper"""

from datalad.api import Dataset
from datalad.downloaders.credentials import UserPassword
from datalad.local.gitcredential import GitCredentialInterface
from datalad.tests.utils_pytest import (
    assert_false,
    assert_is_instance,
    assert_not_in,
    assert_true,
    eq_,
    with_tempfile,
)
from datalad.utils import (
    Path,
    chpwd,
)


@with_tempfile
def test_gitcredential_interface(path=None):
    # use a dataset as a local configuration vehicle
    ds = Dataset(path).create()

    # preserve credentials between git processes for a brief time
    # credential-cache is not supported on windows (needs UNIX sockets)
    # ds.config.set('credential.helper', 'cache', scope='local')
    # However, first set an empty helper in order to disable already set helpers
    ds.config.set('credential.helper', '', scope='local')
    ds.config.set('credential.helper', 'store', scope='local')

    # git manages credentials by target URL
    credurl = 'https://example.datalad.org/somepath'
    credurl_justhost = 'https://example.datalad.org'
    # define a credential
    cred = GitCredentialInterface(url=credurl, username='mike',
                                  password='s3cr3t', repo=ds)
    # put it in the manager (a cache in this case, but could invoke any number
    # of helpers
    cred.approve()
    # new instance, no knowledge of login
    cred = GitCredentialInterface(url=credurl, repo=ds)
    assert_not_in('username', cred)
    # query store
    cred.fill()
    eq_(cred['username'], 'mike')
    eq_(cred['password'], 's3cr3t')
    # git does host-only identification by default (see credential.useHttpPath)
    cred = GitCredentialInterface(url=credurl_justhost, repo=ds)
    cred.fill()
    eq_(cred['username'], 'mike')
    eq_(cred['password'], 's3cr3t')

    # the URL is enough to remove ("reject") a credential
    GitCredentialInterface(url=credurl, repo=ds).reject()

    cred = GitCredentialInterface(url=credurl, repo=ds)
    # this will yield empty passwords, not the most precise test
    # whether it actually removed the credentials, but some test
    # at least
    cred.fill()
    assert_false(cred['username'])
    assert_false(cred['password'])


@with_tempfile
def test_datalad_credential_helper(path=None):

    ds = Dataset(path).create()

    # tell git to use git-credential-datalad
    ds.config.add('credential.helper', 'datalad', scope='local')
    ds.config.add('datalad.credentials.githelper.noninteractive', 'true',
                  scope='global')

    from datalad.downloaders.providers import Providers

    url1 = "https://datalad-test.org/some"
    url2 = "https://datalad-test.org/other"
    provider_name = "datalad-test.org"

    # `Providers` code is old and only considers a dataset root based on PWD
    # for config lookup. contextmanager below can be removed once the
    # provider/credential system is redesigned.
    with chpwd(ds.path):

        gitcred = GitCredentialInterface(url=url1, repo=ds)

        # There's nothing set up yet, helper should return empty
        gitcred.fill()
        eq_(gitcred['username'], '')
        eq_(gitcred['password'], '')

        # store new credentials
        # Note, that `Providers.enter_new()` currently uses user-level config
        # files for storage only. TODO: make that an option!
        # To not mess with existing ones, fail if it already exists:

        cfg_file = Path(Providers._get_providers_dirs()['user']) \
                   / f"{provider_name}.cfg"
        assert_false(cfg_file.exists())

        # Make sure we clean up
        from datalad.tests import _TEMP_PATHS_GENERATED
        _TEMP_PATHS_GENERATED.append(str(cfg_file))

        # Give credentials to git and ask it to store them:
        gitcred = GitCredentialInterface(url=url1, username="dl-user",
                                         password="dl-pwd", repo=ds)
        gitcred.approve()

        assert_true(cfg_file.exists())
        providers = Providers.from_config_files()
        p1 = providers.get_provider(url=url1, only_nondefault=True)
        assert_is_instance(p1.credential, UserPassword)
        eq_(p1.credential.get('user'), 'dl-user')
        eq_(p1.credential.get('password'), 'dl-pwd')

        # default regex should be host only, so matching url2, too
        p2 = providers.get_provider(url=url2, only_nondefault=True)
        assert_is_instance(p1.credential, UserPassword)
        eq_(p1.credential.get('user'), 'dl-user')
        eq_(p1.credential.get('password'), 'dl-pwd')

        # git, too, should now find it for both URLs
        gitcred = GitCredentialInterface(url=url1, repo=ds)
        gitcred.fill()
        eq_(gitcred['username'], 'dl-user')
        eq_(gitcred['password'], 'dl-pwd')

        gitcred = GitCredentialInterface(url=url2, repo=ds)
        gitcred.fill()
        eq_(gitcred['username'], 'dl-user')
        eq_(gitcred['password'], 'dl-pwd')

        # Rejection must not currently lead to deleting anything, since we would
        # delete too broadly.
        gitcred.reject()
        assert_true(cfg_file.exists())
        gitcred = GitCredentialInterface(url=url1, repo=ds)
        gitcred.fill()
        eq_(gitcred['username'], 'dl-user')
        eq_(gitcred['password'], 'dl-pwd')
        dlcred = UserPassword(name=provider_name)
        eq_(dlcred.get('user'), 'dl-user')
        eq_(dlcred.get('password'), 'dl-pwd')


@with_tempfile
def test_credential_cycle(path=None):

    # Test that we break a possible cycle when DataLad is configured to query
    # git-credential and Git is configured to query DataLad.
    # This may happen in a not-so-obvious fashion, if git-credential-datalad
    # was configured generally rather than for a specific URL, while there's a
    # datalad provider config pointing to Git for a particular URL.

    ds = Dataset(path).create()

    # tell git to use git-credential-datalad
    ds.config.add('credential.helper', 'datalad', scope='local')
    ds.config.add('datalad.credentials.githelper.noninteractive', 'true',
                  scope='global')

    provider_dir = ds.pathobj / '.datalad' / 'providers'
    provider_dir.mkdir(parents=True, exist_ok=True)
    provider_cfg = provider_dir / 'test_cycle.cfg'
    provider_cfg.write_text(r"""
[provider:test_cycle]
    url_re = http.*://.*data\.example\.com
    authentication_type = http_basic_auth
    credential = test_cycle_cred
[credential:test_cycle_cred]
    type = git
""")
    ds.save(message="Add provider config")

    gitcred = GitCredentialInterface(url="https://some.data.exampe.com",
                                     repo=ds)

    # There's nothing set up yet, helper should return empty.
    # Importantly, it shouldn't end up in an endless recursion, but just
    # return w/o something filled in.
    gitcred.fill()
    eq_(gitcred['username'], '')
    eq_(gitcred['password'], '')
