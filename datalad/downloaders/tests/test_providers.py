# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for data providers"""

from ..providers import Providers
from ..providers import assure_list_from_str, assure_dict_from_str
from ...tests.utils import eq_
from ...tests.utils import assert_in
from ...tests.utils import assert_equal


def test_ProvidersInformation_OnStockConfiguration():
    pi = Providers.from_config_files()
    eq_(sorted([p.name for p in pi.providers]), ['crcns', 'crcns-nersc', 'hcp-s3', 'hcp-web', 'hcp-xnat', 'openfmri'])

    # every provider must have url_res
    for n, fields in pi.providers.items():
        assert_in('url_re', fields)

    # and then that we didn't screw it up -- cycle few times to verify that we do not
    # somehow remove existing providers while dealing with that "heaplike" list
    for i in range(3):
        provider = pi.get_provider('https://crcns.org/data....')
        assert_equal(provider['name'], 'crcns')

        provider = pi.get_provider('https://portal.nersc.gov/project/crcns/download/bogus')
        assert_equal(provider['name'], 'crcns-nersc')

    assert_equal(pi.needs_authentication('http://google.com'), None)
    assert_equal(pi.needs_authentication('http://crcns.org/'), True)
    assert_equal(pi.needs_authentication('http://openfmri.org/'), False)


def test_assure_list_from_str():
    assert_equal(assure_list_from_str(''), None)
    assert_equal( assure_list_from_str([]), None)
    assert_equal(assure_list_from_str('somestring'), ['somestring'])
    assert_equal(assure_list_from_str('some\nmultiline\nstring'), ['some', 'multiline', 'string'])
    assert_equal( assure_list_from_str(['something']), ['something'])
    assert_equal( assure_list_from_str(['a', 'listof', 'stuff']), ['a', 'listof', 'stuff'])


def test_assure_dict_from_str():
    assert_equal(assure_dict_from_str(''), None)
    assert_equal(assure_dict_from_str({}), None)
    assert_equal(assure_dict_from_str(
            '__ac_name={user}\n__ac_password={password}\nsubmit=Log in\ncookies_enabled=') == dict(
             __ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in'))
    assert_equal(assure_dict_from_str(
        dict(__ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in')) == dict(
             __ac_name='{user}', __ac_password='{password}', cookies_enabled='', submit='Log in'))
