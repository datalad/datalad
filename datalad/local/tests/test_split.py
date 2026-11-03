# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test split"""

import posixpath
from unittest.mock import patch

from datalad.api import clone
from datalad.distribution.dataset import Dataset
from datalad.local import split as split_mod
from datalad.tests.utils_pytest import (
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_repo_status,
    assert_result_count,
    eq_,
    neq_,
    skip_if_adjusted_branch,
    with_tempfile,
    with_tree,
)


def _history_symlinks(repo):
    """{(commit, path): target} for all symlinks in the history of HEAD"""
    return {
        (c, path): repo.call_git(['cat-file', 'blob', sha])
        for c in repo.call_git(['rev-list', 'HEAD']).split()
        for mode, _, sha, path in (
            item.split(None, 3) for item in list(repo.call_git_items_(
                ['ls-tree', '-r', '-z', c], sep='\0')))
        if mode == '120000'
    }


@skip_if_adjusted_branch
@with_tree(tree={'a': {'b': {'f': 'f', 'gone': 'gone', 'c': {'sp ace ': 'sp'}}},
                 'd': {'f': 'df'},
                 'other': 'other'})
@with_tempfile
def test_split_annex(path=None, clonepath=None):
    ds = Dataset(path).create(force=True)
    ds.save(message='initial')
    gone_key = ds.repo.get_file_annexinfo('a/b/gone')['key']
    ds.repo.remove('a/b/gone')
    (ds.pathobj / 'a' / 'b' / 'c' / 'new').write_text('new')
    ds.save(message='second')
    other_key = ds.repo.get_file_annexinfo('other')['key']
    head = ds.repo.get_hexsha()

    res = ds.split(['a/b', 'd'])
    assert_result_count(res, 2)
    for p in ('a/b', 'd'):
        assert_in_results(res, action='split', status='ok',
                          path=str(ds.pathobj / p), type='dataset')
    assert_repo_status(ds.path)
    # one new commit on top of the untouched history
    eq_(ds.repo.get_hexsha('HEAD~1'), head)
    eq_(ds.repo.format_commit('%s'),
        '[DATALAD] Split a/b, d into subdatasets')
    eq_((ds.pathobj / 'other').read_text(), 'other')
    subds = Dataset(ds.pathobj / 'a' / 'b')
    assert_repo_status(subds.path)
    subs = ds.subdatasets(result_renderer='disabled')
    assert_result_count(subs, 2)
    assert_result_count(subs, 1, path=subds.path, gitmodule_url='./a/b',
                        **{'gitmodule_datalad-id': subds.id})
    eq_(subds.repo.get_remotes(), [])
    # no objects of the parent's history remain
    assert not subds.repo.call_git_success(['cat-file', '-e', head])
    neq_(subds.id, ds.id)
    eq_(subds.repo.call_git(['log', '--format=%s']).splitlines(),
        ['[DATALAD] new dataset', 'second', 'initial'])
    links = _history_symlinks(subds.repo)
    eq_({p for _, p in links}, {'f', 'gone', 'c/sp ace ', 'c/new'})
    for (_, p), target in links.items():
        assert posixpath.normpath(
            posixpath.join(posixpath.dirname(p), target)).startswith(
                '.git/annex/objects/'), (p, target)
    eq_(set(subds.repo.call_git_items_(['for-each-ref', '--format=%(refname)',
                                        'refs/heads', 'refs/remotes',
                                        'refs/tags', 'refs/original'])),
        {'refs/heads/' + ds.repo.get_active_branch(), 'refs/heads/git-annex'})
    annexed = subds.repo.call_git(['ls-tree', '-r', '--name-only', 'git-annex'])
    assert_not_in(other_key, annexed)
    # info on keys only used in older commits is kept
    assert_in(gone_key, annexed)
    eq_((subds.pathobj / 'c' / 'sp ace ').read_text(), 'sp')
    # a clone of the parent can get content from the new subdatasets
    cloned = clone(source=ds.path, path=clonepath, result_renderer='disabled')
    cloned.get(['a/b/c/sp ace ', 'd/f'], result_renderer='disabled')
    eq_((cloned.pathobj / 'a' / 'b' / 'c' / 'sp ace ').read_text(), 'sp')
    eq_((cloned.pathobj / 'd' / 'f').read_text(), 'df')


@with_tree(tree={'a': {'b': {'f': 'f', '.datalad': {'x': 'x'}}, 'g': 'g'}})
def test_split_git(path=None):
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()
    ds.split('a/b')
    assert_repo_status(ds.path)
    subds = Dataset(ds.pathobj / 'a' / 'b')
    eq_(subds.repo.call_git(['ls-files']).split(), ['.datalad/config', '.datalad/x', 'f'])
    eq_((subds.pathobj / 'f').read_text(), 'f')
    eq_((ds.pathobj / 'a' / 'g').read_text(), 'g')


@with_tree(tree={'d': {'f': 'f', 'e': {'f': 'f'}}, 'f': 'f',
                 'i': {'f': 'f'}, '.gitignore': '*.log'})
def test_split_refusals(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    ds.create('d/sub')
    head = ds.repo.get_hexsha()

    def check(p, msg, status='impossible'):
        res = ds.split(p, on_failure='ignore', result_renderer='disabled')
        assert_in_results(res, action='split', status=status, message=msg)
        eq_(ds.repo.get_hexsha(), head)

    if ds.repo.is_managed_branch():
        check('d/e', 'datasets on an adjusted branch are not supported')
        return
    check('f', 'path is not a directory with tracked content')
    check('nothere', 'path is not a directory with tracked content')
    check(ds.pathobj.parent, 'path is not a directory within the dataset')
    check(['d/e', 'd'], 'path overlaps with another path to split')
    check('d', 'splitting directories with subdatasets is not supported')
    # failure midway is rolled back, also for already split paths
    orig_split_one = split_mod._split_one

    def fail_second(ds_, p, rel):
        if rel.name == 'i':
            raise RuntimeError('injected')
        return orig_split_one(ds_, p, rel)

    with patch('datalad.local.split._split_one', fail_second):
        res = ds.split(['d/e', 'i'], on_failure='ignore', result_renderer='disabled')
    assert_in_results(res, action='split', status='error')
    eq_(ds.repo.get_hexsha(), head)
    assert_repo_status(ds.path)
    eq_((ds.pathobj / 'd' / 'e' / 'f').read_text(), 'f')
    (ds.pathobj / 'i' / 'x.log').write_text('x')
    check('i', 'directory contains ignored files')
    assert_repo_status(ds.path)
    (ds.pathobj / 'untracked').write_text('u')
    check('d/e', 'dataset has modifications or untracked files')
