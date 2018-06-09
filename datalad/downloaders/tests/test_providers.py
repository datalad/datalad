# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for data providers"""

from mock import patch
from tempfile import mkdtemp

from ..providers import Provider
from ..providers import Providers
from ..providers import HTTPDownloader
from ...utils import chpwd
from ...tests.utils import eq_
from ...tests.utils import assert_in
from ...tests.utils import assert_greater
from ...tests.utils import assert_equal
from ...tests.utils import assert_raises
from ...tests.utils import with_tree

from ...support.external_versions import external_versions
from ...interface.common_cfg import dirs


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
    # If uknown type -- raises ValueError
    assert_raises(ValueError, Providers._process_credential, 'cred', {'type': '_unknown_'})


def test_get_downloader_class():
    url = 'http://example.com'

    with patch.object(external_versions, '_versions', {'requests': 1}):
        assert Provider._get_downloader_class(url) is HTTPDownloader

    with patch.object(external_versions, '_versions', {'requests': None}):
        with assert_raises(RuntimeError) as cmr:
            Provider._get_downloader_class(url)
        assert_in("you need 'requests'", str(cmr.exception))

@with_tree(tree={
  'providers': {'atest.cfg':"""\
[provider:syscrcns]
url_re = https?://crcns\.org/.*
authentication_type = none
"""}})
@with_tree(tree={
  'providers': {'atestwithothername.cfg':"""\
[provider:usercrcns]
url_re = https?://crcns\.org/.*
authentication_type = none
"""}})
@with_tree(tree={
  '.datalad': {'providers': {'atest.cfg':"""\
[provider:dscrcns]
url_re = https?://crcns\.org/.*
authentication_type = none
"""}},
   '.git': { "HEAD" : ""}})
@patch.multiple("appdirs.AppDirs", site_config_dir=None, user_config_dir=None)
def test_Providers_from_config__files(sysdir, userdir, dsdir):
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
        with patch.multiple("appdirs.AppDirs", site_config_dir=sysdir, user_config_dir=None):
            providers = Providers.from_config_files(reload=True)
            provider = providers.get_provider('https://crcns.org/data....')
            assert_equal(provider.name, 'syscrcns')

        # Test that the user defaults take precedence over the system
        # defaults
        with patch.multiple("appdirs.AppDirs", site_config_dir=sysdir, user_config_dir=userdir):
            providers = Providers.from_config_files(reload=True)
            provider = providers.get_provider('https://crcns.org/data....')
            assert_equal(provider.name, 'usercrcns')
