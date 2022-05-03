# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for vcr adapter"""

from ...tests.utils_pytest import (
    SkipTest,
    eq_,
)
from ..vcr_ import use_cassette


def test_use_cassette_if_no_vcr():
    # just test that our do nothing decorator does the right thing if vcr is not present
    skip = False
    try:
        import vcr
        skip = True
    except ImportError:
        pass
    except:
        # if anything else goes wrong with importing vcr, we still should be able to
        # run use_cassette
        pass
    if skip:
        raise SkipTest("vcr is present, can't test behavior with vcr presence ATM")

    @use_cassette("some_path")
    def checker(x):
        return x + 1

    eq_(checker(1), 2)
