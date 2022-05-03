# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ...tests.utils_pytest import assert_equal
from ..cache import DictCache


def test_DictCache():
    d = DictCache(size_limit=2)

    assert_equal(d, {})
    d['a'] = 2
    d['b'] = 1
    assert_equal(d, {'a': 2, 'b': 1})

    d['c'] = 2
    assert_equal(d, {'c': 2, 'b': 1})
