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

from datalad.api import clone
from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
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
            line.split(None, 3) for line in repo.call_git(
                ['ls-tree', '-r', c]).splitlines())
        if mode == '120000'
    }


@skip_if_adjusted_branch
@with_tree(tree={'a': {'b': {'f': 'f', 'c': {'sp ace ': 'sp'}}},
                 'other': 'other'})
@with_tempfile
def test_split_annex(path=None, clonepath=None):
    ds = Dataset(path).create(force=True)
    ds.save(message='initial')
    (ds.pathobj / 'a' / 'b' / 'c' / 'new').write_text('new')
    ds.save(message='second')
    other_key = ds.repo.get_file_annexinfo('other')['key']

    res = ds.split('a/b')
    assert_result_count(res, 1)
    assert_in_results(res, action='split', status='ok',
                      path=str(ds.pathobj / 'a' / 'b'), type='dataset')
    assert_repo_status(ds.path)
    subds = Dataset(ds.pathobj / 'a' / 'b')
    assert_repo_status(subds.path)
    # registered subdataset with an identity of its own
    subs = ds.subdatasets(result_renderer='disabled')
    assert_result_count(subs, 1, path=subds.path,
                        **{'gitmodule_datalad-id': subds.id})
    neq_(subds.id, ds.id)
    # history of the directory, plus the commit adding the dataset id
    eq_(subds.repo.format_commit('%s', 'HEAD~1'), 'second')
    eq_(subds.repo.format_commit('%s', 'HEAD~2'), 'initial')
    # annex symlinks point into the subdataset's annex throughout history
    links = _history_symlinks(subds.repo)
    eq_({p for _, p in links}, {'f', 'c/sp ace ', 'c/new'})
    for (_, p), target in links.items():
        assert posixpath.normpath(
            posixpath.join(posixpath.dirname(p), target)).startswith(
                '.git/annex/objects/'), (p, target)
    # nothing else of the parent was carried over
    eq_(set(subds.repo.call_git_items_(['for-each-ref', '--format=%(refname)',
                                        'refs/heads', 'refs/remotes',
                                        'refs/tags', 'refs/original'])),
        {'refs/heads/' + ds.repo.get_active_branch(), 'refs/heads/git-annex'})
    assert_not_in(other_key, subds.repo.call_git(
        ['ls-tree', '-r', '--name-only', 'git-annex']))
    # content was obtained from the parent
    eq_((subds.pathobj / 'c' / 'sp ace ').read_text(), 'sp')
    # a clone of the subdataset (no pre-existing working tree) can get it
    cloned = clone(source=subds.path, path=clonepath)
    cloned.get('c/sp ace ')
    eq_((cloned.pathobj / 'c' / 'sp ace ').read_text(), 'sp')


@with_tree(tree={'a': {'b': {'f': 'f'}, 'g': 'g'}})
def test_split_git(path=None):
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()
    ds.split('a/b')
    assert_repo_status(ds.path)
    subds = Dataset(ds.pathobj / 'a' / 'b')
    eq_(subds.repo.call_git(['ls-files']).split(), ['.datalad/config', 'f'])
    eq_((subds.pathobj / 'f').read_text(), 'f')
    eq_((ds.pathobj / 'a' / 'g').read_text(), 'g')


@with_tree(tree={'d': {'f': 'f', 'e': {'f': 'f'}}, 'f': 'f'})
def test_split_refusals(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    ds.create('d/sub')
    head = ds.repo.get_hexsha()

    def check(p, msg):
        res = ds.split(p, on_failure='ignore', result_renderer='disabled')
        assert_in_results(res, action='split', status='impossible',
                          message=msg)
        eq_(ds.repo.get_hexsha(), head)

    check('f', 'path is not a directory with tracked content')
    check('nothere', 'path is not a directory with tracked content')
    check(ds.pathobj.parent, 'path is not a directory within the dataset')
    check(['d/e', 'd'], 'path overlaps with another path to split')
    check('d', 'splitting directories with subdatasets is not supported')
    assert_repo_status(ds.path)
    (ds.pathobj / 'untracked').write_text('u')
    check('d/e', 'dataset has modifications or untracked files')
