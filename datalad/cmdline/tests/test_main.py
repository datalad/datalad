# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for cmdline.main"""

from ..main import main
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.tests.utils import swallow_outputs


def check_incorrect_option(opts, string_to_check):
    with swallow_outputs() as cmo:
        assert_raises(SystemExit, main, ("datalad",) + opts)
        out = cmo.out + cmo.err
    assert_in("error: invalid", out)
    assert_in("usage: ", out)


def test_incorrect_options():
    # apparently a bit different if following a good one so let's do both
    err_invalid = "error: invalid"
    yield check_incorrect_option, ('--buga',), err_invalid
    yield check_incorrect_option, ('--dbg', '--buga'), err_invalid

    err_insufficient = "specify"
    yield check_incorrect_option, ('--dbg',), err_insufficient
    yield check_incorrect_option, tuple(), err_insufficient



