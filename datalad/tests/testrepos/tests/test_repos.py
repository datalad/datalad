# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for testrepos
"""

from datalad.tests.testrepos.repos import *

from datalad.tests.utils import with_tempfile


@with_tempfile
def test_BasicGit_instantiation(path):
    tr = BasicGit(path)
    tr.assert_intact()


@with_tempfile
def test_BasicMixed_instantiation(path):
    tr = BasicMixed(path)
    tr.assert_intact()



