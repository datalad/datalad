# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for data providers"""

from ..providers import Provider
from ..providers import Providers
from ..providers import assure_list_from_str, assure_dict_from_str
from ...tests.utils import eq_
from ...tests.utils import assert_in
from ...tests.utils import assert_equal


def test_Providers_OnStockConfiguration():
    providers = Providers.from_config_files()
    eq_(sorted([p.name for p in providers]), ['crcns', 'crcns-nersc', 'hcp-s3', 'hcp-web', 'hcp-xnat', 'openfmri'])

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


def test_assure_list_from_str():
    assert_equal(assure_list_from_str(''), None)
    assert_equal(assure_list_from_str([]), None)
    assert_equal(assure_list_from_str('somestring'), ['somestring'])
    assert_equal(assure_list_from_str('some\nmultiline\nstring'), ['some', 'multiline', 'string'])
    assert_equal(assure_list_from_str(['something']), ['something'])
    assert_equal(assure_list_from_str(['a', 'listof', 'stuff']), ['a', 'listof', 'stuff'])


def test_assure_dict_from_str():
    assert_equal(assure_dict_from_str(''), None)
    assert_equal(assure_dict_from_str({}), None)
    assert_equal(assure_dict_from_str(
            '__ac_name={user}\n__ac_password={password}\nsubmit=Log in\ncookies_enabled='), dict(
             __ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in'))
    assert_equal(assure_dict_from_str(
        dict(__ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in')), dict(
             __ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in'))
