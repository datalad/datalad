# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ..status import FileStatus
from ...tests.utils import assert_equal, assert_false
from nose.tools import assert_not_equal

def test_FileStatus_basic():
    assert_equal(FileStatus(size=0), FileStatus(size=0))
    assert_not_equal(FileStatus(size=0), FileStatus(size=1))
    # mtimes allow trimming if one is int
    assert_equal(FileStatus(mtime=0), FileStatus(mtime=0.9999))
    assert_equal(FileStatus(mtime=0), FileStatus(mtime=0.0001))
    assert_not_equal(FileStatus(mtime=0.2), FileStatus(mtime=0.1))
    assert_not_equal(FileStatus(mtime=0.2), FileStatus(mtime=None))
    assert_not_equal(FileStatus(mtime=1), FileStatus(mtime=None))
    # And with None should be False
    assert_not_equal(FileStatus(mtime=1), None)
    assert_not_equal(None, FileStatus(mtime=1))
    # adding more information would result in not-equal
    assert_not_equal(FileStatus(size=0), FileStatus(size=0, mtime=123))
    # empty ones can't be compared
    # TODO: actually not clear why that NotImplemented singleton is not returned
    assert_not_equal(FileStatus(), FileStatus())
    #assert_false(FileStatus() != FileStatus())
