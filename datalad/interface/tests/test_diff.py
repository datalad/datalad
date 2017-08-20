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

from os.path import join as opj
from datalad.utils import chpwd

from datalad.distribution.dataset import Dataset
from datalad.api import diff
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_diff(path, norepo):
    with chpwd(norepo):
        assert_status('impossible', diff(on_failure='ignore'))
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

    # untracked stuff
    create_tree(ds.path, {'deep': {'down': 'untracked', 'down2': 'tobeadded'}})
    # a plain diff should report the untracked file
    # but not directly, because the parent dir is already unknown
    res = ds.diff()
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, state='untracked', type='directory', path=opj(ds.path, 'deep'))
    # report of individual files is also possible
    assert_result_count(
        ds.diff(report_untracked='all'), 2, state='untracked', type='file')
    # an unmatching path will hide this result
    assert_result_count(ds.diff(path='somewhere'), 0)
    # perfect match and anything underneath will do
    assert_result_count(
        ds.diff(path='deep'), 1, state='untracked', path=opj(ds.path, 'deep'),
        type='directory')
    assert_result_count(
        ds.diff(path=opj('deep', 'somewhere')), 1,
        state='untracked', path=opj(ds.path, 'deep'))
    # now we stage on of the two files in deep
    ds.add(opj('deep', 'down2'), to_git=True, save=False)
    # without any reference it will ignore the staged stuff and report the remaining
    # untracked file
    assert_result_count(
        ds.diff(), 1, state='untracked', path=opj(ds.path, 'deep', 'down'),
        type='file')
    res = ds.diff(staged=True)
    assert_result_count(
        res, 1, state='untracked', path=opj(ds.path, 'deep', 'down'), type='file')
    assert_result_count(
        res, 1, state='added', path=opj(ds.path, 'deep', 'down2'), type='file')
