# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad save

"""

__docformat__ = 'restructuredtext'

import os
from os.path import join as opj
from datalad.utils import chpwd

from datalad.interface.results import is_ok_dataset
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import DeprecatedError
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.tests.utils import ok_
from datalad.api import diff
from datalad.tests.utils import assert_raises
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_equal
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_result_values_equal


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_diff(path, norepo):
    ds = Dataset(path).create()
    ok_clean_git(ds.path)
    # reports stupid revision input
    assert_result_count(
        ds.diff(revision='WTF', on_failure='ignore'),
        1,
        status='impossible',
        message="fatal: bad revision 'WTF'")
    assert_result_count(ds.diff(), 0)
    # no diff
    assert_result_count(ds.diff(), 0)
    assert_result_count(ds.diff(revision='HEAD'), 0)
    # bogus path makes no difference
    assert_result_count(ds.diff(path='THIS', revision='HEAD'), 0)
    # comparing to a previous state we should get a diff in most cases
    # for this test, let's not care what exactly it is -- will do later
    assert len(ds.diff(revision='HEAD~1')) > 0
    # let's introduce a known change
    create_tree(ds.path, {'new': 'empty'})
    ds.add('.', to_git=True)
    ok_clean_git(ds.path)
    res = ds.diff(revision='HEAD~1')
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, action='diff', path=opj(ds.path, 'new'), state='added')
    # we can also find the diff without going through the dataset explicitly
    with chpwd(ds.path):
        assert_result_count(
            diff(revision='HEAD~1'), 1,
            action='diff', path=opj(ds.path, 'new'), state='added')
    # no diff against HEAD
    assert_result_count(ds.diff(), 0)
    # modify known file
    create_tree(ds.path, {'new': 'notempty'})
    for diffy in (None, 'HEAD'):
        res = ds.diff(revision=diffy)
        assert_result_count(res, 1)
        assert_result_count(
            res, 1, action='diff', path=opj(ds.path, 'new'), state='modified')
    # but if we give another path, it doesn't show up
    assert_result_count(ds.diff('otherpath'), 0)
    # giving the right path must work though
    assert_result_count(
        ds.diff('new'), 1,
        action='diff', path=opj(ds.path, 'new'), state='modified')
    # stage changes
    ds.add('.', to_git=True, save=False)
    # no diff, because we staged the modification
    assert_result_count(ds.diff(), 0)
    # but we can get at it
    assert_result_count(
        ds.diff(staged=True), 1,
        action='diff', path=opj(ds.path, 'new'), state='modified')
    # OR
    assert_result_count(
        ds.diff(revision='HEAD'), 1,
        action='diff', path=opj(ds.path, 'new'), state='modified')
    ds.save()
    ok_clean_git(ds.path)
