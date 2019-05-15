# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test dataset diff

"""

__docformat__ = 'restructuredtext'

from six import text_type
import os
import os.path as op
from datalad.support.exceptions import (
    NoDatasetArgumentFound,
)

from datalad.consts import PRE_INIT_COMMIT_SHA
from datalad.cmd import GitRunner
from datalad.utils import (
    on_windows,
)
from datalad.tests.utils import (
    with_tempfile,
    create_tree,
    eq_,
    ok_,
    assert_raises,
    assert_status,
    assert_in,
    chpwd,
    assert_result_count,
    OBSCURE_FILENAME,
)

import datalad.utils as ut
from datalad.distribution.dataset import Dataset
from datalad.api import (
    save,
    create,
    diff,
)
from datalad.tests.utils import (
    get_deeply_nested_structure,
    has_symlink_capability,
    assert_repo_status,
)


def test_magic_number():
    # we hard code the magic SHA1 that represents the state of a Git repo
    # prior to the first commit -- used to diff from scratch to a specific
    # commit
    # given the level of dark magic, we better test whether this stays
    # constant across Git versions (it should!)
    out, err = GitRunner().run('cd ./ | git hash-object --stdin -t tree')
    eq_(out.strip(), PRE_INIT_COMMIT_SHA)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_repo_diff(path, norepo):
    ds = Dataset(path).create()
    assert_repo_status(ds.path)
    assert_raises(ValueError, ds.repo.diff, fr='WTF', to='MIKE')
    # no diff
    eq_(ds.repo.diff('HEAD', None), {})
    # bogus path makes no difference
    eq_(ds.repo.diff('HEAD', None, paths=['THIS']), {})
    # let's introduce a known change
    create_tree(ds.path, {'new': 'empty'})
    ds.save(to_git=True)
    assert_repo_status(ds.path)
    eq_(ds.repo.diff(fr='HEAD~1', to='HEAD'),
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
    eq_(ds.repo.diff(fr='HEAD', to=None),
        ds.repo.diff(fr='HEAD', to=None, paths=['new']))
    # also given a directory as a constraint does the same
    eq_(ds.repo.diff(fr='HEAD', to=None),
        ds.repo.diff(fr='HEAD', to=None, paths=['.']))
    # but if we give another path, it doesn't show up
    eq_(ds.repo.diff(fr='HEAD', to=None, paths=['other']), {})

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

    # again a unmatching path constrainted will give an empty report
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
def test_diff(path, norepo):
    with chpwd(norepo):
        assert_raises(NoDatasetArgumentFound, diff)
    ds = Dataset(path).create()
    assert_repo_status(ds.path)
    # reports stupid revision input
    assert_result_count(
        ds.diff(fr='WTF', on_failure='ignore'),
        1,
        status='impossible',
        message="Git reference 'WTF' invalid")
    # no diff
    assert_result_count(_dirty_results(ds.diff()), 0)
    assert_result_count(_dirty_results(ds.diff(fr='HEAD')), 0)
    # bogus path makes no difference
    assert_result_count(_dirty_results(ds.diff(path='THIS', fr='HEAD')), 0)
    # let's introduce a known change
    create_tree(ds.path, {'new': 'empty'})
    ds.save(to_git=True)
    assert_repo_status(ds.path)
    res = _dirty_results(ds.diff(fr='HEAD~1'))
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, action='diff', path=op.join(ds.path, 'new'), state='added')
    # we can also find the diff without going through the dataset explicitly
    with chpwd(ds.path):
        assert_result_count(
            _dirty_results(diff(fr='HEAD~1')), 1,
            action='diff', path=op.join(ds.path, 'new'), state='added')
    # no diff against HEAD
    assert_result_count(_dirty_results(ds.diff()), 0)
    # modify known file
    create_tree(ds.path, {'new': 'notempty'})
    res = _dirty_results(ds.diff())
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, action='diff', path=op.join(ds.path, 'new'),
        state='modified')
    # but if we give another path, it doesn't show up
    assert_result_count(ds.diff(path='otherpath'), 0)
    # giving the right path must work though
    assert_result_count(
        ds.diff(path='new'), 1,
        action='diff', path=op.join(ds.path, 'new'), state='modified')
    # stage changes
    ds.repo.add('.', git=True)
    # no change in diff, staged is not commited
    assert_result_count(_dirty_results(ds.diff()), 1)
    ds.save()
    assert_repo_status(ds.path)
    assert_result_count(_dirty_results(ds.diff()), 0)

    # untracked stuff
    create_tree(ds.path, {'deep': {'down': 'untracked', 'down2': 'tobeadded'}})
    # a plain diff should report the untracked file
    # but not directly, because the parent dir is already unknown
    res = _dirty_results(ds.diff())
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, state='untracked', type='directory',
        path=op.join(ds.path, 'deep'))
    # report of individual files is also possible
    assert_result_count(
        ds.diff(untracked='all'), 2, state='untracked', type='file')
    # an unmatching path will hide this result
    assert_result_count(ds.diff(path='somewhere'), 0)
    # perfect match and anything underneath will do
    assert_result_count(
        ds.diff(path='deep'), 1, state='untracked',
        path=op.join(ds.path, 'deep'),
        type='directory')
    assert_result_count(
        ds.diff(path='deep'), 1,
        state='untracked', path=op.join(ds.path, 'deep'))
    ds.repo.add(op.join('deep', 'down2'), git=True)
    # now the remaining file is the only untracked one
    assert_result_count(
        ds.diff(), 1, state='untracked',
        path=op.join(ds.path, 'deep', 'down'),
        type='file')


@with_tempfile(mkdir=True)
def test_diff_recursive(path):
    ds = Dataset(path).create()
    sub = ds.create('sub')
    # look at the last change, and confirm a dataset was added
    res = ds.diff(fr='HEAD~1', to='HEAD')
    assert_result_count(
        res, 1, action='diff', state='added', path=sub.path, type='dataset')
    # now recursive
    res = ds.diff(recursive=True, fr='HEAD~1', to='HEAD')
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
    res = ds.diff(recursive=True, untracked='all')
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
    # look at the last change, only one file was added
    res = ds.diff(fr='HEAD~1', to='HEAD')
    assert_result_count(_dirty_results(res), 1)
    assert_result_count(
        res, 1,
        action='diff', state='added', path=op.join(ds.path, 'onefile'),
        type='file')

    # now the exact same thing with recursion, must not be different from the
    # call above
    res = ds.diff(recursive=True, fr='HEAD~1', to='HEAD')
    assert_result_count(_dirty_results(res), 1)
    # last change in parent
    assert_result_count(
        res, 1, action='diff', state='added', path=op.join(ds.path, 'onefile'),
        type='file')

    # one further back brings in the modified subdataset, and the added file
    # within it
    res = ds.diff(recursive=True, fr='HEAD~2', to='HEAD')
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
def test_path_diff(_path, linkpath):
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
    if not on_windows:
        # TODO test should also be has_symlink_capability(), but
        # something in the repo base class is not behaving yet
        # check the premise of this test
        assert ds.pathobj != ds.repo.pathobj

    plain_recursive = ds.diff(recursive=True, annex='all')
    # check integrity of individual reports with a focus on how symlinks
    # are reported
    for res in plain_recursive:
        # anything that is an "intended" symlink should be reported
        # as such. In contrast, anything that is a symlink for mere
        # technical reasons (annex using it for something in some mode)
        # should be reported as the thing it is representing (i.e.
        # a file)
        if 'link2' in text_type(res['path']):
            assert res['type'] == 'symlink', res
        else:
            assert res['type'] != 'symlink', res
        # every item must report its parent dataset
        assert_in('parentds', res)

    # bunch of smoke tests
    # query of '.' is same as no path
    eq_(plain_recursive, ds.diff(path='.', recursive=True, annex='all'))
    # duplicate paths do not change things
    eq_(plain_recursive, ds.diff(path=['.', '.'], recursive=True, annex='all'))
    # neither do nested paths
    eq_(plain_recursive,
        ds.diff(path=['.', 'subds_modified'], recursive=True, annex='all'))
    # when invoked in a subdir of a dataset it still reports on the full thing
    # just like `git status`, as long as there are no paths specified
    with chpwd(op.join(path, 'directory_untracked')):
        plain_recursive = diff(recursive=True, annex='all')
    # should be able to take absolute paths and yield the same
    # output
    eq_(plain_recursive, ds.diff(path=ds.path, recursive=True, annex='all'))

    # query for a deeply nested path from the top, should just work with a
    # variety of approaches
    rpath = op.join('subds_modified', 'subds_lvl1_modified',
                    u'{}_directory_untracked'.format(OBSCURE_FILENAME))
    apathobj = ds.pathobj / rpath
    apath = text_type(apathobj)
    for p in (rpath, apath, None):
        if p is None:
            # change into the realpath of the dataset and
            # query with an explicit path
            with chpwd(ds.path):
                res = ds.diff(
                    path=op.join('.', rpath),
                    recursive=True,
                    annex='all')
        else:
            res = ds.diff(
                path=p,
                recursive=True,
                annex='all')
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
            recursive=True),
        1,
        path=apath)
    # limiting recursion will exclude this particular path
    assert_result_count(
        ds.diff(
            recursive=True,
            recursion_limit=1),
        0,
        path=apath)
    # negative limit is unlimited limit
    eq_(
        ds.diff(recursive=True, recursion_limit=-1),
        ds.diff(recursive=True)
    )


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_diff_nods(path, otherpath):
    ds = Dataset(path).create()
    assert_result_count(
        ds.diff(path=otherpath, on_failure='ignore'),
        1,
        status='error',
        message='path not underneath this dataset')
    otherds = Dataset(otherpath).create()
    assert_result_count(
        ds.diff(path=otherpath, on_failure='ignore'),
        1,
        path=otherds.path,
        status='error',
        message=(
            'dataset containing given paths is not underneath the '
            'reference dataset %s: %s', ds, otherds.path)
    )


@with_tempfile(mkdir=True)
def test_diff_rsync_syntax(path):
    # three nested datasets
    ds = Dataset(path).create()
    subds = ds.create('sub')
    subsubds = subds.create('deep')
    justtop = ds.diff(fr=PRE_INIT_COMMIT_SHA, path='sub')
    # we only get a single result, the subdataset in question
    assert_result_count(justtop, 1)
    assert_result_count(justtop, 1, type='dataset', path=subds.path)
    # now with "peak inside the dataset" syntax
    inside = ds.diff(fr=PRE_INIT_COMMIT_SHA, path='sub' + os.sep)
    # we get both subdatasets, but nothing else inside the nested one
    assert_result_count(inside, 2, type='dataset')
    assert_result_count(inside, 1, type='dataset', path=subds.path)
    assert_result_count(inside, 1, type='dataset', path=subsubds.path)
    assert_result_count(inside, 0, type='file', parentds=subsubds.path)
    # just for completeness, we get more when going full recursive
    rec = ds.diff(fr=PRE_INIT_COMMIT_SHA, recursive=True, path='sub' + os.sep)
    assert(len(inside) < len(rec))


@with_tempfile(mkdir=True)
def test_diff_nonexistent_ref_unicode(path):
    ds = Dataset(path).create()
    assert_result_count(
        ds.diff(fr="HEAD", to=u"β", on_failure="ignore"),
        1,
        path=ds.path,
        status="impossible")
