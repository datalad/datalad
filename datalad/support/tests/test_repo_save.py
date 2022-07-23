# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test saveds function"""

import shutil

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
    ds = get_convoluted_situation(path, GitRepo)
    orig_status = ds.repo.status(untracked='all')
    # TODO test the results when the are crafted
    res = ds.repo.save()
    # make sure we get a 'delete' result for each deleted file
    eq_(
        set(r['path'] for r in res if r['action'] == 'delete'),
        {k for k, v in orig_status.items()
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
    filelinktype = 'file' if ds.repo.is_managed_branch() else 'symlink'

    foo = ds.pathobj / 'foo'
    # save a file
    foo.write_text('some')
    assert_in_results(
        ds.status(path=foo, **ckwa),
        type='file',
        state='untracked',
    )
    ds.save(**ckwa)
    # now delete the file and replace with a directory and a file in it
    foo.unlink()
    assert_in_results(
        ds.status(path=foo, **ckwa),
        type=filelinktype,
        state='deleted',
    )
    foo.mkdir()
    # a directory is not enough for git to change its minds just yet
    assert_in_results(
        ds.status(path=foo, **ckwa),
        type=filelinktype,
        state='deleted',
    )
    bar = foo / 'bar'
    bar.write_text('foobar')
    assert_in_results(
        ds.status(path=foo, **ckwa),
        type=filelinktype,
        state='deleted',
    )
    assert_in_results(
        ds.status(path=bar, **ckwa),
        type='file',
        state='untracked',
    )
    res = ds.save(**ckwa)
    assert_in_results(res, path=str(bar), action='add', status='ok')
    assert_repo_status(ds.repo)
    # AKA not on crippled FS
    # https://github.com/datalad/datalad/issues/6857
    if filelinktype == 'symlink':
        # now replace file with subdataset
        # (this is https://github.com/datalad/datalad/issues/5418)
        bar.unlink()
        subds = Dataset(ds.pathobj / 'tmp').create(**ckwa)
        subdshexsha = subds.repo.get_hexsha(subds.repo.get_corresponding_branch())
        shutil.move(ds.pathobj / 'tmp', bar)
        assert_in_results(
            ds.status(path=bar, **ckwa),
            type='dataset',
            prev_type=filelinktype,
            state='modified',
        )
        res = ds.save(**ckwa)
        assert_repo_status(ds.repo)
        assert len(ds.subdatasets(**ckwa)) == 1
    # now replace directory with subdataset
    rmtree(foo)
    # AKA not on crippled FS, need to make conditional, because we did it above too
    if filelinktype == 'symlink':
        assert_in_results(
            ds.status(path=bar, **ckwa),
            type='dataset',
            prev_gitshasum=subdshexsha,
            state='deleted',
        )
    newsubds = Dataset(ds.pathobj / 'tmp').create(**ckwa)
    newsubdshexsha = newsubds.repo.get_hexsha(
        newsubds.repo.get_corresponding_branch())
    shutil.move(ds.pathobj / 'tmp', foo)
    # AKA not on crippled FS, need to make conditional, because we did it above too
    if filelinktype == 'symlink':
        # right now neither datalad not git recognize a repo that
        # is inserted between the root repo and a known subdataset
        # (still registered in index)
        assert_in_results(
            ds.status(path=foo, **ckwa),
            type='dataset',
            prev_gitshasum=subdshexsha,
            state='deleted',
        )
    # a first save() will save the subdataset removal only
    ds.save(**ckwa)
    # subdataset is gone
    assert len(ds.subdatasets(**ckwa)) == 0
    # this brings back the sanity of the status git (again for both
    # git and datalad)
    assert_in_results(
        ds.status(path=foo, **ckwa),
        # not yet recognized as a dataset, a good thing, because it
        # would be more expensive to figuure this out
        type='directory',
        state='untracked',
    )
    ds.save(**ckwa)
    assert_repo_status(ds.repo)
    assert len(ds.subdatasets(**ckwa)) == 1
    if filelinktype == 'file':
        # no point in continuing when on crippled FS due to
        # https://github.com/datalad/datalad/issues/6857
        return
    # now replace subdataset with a file
    rmtree(foo)
    foo.write_text('some')
    assert_in_results(
        ds.status(path=foo, **ckwa),
        # not yet recognized as a dataset, a good thing, because it
        # would be more expensive to figuure this out
        type='file',
        prev_type='dataset',
        state='modified',
        prev_gitshasum=newsubdshexsha,

    )
    ds.save(**ckwa)
    assert_repo_status(ds.repo)


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
