# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test saveds function"""

import shutil

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
    ds = Dataset(path).create()
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
        {k for k, v in orig_status.items() if k.name == 'file_deleted'}
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
def test_save_to_git(path=None):
    ds = Dataset(path).create()
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
