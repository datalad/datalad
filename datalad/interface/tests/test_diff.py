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

from datalad.tests.utils import known_failure_direct_mode


from os.path import join as opj
from datalad.utils import chpwd

from datalad.cmd import GitRunner

from datalad.distribution.dataset import Dataset
from datalad.api import diff
from datalad.interface.diff import _parse_git_diff
from datalad.consts import PRE_INIT_COMMIT_SHA
from datalad.tests.utils import known_failure_windows
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import create_tree
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count


@known_failure_windows
def test_magic_number():
    # we hard code the magic SHA1 that represents the state of a Git repo
    # prior to the first commit -- used to diff from scratch to a specific
    # commit
    # given the level of dark magic, we better test whether this stays
    # constant across Git versions (it should!)
    out, err = GitRunner().run('git hash-object -t tree /dev/null')
    eq_(out.strip(), PRE_INIT_COMMIT_SHA)


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
        ds.diff(path='deep'), 1,
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


@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_diff_recursive(path):
    ds = Dataset(path).create()
    sub = ds.create('sub')
    # look at the last change, and confirm a dataset was added
    res = ds.diff(revision='HEAD~1..HEAD')
    assert_result_count(res, 1, action='diff', state='added', path=sub.path, type='dataset')
    # now recursive
    res = ds.diff(recursive=True, revision='HEAD~1..HEAD')
    # we also get the entire diff of the subdataset from scratch
    assert_status('ok', res)
    ok_(len(res) > 3)
    # one specific test
    assert_result_count(res, 1, action='diff', state='added', path=opj(sub.path, '.datalad', 'config'))

    # now we add a file to just the parent
    create_tree(ds.path, {'onefile': 'tobeadded', 'sub': {'twofile': 'tobeadded'}})
    res = ds.diff(recursive=True, report_untracked='all')
    assert_result_count(res, 3)
    assert_result_count(res, 1, action='diff', state='untracked', path=opj(ds.path, 'onefile'), type='file')
    assert_result_count(res, 1, action='diff', state='modified', path=sub.path, type='dataset')
    assert_result_count(res, 1, action='diff', state='untracked', path=opj(sub.path, 'twofile'), type='file')
    # save sub
    sub.add('.')
    # save sub in parent
    ds.save()
    # save addition in parent
    ds.add('.')
    ok_clean_git(ds.path)
    # look at the last change, only one file was added
    res = ds.diff(revision='HEAD~1..HEAD')
    assert_result_count(res, 1)
    assert_result_count(res, 1, action='diff', state='added', path=opj(ds.path, 'onefile'), type='file')

    # now the exact same thing with recursion, must not be different from the call
    # above
    res = ds.diff(recursive=True, revision='HEAD~1..HEAD')
    assert_result_count(res, 1)
    # last change in parent
    assert_result_count(res, 1, action='diff', state='added', path=opj(ds.path, 'onefile'), type='file')

    # one further back brings in the modified subdataset, and the added file within it
    res = ds.diff(recursive=True, revision='HEAD~2..HEAD')
    assert_result_count(res, 3)
    assert_result_count(res, 1, action='diff', state='added', path=opj(ds.path, 'onefile'), type='file')
    assert_result_count(res, 1, action='diff', state='added', path=opj(sub.path, 'twofile'), type='file')
    assert_result_count(res, 1, action='diff', state='modified', path=sub.path, type='dataset')


@with_tree(tree={
    'sub_clean': {},
    'sub_modified': {'modified': 'original'},
    'sub_dirty': {'untracked': 'dirt'},
    'clean': 'clean_content',
    'modified': 'original_content',
    'untracked': 'dirt',
})
@known_failure_direct_mode  #FIXME
def test_diff_helper(path):
    # make test dataset components of interesting states
    ds = Dataset.create(path, force=True)
    # detached dataset, not a submodule
    nosub = Dataset.create(opj(path, 'nosub'))
    # unmodified, proper submodule
    sub_clean = ds.create('sub_clean', force=True)
    # proper submodule, but commited modifications not commited in parent
    sub_modified = ds.create('sub_modified', force=True)
    sub_modified.add('modified')
    # proper submodule with untracked changes
    sub_dirty = ds.create('sub_dirty', force=True)
    ds.add(['clean', 'modified'])
    ds.unlock('modified')
    with open(opj(ds.path, 'modified'), 'w') as f:
        f.write('modified_content')
    file_mod = opj(ds.path, 'modified')
    # standard `git diff` no special args, reports modified, but not untracked
    res = list(_parse_git_diff(ds.path))
    assert_result_count(res, 3)
    assert_result_count(res, 1, path=file_mod)
    assert_result_count(res, 1, path=sub_modified.path)
    assert_result_count(res, 1, path=sub_dirty.path)
