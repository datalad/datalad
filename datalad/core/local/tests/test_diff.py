# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test dataset diff

"""

__docformat__ = 'restructuredtext'

import os
import os.path as op
from unittest.mock import patch

import datalad.utils as ut
from datalad.api import (
    create,
    diff,
    save,
)
from datalad.cmd import (
    GitWitlessRunner,
    StdOutCapture,
)
from datalad.consts import PRE_INIT_COMMIT_SHA
from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import NoDatasetFound
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    OBSCURE_FILENAME,
    SkipTest,
    assert_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    chpwd,
    create_tree,
    eq_,
    get_deeply_nested_structure,
    has_symlink_capability,
    known_failure_githubci_win,
    neq_,
    ok_,
    with_tempfile,
)
from datalad.utils import Path


def test_magic_number():
    # we hard code the magic SHA1 that represents the state of a Git repo
    # prior to the first commit -- used to diff from scratch to a specific
    # commit
    # given the level of dark magic, we better test whether this stays
    # constant across Git versions (it should!)
    out = GitWitlessRunner().run(
        'cd ./ | git hash-object --stdin -t tree',
        protocol=StdOutCapture)
    eq_(out['stdout'].strip(), PRE_INIT_COMMIT_SHA)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_repo_diff(path=None, norepo=None):
    ds = Dataset(path).create()
    assert_repo_status(ds.path)
    assert_raises(ValueError, ds.repo.diff, fr='WTF', to='MIKE')

    if ds.repo.is_managed_branch():
        fr_base = DEFAULT_BRANCH
        to = DEFAULT_BRANCH
    else:
        fr_base = "HEAD"
        to = None

    # no diff
    eq_(ds.repo.diff(fr_base, to), {})
    # bogus path makes no difference
    eq_(ds.repo.diff(fr_base, to, paths=['THIS']), {})
    # let's introduce a known change
    create_tree(ds.path, {'new': 'empty'})
    ds.save(to_git=True)
    assert_repo_status(ds.path)
    eq_(ds.repo.diff(fr=fr_base + '~1', to=fr_base),
        {ut.Path(ds.repo.pathobj / 'new'): {
            'state': 'added',
            'type': 'file',
            'bytesize': 5,
            'gitshasum': '7b4d68d70fcae134d5348f5e118f5e9c9d3f05f6'}})
    # modify known file
    create_tree(ds.path, {'new': 'notempty'})
    eq_(ds.repo.diff(fr='HEAD', to=None),
        {ut.Path(ds.repo.pathobj / 'new'): {
            'state': 'modified',
            'type': 'file',
            # the beast is modified, but no change in shasum -> not staged
            'gitshasum': '7b4d68d70fcae134d5348f5e118f5e9c9d3f05f6',
            'prev_gitshasum': '7b4d68d70fcae134d5348f5e118f5e9c9d3f05f6'}})
    # per path query gives the same result
    eq_(ds.repo.diff(fr=fr_base, to=to),
        ds.repo.diff(fr=fr_base, to=to, paths=['new']))
    # also given a directory as a constraint does the same
    eq_(ds.repo.diff(fr=fr_base, to=to),
        ds.repo.diff(fr=fr_base, to=to, paths=['.']))
    # but if we give another path, it doesn't show up
    eq_(ds.repo.diff(fr=fr_base, to=to, paths=['other']), {})

    # make clean
    ds.save()
    assert_repo_status(ds.path)

    # untracked stuff
    create_tree(ds.path, {'deep': {'down': 'untracked', 'down2': 'tobeadded'}})
    # default is to report all files
    eq_(ds.repo.diff(fr='HEAD', to=None),
        {
            ut.Path(ds.repo.pathobj / 'deep' / 'down'): {
                'state': 'untracked',
                'type': 'file'},
            ut.Path(ds.repo.pathobj / 'deep' / 'down2'): {
                'state': 'untracked',
                'type': 'file'}})
    # but can be made more compact
    eq_(ds.repo.diff(fr='HEAD', to=None, untracked='normal'),
        {
            ut.Path(ds.repo.pathobj / 'deep'): {
                'state': 'untracked',
                'type': 'directory'}})

    # again a unmatching path constrained will give an empty report
    eq_(ds.repo.diff(fr='HEAD', to=None, paths=['other']), {})
    # perfect match and anything underneath will do
    eq_(ds.repo.diff(fr='HEAD', to=None, paths=['deep']),
        {
            ut.Path(ds.repo.pathobj / 'deep' / 'down'): {
                'state': 'untracked',
                'type': 'file'},
            ut.Path(ds.repo.pathobj / 'deep' / 'down2'): {
                'state': 'untracked',
                'type': 'file'}})


def _dirty_results(res):
    return [r for r in res if r.get('state', None) != 'clean']


# this is an extended variant of `test_repo_diff()` above
# that focuses on the high-level command API
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_diff(path=None, norepo=None):
    with chpwd(norepo):
        assert_raises(NoDatasetFound, diff)
    ds = Dataset(path).create()
    assert_repo_status(ds.path)
    # reports stupid revision input
    assert_result_count(
        ds.diff(fr='WTF', on_failure='ignore', result_renderer='disabled'),
        1,
        status='impossible',
        message="Git reference 'WTF' invalid")
    # no diff
    assert_result_count(_dirty_results(ds.diff(result_renderer='disabled')), 0)
    assert_result_count(
        _dirty_results(ds.diff(fr='HEAD', result_renderer='disabled')), 0)
    # bogus path makes no difference
    assert_result_count(
        _dirty_results(ds.diff(path='THIS', fr='HEAD', result_renderer='disabled')),
        0)
    # let's introduce a known change
    create_tree(ds.path, {'new': 'empty'})
    ds.save(to_git=True)
    assert_repo_status(ds.path)

    if ds.repo.is_managed_branch():
        fr_base = DEFAULT_BRANCH
        to = DEFAULT_BRANCH
    else:
        fr_base = "HEAD"
        to = None

    res = _dirty_results(ds.diff(fr=fr_base + '~1', to=to, result_renderer='disabled'))
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, action='diff', path=op.join(ds.path, 'new'), state='added')
    # we can also find the diff without going through the dataset explicitly
    with chpwd(ds.path):
        assert_result_count(
            _dirty_results(diff(fr=fr_base + '~1', to=to,
                                result_renderer='disabled')),
            1,
            action='diff', path=op.join(ds.path, 'new'), state='added')
    # no diff against HEAD
    assert_result_count(_dirty_results(ds.diff(result_renderer='disabled')), 0)
    # modify known file
    create_tree(ds.path, {'new': 'notempty'})
    res = _dirty_results(ds.diff(result_renderer='disabled'))
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, action='diff', path=op.join(ds.path, 'new'),
        state='modified')
    # but if we give another path, it doesn't show up
    assert_result_count(ds.diff(path='otherpath', result_renderer='disabled'), 0)
    # giving the right path must work though
    assert_result_count(
        ds.diff(path='new', result_renderer='disabled'), 1,
        action='diff', path=op.join(ds.path, 'new'), state='modified')
    # stage changes
    ds.repo.add('.', git=True)
    # no change in diff, staged is not committed
    assert_result_count(_dirty_results(ds.diff(result_renderer='disabled')), 1)
    ds.save()
    assert_repo_status(ds.path)
    assert_result_count(_dirty_results(ds.diff(result_renderer='disabled')), 0)

    # untracked stuff
    create_tree(ds.path, {'deep': {'down': 'untracked', 'down2': 'tobeadded'}})
    # a plain diff should report the untracked file
    # but not directly, because the parent dir is already unknown
    res = _dirty_results(ds.diff(result_renderer='disabled'))
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, state='untracked', type='directory',
        path=op.join(ds.path, 'deep'))
    # report of individual files is also possible
    assert_result_count(
        ds.diff(untracked='all', result_renderer='disabled'), 2, state='untracked',
        type='file')
    # an unmatching path will hide this result
    assert_result_count(ds.diff(path='somewhere', result_renderer='disabled'), 0)
    # perfect match and anything underneath will do
    assert_result_count(
        ds.diff(path='deep', result_renderer='disabled'), 1, state='untracked',
        path=op.join(ds.path, 'deep'),
        type='directory')
    assert_result_count(
        ds.diff(path='deep', result_renderer='disabled'), 1,
        state='untracked', path=op.join(ds.path, 'deep'))
    ds.repo.add(op.join('deep', 'down2'), git=True)
    # now the remaining file is the only untracked one
    assert_result_count(
        ds.diff(result_renderer='disabled'), 1, state='untracked',
        path=op.join(ds.path, 'deep', 'down'),
        type='file')


@with_tempfile(mkdir=True)
def test_diff_recursive(path=None):
    ds = Dataset(path).create()
    sub = ds.create('sub')
    # look at the last change, and confirm a dataset was added
    res = ds.diff(fr=DEFAULT_BRANCH + '~1', to=DEFAULT_BRANCH,
                  result_renderer='disabled')
    assert_result_count(
        res, 1, action='diff', state='added', path=sub.path, type='dataset')
    # now recursive
    res = ds.diff(recursive=True, fr=DEFAULT_BRANCH + '~1', to=DEFAULT_BRANCH,
                  result_renderer='disabled')
    # we also get the entire diff of the subdataset from scratch
    assert_status('ok', res)
    ok_(len(res) > 3)
    # one specific test
    assert_result_count(
        res, 1, action='diff', state='added',
        path=op.join(sub.path, '.datalad', 'config'))

    # now we add a file to just the parent
    create_tree(
        ds.path,
        {'onefile': 'tobeadded', 'sub': {'twofile': 'tobeadded'}})
    res = ds.diff(recursive=True, untracked='all', result_renderer='disabled')
    assert_result_count(_dirty_results(res), 3)
    assert_result_count(
        res, 1,
        action='diff', state='untracked', path=op.join(ds.path, 'onefile'),
        type='file')
    assert_result_count(
        res, 1,
        action='diff', state='modified', path=sub.path, type='dataset')
    assert_result_count(
        res, 1,
        action='diff', state='untracked', path=op.join(sub.path, 'twofile'),
        type='file')
    # intentional save in two steps to make check below easier
    ds.save('sub', recursive=True)
    ds.save()
    assert_repo_status(ds.path)

    head_ref = DEFAULT_BRANCH if ds.repo.is_managed_branch() else 'HEAD'

    # look at the last change, only one file was added
    res = ds.diff(fr=head_ref + '~1', to=head_ref, annex='basic',
                  result_renderer='disabled')
    assert_result_count(_dirty_results(res), 1)
    assert_result_count(
        res, 1,
        action='diff', state='added', path=op.join(ds.path, 'onefile'),
        type='file')

    # now the exact same thing with recursion, must not be different from the
    # call above
    res = ds.diff(recursive=True, fr=head_ref + '~1', to=head_ref,
                  annex='basic', result_renderer='disabled')
    assert_result_count(_dirty_results(res), 1)
    # last change in parent
    assert_result_count(
        res, 1, action='diff', state='added', path=op.join(ds.path, 'onefile'),
        type='file')

    if ds.repo.is_managed_branch():
        raise SkipTest(
            "Test assumption broken: https://github.com/datalad/datalad/issues/3818")
    # one further back brings in the modified subdataset, and the added file
    # within it
    res = ds.diff(recursive=True, fr=head_ref + '~2', to=head_ref,
                  annex='basic', result_renderer='disabled')
    assert_result_count(_dirty_results(res), 3)
    assert_result_count(
        res, 1,
        action='diff', state='added', path=op.join(ds.path, 'onefile'),
        type='file')
    assert_result_count(
        res, 1,
        action='diff', state='added', path=op.join(sub.path, 'twofile'),
        type='file')
    assert_result_count(
        res, 1,
        action='diff', state='modified', path=sub.path, type='dataset')


@with_tempfile(mkdir=True)
@with_tempfile()
def test_path_diff(_path=None, linkpath=None):
    # do the setup on the real path, not the symlink, to have its
    # bugs not affect this test of status()
    ds = get_deeply_nested_structure(str(_path))
    if has_symlink_capability():
        # make it more complicated by default
        ut.Path(linkpath).symlink_to(_path, target_is_directory=True)
        path = linkpath
    else:
        path = _path

    ds = Dataset(path)
    if has_symlink_capability():
        assert ds.pathobj != ds.repo.pathobj

    plain_recursive = ds.diff(recursive=True, annex='all', result_renderer='disabled')
    # check integrity of individual reports with a focus on how symlinks
    # are reported
    for res in plain_recursive:
        # anything that is an "intended" symlink should be reported
        # as such. In contrast, anything that is a symlink for mere
        # technical reasons (annex using it for something in some mode)
        # should be reported as the thing it is representing (i.e.
        # a file)
        if 'link2' in str(res['path']):
            assert res['type'] == 'symlink', res
        else:
            assert res['type'] != 'symlink', res
        # every item must report its parent dataset
        assert_in('parentds', res)

    # bunch of smoke tests
    # query of '.' is same as no path
    eq_(plain_recursive, ds.diff(path='.', recursive=True, annex='all',
                                 result_renderer='disabled'))
    # duplicate paths do not change things
    eq_(plain_recursive, ds.diff(path=['.', '.'], recursive=True, annex='all',
                                 result_renderer='disabled'))
    # neither do nested paths
    eq_(plain_recursive,
        ds.diff(path=['.', 'subds_modified'], recursive=True, annex='all',
                result_renderer='disabled'))
    # when invoked in a subdir of a dataset it still reports on the full thing
    # just like `git status`, as long as there are no paths specified
    with chpwd(op.join(path, 'directory_untracked')):
        plain_recursive = diff(recursive=True, annex='all',
                               result_renderer='disabled')
    # should be able to take absolute paths and yield the same
    # output
    eq_(plain_recursive, ds.diff(path=ds.path, recursive=True, annex='all',
                                 result_renderer='disabled'))

    # query for a deeply nested path from the top, should just work with a
    # variety of approaches
    rpath = op.join('subds_modified', 'subds_lvl1_modified',
                    u'{}_directory_untracked'.format(OBSCURE_FILENAME))
    apathobj = ds.pathobj / rpath
    apath = str(apathobj)
    for p in (rpath, apath, None):
        if p is None:
            # change into the realpath of the dataset and
            # query with an explicit path
            with chpwd(ds.path):
                res = ds.diff(
                    path=op.join('.', rpath),
                    recursive=True,
                    annex='all', result_renderer='disabled')
        else:
            res = ds.diff(
                path=p,
                recursive=True,
                annex='all', result_renderer='disabled')
        assert_result_count(
            res,
            1,
            state='untracked',
            type='directory',
            refds=ds.path,
            # path always comes out a full path inside the queried dataset
            path=apath,
        )

    assert_result_count(
        ds.diff(
            recursive=True, result_renderer='disabled'),
        1,
        path=apath)
    # limiting recursion will exclude this particular path
    assert_result_count(
        ds.diff(
            recursive=True,
            recursion_limit=1, result_renderer='disabled'),
        0,
        path=apath)
    # negative limit is unlimited limit
    eq_(
        ds.diff(recursive=True, recursion_limit=-1, result_renderer='disabled'),
        ds.diff(recursive=True, result_renderer='disabled')
    )


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_diff_nods(path=None, otherpath=None):
    ds = Dataset(path).create()
    assert_result_count(
        ds.diff(path=otherpath, on_failure='ignore', result_renderer='disabled'),
        1,
        status='error',
        message='path not underneath this dataset')
    otherds = Dataset(otherpath).create()
    assert_result_count(
        ds.diff(path=otherpath, on_failure='ignore', result_renderer='disabled'),
        1,
        path=otherds.path,
        status='error',
        message=(
            'dataset containing given paths is not underneath the '
            'reference dataset %s: %s', ds, otherds.path)
    )


@with_tempfile(mkdir=True)
def test_diff_rsync_syntax(path=None):
    # three nested datasets
    ds = Dataset(path).create()
    subds = ds.create('sub')
    subsubds = subds.create(Path('subdir', 'deep'))
    justtop = ds.diff(fr=PRE_INIT_COMMIT_SHA, path='sub', result_renderer='disabled')
    # we only get a single result, the subdataset in question
    assert_result_count(justtop, 1)
    assert_result_count(justtop, 1, type='dataset', path=subds.path)
    # now with "peak inside the dataset" syntax
    inside = ds.diff(fr=PRE_INIT_COMMIT_SHA, path='sub' + os.sep,
                     result_renderer='disabled')
    # we get both subdatasets, but nothing else inside the nested one
    assert_result_count(inside, 2, type='dataset')
    assert_result_count(inside, 1, type='dataset', path=subds.path)
    assert_result_count(inside, 1, type='dataset', path=subsubds.path)
    assert_result_count(inside, 0, type='file', parentds=subsubds.path)
    # if we point to the subdir in 'sub' the reporting wrt the subsubds
    # doesn't change. It is merely a path constraint within the queried
    # subds, but because the subsubds is still underneath it, nothing changes
    inside_subdir = ds.diff(
        fr=PRE_INIT_COMMIT_SHA, path=op.join('sub', 'subdir'),
        result_renderer='disabled')
    assert_result_count(inside_subdir, 2, type='dataset')
    assert_result_count(inside_subdir, 1, type='dataset', path=subds.path)
    assert_result_count(inside_subdir, 1, type='dataset', path=subsubds.path)
    assert_result_count(inside_subdir, 0, type='file', parentds=subsubds.path)
    # but the rest is different (e.g. all the stuff in .datalad is gone)
    neq_(inside, inside_subdir)
    # just for completeness, we get more when going full recursive
    rec = ds.diff(fr=PRE_INIT_COMMIT_SHA, recursive=True, path='sub' + os.sep,
                  result_renderer='disabled')
    assert(len(inside) < len(rec))


@with_tempfile(mkdir=True)
def test_diff_nonexistent_ref_unicode(path=None):
    ds = Dataset(path).create()
    assert_result_count(
        ds.diff(fr="HEAD", to=u"β", on_failure="ignore", result_renderer='disabled'),
        1,
        path=ds.path,
        status="impossible")


# https://github.com/datalad/datalad/issues/3997
@with_tempfile(mkdir=True)
def test_no_worktree_impact_false_deletions(path=None):
    ds = Dataset(path).create()
    # create a branch that has no new content
    ds.repo.call_git(['checkout', '-b', 'test'])
    # place two successive commits with file additions into the default branch
    ds.repo.call_git(['checkout', DEFAULT_BRANCH])
    (ds.pathobj / 'identical').write_text('should be')
    ds.save()
    (ds.pathobj / 'new').write_text('yes')
    ds.save()
    # now perform a diff for the last commit, there is one file that remained
    # identifical
    ds.repo.call_git(['checkout', 'test'])
    res = ds.diff(fr=DEFAULT_BRANCH + '~1', to=DEFAULT_BRANCH,
                  result_renderer='disabled')
    # under no circumstances can there be any reports on deleted files
    # because we never deleted anything
    assert_result_count(res, 0, state='deleted')
    # the identical file must be reported clean
    assert_result_count(
        res,
        1,
        state='clean',
        path=str(ds.pathobj / 'identical'),
    )


@with_tempfile(mkdir=True)
def test_diff_fr_none_one_get_content_annexinfo_call(path=None):
    from datalad.support.annexrepo import AnnexRepo
    ds = Dataset(path).create()
    (ds.pathobj / "foo").write_text("foo")
    ds.save()
    # get_content_annexinfo() is expensive.  If fr=None, we should
    # only need to call it once.
    with patch.object(AnnexRepo, "get_content_annexinfo") as gca:
        res = ds.diff(fr=None, to="HEAD", annex="all", result_renderer='disabled')
        eq_(gca.call_count, 1)
