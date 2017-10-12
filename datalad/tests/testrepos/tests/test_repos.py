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
from datalad.tests.utils import with_tempfile, assert_raises



#log("Processing definition of %s", self.__class__)


@with_tempfile
def test_TestRepo_instantiation(path):
    # we can't instantiate the base class due to missing definition:
    assert_raises(InvalidTestRepoDefinitionError, TestRepo_NEW, path)


@with_tempfile
def test_BasicGit_instantiation(path):
    tr = BasicGit(path)


@with_tempfile
def test_BasicMixed_instantiation(path):
    tr = BasicMixed(path)



