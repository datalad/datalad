# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test saveds function"""

import os
import os.path as op
import shutil
from unittest.mock import patch

from datalad.api import create
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_repo_status,
    create_tree,
    eq_,
    get_annexstatus,
    get_convoluted_situation,
    known_failure_windows,
    slow,
    with_tempfile,
)
from datalad.utils import (
    on_windows,
    rmtree,
)


@with_tempfile
def test_save_basics(path=None):
    ds = Dataset(path).create(result_renderer='disabled')
    # nothing happens
    eq_(list(ds.repo.save(paths=[], _status={})),
        [])

    # dataset is clean, so nothing happens with all on default
    eq_(list(ds.repo.save()),
        [])


def _test_save_all(path, repocls):
    ds = get_convoluted_situation(path, repocls)
    orig_status = ds.repo.status(untracked='all')
    # TODO test the results when the are crafted
    res = ds.repo.save()
    # make sure we get a 'delete' result for each deleted file
    eq_(
        set(r['path'] for r in res if r['action'] == 'delete'),
        {str(k) for k, v in orig_status.items()
         if k.name in ('file_deleted', 'file_staged_deleted')}
    )
    saved_status = ds.repo.status(untracked='all')
    # we still have an entry for everything that did not get deleted
    # intentionally
    eq_(
        len([f for f, p in orig_status.items()
             if not f.match('*_deleted')]),
        len(saved_status))
    # everything but subdataset entries that contain untracked content,
    # or modified subsubdatasets is now clean, a repo simply doesn touch
    # other repos' private parts
    for f, p in saved_status.items():
        if p.get('state', None) != 'clean':
            assert f.match('subds_modified'), f

    # Since we already have rich filetree, now save at dataset level
    # recursively and introspect some known gotchas
    resr = ds.save(recursive=True)

    # File within subdataset got committed to git-annex, which was not the
    # case for GitRepo parent https://github.com/datalad/datalad/issues/7351
    assert_in_results(
        resr,
        status='ok',
        path=str(ds.pathobj / 'subds_modified' / 'someds' / 'dirtyds' / 'file_untracked'),
        # if key is None -- was committed to git which should have not happened!
        key="MD5E-s14--2c320e0c56ed653384a926292647f226")

    return ds


@slow  # 11sec on travis
@known_failure_windows  # see gh-5462
@with_tempfile
def test_gitrepo_save_all(path=None):
    _test_save_all(path, GitRepo)


@slow  # 11sec on travis
@known_failure_windows  # see gh-5462
@with_tempfile
def test_annexrepo_save_all(path=None):
    _test_save_all(path, AnnexRepo)


@with_tempfile
def test_save_typechange(path=None):
    ckwa = dict(result_renderer='disabled')
    ds = Dataset(path).create(**ckwa)
    foo = ds.pathobj / 'foo'
    # save a file
    foo.write_text('some')
    ds.save(**ckwa)
    # now delete the file and replace with a directory and a file in it
    foo.unlink()
    foo.mkdir()
    bar = foo / 'bar'
    bar.write_text('foobar')
    res = ds.save(**ckwa)
    assert_in_results(res, path=str(bar), action='add', status='ok')
    assert_repo_status(ds.repo)
    if not on_windows:
        # now replace file with subdataset
        # (this is https://github.com/datalad/datalad/issues/5418)
        bar.unlink()
        Dataset(ds.pathobj / 'tmp').create(**ckwa)
        shutil.move(ds.pathobj / 'tmp', bar)
        res = ds.save(**ckwa)
        assert_repo_status(ds.repo)
        assert len(ds.subdatasets(**ckwa)) == 1
    # now replace directory with subdataset
    rmtree(foo)
    Dataset(ds.pathobj / 'tmp').create(**ckwa)
    shutil.move(ds.pathobj / 'tmp', foo)
    # right now a first save() will save the subdataset removal only
    ds.save(**ckwa)
    # subdataset is gone
    assert len(ds.subdatasets(**ckwa)) == 0
    # but it takes a second save() run to get a valid status report
    # to understand that there is a new subdataset on a higher level
    ds.save(**ckwa)
    assert_repo_status(ds.repo)
    assert len(ds.subdatasets(**ckwa)) == 1
    # now replace subdataset with a file
    rmtree(foo)
    foo.write_text('some')
    ds.save(**ckwa)
    assert_repo_status(ds.repo)


@with_tempfile
def test_save_annex_add_batch(path=None):
    ckwa = dict(result_renderer='disabled')
    ds = Dataset(path).create(**ckwa)
    create_tree(ds.path, {'tracked': 'tracked'})
    ds.save(to_git=True, **ckwa)
    untracked = ['file1', ' lead and trail ', op.join('sub', 'file2')]
    create_tree(ds.path, {
        'file1': 'file1',
        ' lead and trail ': 'lead and trail',
        'sub': {'file2': 'file2'},
        'tracked': 'modified',
    })
    with patch.object(ds.repo, '_call_annex_records',
                      wraps=ds.repo._call_annex_records) as call_annex_records:
        res = ds.save(**ckwa)
    assert_repo_status(ds.repo)
    for name in untracked + ['tracked']:
        assert_in_results(
            res, action='add', status='ok', path=str(ds.pathobj / name))
    # all untracked files are fed to a single `git annex add --batch`,
    # a modified tracked file is given on the command line
    batch_call, cmdline_call = [
        c for c in call_annex_records.call_args_list if c.args[0][0] == 'add']
    assert_in('--batch', batch_call.args[0])
    eq_(sorted(batch_call.kwargs['stdin'].split(b'\0')[:-1]),
        sorted(os.fsencode(n) for n in untracked))
    assert_not_in('--batch', cmdline_call.args[0])
    eq_(cmdline_call.kwargs['files'], ['tracked'])

    # paths `git annex add --batch` would not handle like the non-batch mode
    # does, are given on the command line: a directory, and a file within a
    # repository nested in this one (not to be added to this repository)
    create_tree(ds.path, {'another': 'another', 'dir': {'file3': 'file3'}})
    nested = GitRepo(ds.pathobj / 'nested', create=True)
    create_tree(nested.path, {'innested': 'innested'})
    with patch.object(ds.repo, '_call_annex_records',
                      wraps=ds.repo._call_annex_records) as call_annex_records:
        res = list(ds.repo._save_add({
            p: {'state': 'untracked', 'type': 'file'}
            for p in ('another', 'dir', op.join('nested', 'innested'),
                      'vanished')}))
    batch_call, cmdline_call = call_annex_records.call_args_list
    eq_(batch_call.kwargs['stdin'], b'another\0vanished\0')
    eq_(cmdline_call.kwargs['files'], ['dir', op.join('nested', 'innested')])
    assert_in_results(
        res, action='add', status='ok', path=ds.pathobj / 'another')
    assert_in_results(
        res, action='add', status='ok', path=ds.pathobj / 'dir' / 'file3')
    # as in non-batch mode, a file vanished since status() is an error
    assert_in_results(
        res, action='add', status='error', path=ds.pathobj / 'vanished')
    eq_(len(res), 3)


@with_tempfile
def test_save_to_git(path=None):
    ds = Dataset(path).create(result_renderer='disabled')
    create_tree(
        ds.path,
        {
            'file_ingit': 'file_ingit',
            'file_inannex': 'file_inannex',
        }
    )
    ds.repo.save(paths=['file_ingit'], git=True)
    ds.repo.save(paths=['file_inannex'])
    assert_repo_status(ds.repo)
    for f, p in get_annexstatus(ds.repo).items():
        eq_(p['state'], 'clean')
        if f.match('*ingit'):
            assert_not_in('key', p, f)
        elif f.match('*inannex'):
            assert_in('key', p, f)


@with_tempfile
def test_save_subds_change(path=None):
    ckwa = dict(result_renderer='disabled')
    ds = Dataset(path).create(**ckwa)
    subds = ds.create('sub', **ckwa)
    assert_repo_status(ds.repo)
    rmtree(subds.path)
    res = ds.save(**ckwa)
    assert_repo_status(ds.repo)
    # updated .gitmodules, deleted subds, saved superds
    assert len(res) == 3
    assert_in_results(
        res, type='dataset', path=ds.path, action='save')
    assert_in_results(
        res, type='dataset', path=subds.path, action='delete')
    assert_in_results(
        res, type='file', path=str(ds.pathobj / '.gitmodules'), action='add')
    # now add one via save
    subds2 = create(ds.pathobj / 'sub2', **ckwa)
    res = ds.save(**ckwa)
    # updated .gitmodules, added subds, saved superds
    assert len(res) == 3
    assert_repo_status(ds.repo)
    assert_in_results(
        res, type='dataset', path=ds.path, action='save')
    assert_in_results(
        res, type='dataset', path=subds2.path, action='add')
    assert_in_results(
        res, type='file', path=str(ds.pathobj / '.gitmodules'), action='add')
