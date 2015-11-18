# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for data providers"""

from ..providers import ProvidersInformation
from ...tests.utils import eq_
from ...tests.utils import assert_in

def test_ProvidersInformationDummyOne():
    pi = ProvidersInformation()
    eq_(sorted(pi.providers.keys()), ['crcns', 'crcns-nersc'])
    for n, fields in pi.providers.items():
        assert_in('credentials', fields)
        assert_in('url_re', fields)
