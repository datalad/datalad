# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test saveds fuction"""

from six import iteritems

from datalad.tests.utils import (
    assert_in,
    assert_not_in,
    create_tree,
    with_tempfile,
    eq_,
)

from datalad.distribution.dataset import Dataset
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import (
    assert_repo_status,
    get_convoluted_situation,
)


@with_tempfile
def test_save_basics(path):
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
        {k for k, v in iteritems(orig_status) if k.name == 'file_deleted'}
    )
    saved_status = ds.repo.status(untracked='all')
    # we still have an entry for everything that did not get deleted
    # intentionally
    eq_(
        len([f for f, p in iteritems(orig_status)
             if not f.match('*_deleted')]),
        len(saved_status))
    # everything but subdataset entries that contain untracked content,
    # or modified subsubdatasets is now clean, a repo simply doesn touch
    # other repos' private parts
    for f, p in iteritems(saved_status):
        if p.get('state', None) != 'clean':
            assert f.match('subds_modified'), f
    return ds


@with_tempfile
def test_gitrepo_save_all(path):
    _test_save_all(path, GitRepo)


@with_tempfile
def test_annexrepo_save_all(path):
    _test_save_all(path, AnnexRepo)


@with_tempfile
def test_save_to_git(path):
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
    for f, p in iteritems(ds.repo.annexstatus()):
        eq_(p['state'], 'clean')
        if f.match('*ingit'):
            assert_not_in('key', p, f)
        elif f.match('*inannex'):
            assert_in('key', p, f)
