# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for cmdline.helpers"""

__docformat__ = 'restructuredtext'

from datalad.tests.utils_pytest import assert_equal

from ..helpers import _fix_datalad_ri


def test_fix_datalad_ri():
    assert_equal(_fix_datalad_ri('/'), '/')
    assert_equal(_fix_datalad_ri('/a/b'), '/a/b')
    assert_equal(_fix_datalad_ri('//'), '///')
    assert_equal(_fix_datalad_ri('///'), '///')
    assert_equal(_fix_datalad_ri('//a'), '///a')
    assert_equal(_fix_datalad_ri('///a'), '///a')
    assert_equal(_fix_datalad_ri('//a/b'), '///a/b')
    assert_equal(_fix_datalad_ri('///a/b'), '///a/b')
