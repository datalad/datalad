# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for data providers"""

import logging
import os.path as op
from unittest.mock import patch

from ...support.external_versions import external_versions
from ...tests.utils_pytest import (
    assert_equal,
    assert_false,
    assert_greater,
    assert_in,
    assert_raises,
    ok_exists,
    swallow_logs,
    with_tempfile,
    with_testsui,
    with_tree,
)
from ...utils import (
    chpwd,
    create_tree,
)
from ..providers import (
    HTTPDownloader,
    Provider,
    Providers,
)


def test_Providers_OnStockConfiguration():
    providers = Providers.from_config_files()
    provider_names = {p.name for p in providers}
    assert_in('datalad-test-s3', provider_names)
    assert_in('crcns', provider_names)
    assert_greater(len(provider_names), 5)
    # too rigid
    #eq_(provider_names, {'crcns', 'crcns-nersc', 'hcp-http', 'hcp-s3', 'hcp-web', 'hcp-xnat', 'openfmri'})

    # every provider must have url_res
    for provider in providers:
        assert(provider.url_res)

    # and then that we didn't screw it up -- cycle few times to verify that we do not
    # somehow remove existing providers while dealing with that "heaplike" list
    for i in range(3):
        provider = providers.get_provider('https://crcns.org/data....')
        assert_equal(provider.name, 'crcns')

        provider = providers.get_provider('https://portal.nersc.gov/project/crcns/download/bogus')
        assert_equal(provider.name, 'crcns-nersc')

    assert_equal(providers.needs_authentication('http://google.com'), None)
    assert_equal(providers.needs_authentication('http://crcns.org/'), True)
    assert_equal(providers.needs_authentication('http://openfmri.org/'), False)

    providers_repr = repr(providers)
    # should list all the providers atm
    assert_equal(providers_repr.count('Provider('), len(providers))

    # Should be a lazy evaluator unless reload is specified
    assert(providers is Providers.from_config_files())
    assert(providers is not Providers.from_config_files(reload=True))


def test_Providers_default_ones():
    providers = Providers()  # empty one

    # should return default one
    http_provider = providers.get_provider("http://example.com")
    # which must be the same if asked for another one of http
    http_provider2 = providers.get_provider("http://datalad.org")
    assert(http_provider is http_provider2)

    # but for another protocol, we would generate a new one
    crap_provider = providers.get_provider("crap://crap.crap")
    assert(crap_provider is not http_provider)
    assert(isinstance(crap_provider, Provider))


def test_Providers_process_credential():
    # If unknown type -- raises ValueError
    assert_raises(ValueError, Providers._process_credential, 'cred', {'type': '_unknown_'})


def test_get_downloader_class():
    url = 'http://example.com'

    with patch.object(external_versions, '_versions', {'requests': 1}):
        assert Provider._get_downloader_class(url) is HTTPDownloader

    with patch.object(external_versions, '_versions', {'requests': None}):
        with assert_raises(RuntimeError) as cmr:
            Provider._get_downloader_class(url)
        assert_in("you need 'requests'", str(cmr.value))


@with_tree(tree={
  'providers': {'atest.cfg':"""\
[provider:syscrcns]
url_re = https?://crcns\\.org/.*
authentication_type = none
"""}})
@with_tree(tree={
  'providers': {'atestwithothername.cfg':"""\
[provider:usercrcns]
url_re = https?://crcns\\.org/.*
authentication_type = none
"""}})
@with_tree(tree={
  '.datalad': {'providers': {'atest.cfg':"""\
[provider:dscrcns]
url_re = https?://crcns\\.org/.*
authentication_type = none
"""}},
   '.git': { "HEAD" : ""}})
@patch.multiple("platformdirs.AppDirs", site_config_dir=None, user_config_dir=None)
def test_Providers_from_config__files(sysdir=None, userdir=None, dsdir=None):
    """Test configuration file precedence

    Ensure that provider precedence works in the correct order:

        datalad defaults < dataset defaults < system defaults < user defaults
    """

    # Test the default, this is an arbitrary provider used from another
    # test
    providers = Providers.from_config_files(reload=True)
    provider = providers.get_provider('https://crcns.org/data....')
    assert_equal(provider.name, 'crcns')

    # Test that the dataset provider overrides the datalad
    # default
    with chpwd(dsdir):
        providers = Providers.from_config_files(reload=True)
        provider = providers.get_provider('https://crcns.org/data....')
        assert_equal(provider.name, 'dscrcns')

        # Test that the system defaults take precedence over the dataset
        # defaults (we're still within the dsdir)
        with patch.multiple("platformdirs.AppDirs", site_config_dir=sysdir, user_config_dir=None):
            providers = Providers.from_config_files(reload=True)
            provider = providers.get_provider('https://crcns.org/data....')
            assert_equal(provider.name, 'syscrcns')

        # Test that the user defaults take precedence over the system
        # defaults
        with patch.multiple("platformdirs.AppDirs", site_config_dir=sysdir, user_config_dir=userdir):
            providers = Providers.from_config_files(reload=True)
            provider = providers.get_provider('https://crcns.org/data....')
            assert_equal(provider.name, 'usercrcns')


@with_tempfile(mkdir=True)
def test_providers_enter_new(path=None):
    with patch.multiple("platformdirs.AppDirs", site_config_dir=None,
                        user_config_dir=path):
        providers_dir = op.join(path, "providers")
        providers = Providers.from_config_files(reload=True)

        url = "blah://thing"
        url_re = r"blah:\/\/.*"
        auth_type = "http_auth"
        creds = "user_password"

        @with_testsui(responses=["foo", url_re, auth_type,
                                 creds, "no"])
        def no_save():
            providers.enter_new(url)
        no_save()
        assert_false(op.exists(op.join(providers_dir, "foo.cfg")))

        @with_testsui(responses=["foo", url_re, auth_type,
                                 creds, "yes"])
        def save():
            providers.enter_new(url)
        save()
        ok_exists(op.join(providers_dir, "foo.cfg"))

        create_tree(path=providers_dir, tree={"exists.cfg": ""})
        @with_testsui(responses=["exists", "foobert", url_re,
                                 auth_type, creds, "yes"])
        def already_exists():
            providers.enter_new(url)
        already_exists()
        ok_exists(op.join(providers_dir, "foobert.cfg"))

        @with_testsui(responses=["crawdad", "yes"])
        def known_provider():
            providers.enter_new(url)
        known_provider()

        @with_testsui(responses=["foo2", url_re, auth_type,
                                 creds, "yes"])
        def auth_types():
            providers.enter_new(url, auth_types=["http_basic_auth"])
        auth_types()
        ok_exists(op.join(providers_dir, "foo2.cfg"))

        @with_testsui(responses=["foo3", "doesn't match", url_re, auth_type,
                                 creds, "yes"])
        def nonmatching_url():
            providers.enter_new(url, auth_types=["http_basic_auth"])
        nonmatching_url()
        ok_exists(op.join(providers_dir, "foo3.cfg"))


@with_tree(tree={'providers.cfg': """\
[provider:foo0]
url_re = https?://foo\\.org/.*
authentication_type = none

[provider:foo1]
url_re = https?://foo\\.org/.*
authentication_type = none
"""})
def test_providers_multiple_matches(path=None):
    providers = Providers.from_config_files(
        files=[op.join(path, "providers.cfg")], reload=True)
    all_provs = providers.get_provider('https://foo.org/data',
                                       return_all=True)
    assert_equal({p.name for p in all_provs}, {'foo0', 'foo1'})

    # When selecting a single one, the later one is given priority.
    the_chosen_one = providers.get_provider('https://foo.org/data')
    assert_equal(the_chosen_one.name, "foo1")

@with_tree(tree={'providers.cfg': """\
[provider:foo0]
url_re = https?://[foo-a\\.org]/.*
authentication_type = none

[provider:foo1]
url_re = https?://foo\\.org/.*
authentication_type = none
"""})
def test_providers_badre(path=None):
    """Test that a config with a bad regular expression doesn't crash

    Ensure that when a provider config has a bad url_re, there is no
    exception thrown and a valid warning is provided.
    """

    providers = Providers.from_config_files(
        files=[op.join(path, "providers.cfg")], reload=True)

    # Regexes are evaluated when get_provider is called,
    # so we need to get a random provider, even though it
    # doesn't match.
    with swallow_logs(logging.WARNING) as msg:
        the_chosen_one = providers.get_provider('https://foo.org/data')
        assert_in("Invalid regex", msg.out)
