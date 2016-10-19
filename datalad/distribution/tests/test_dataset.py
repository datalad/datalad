# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test Dataset class

"""

import os
import shutil
from os.path import join as opj, abspath, normpath

from ..dataset import Dataset, EnsureDataset, resolve_path, require_dataset
from datalad.api import create
from datalad.api import install
from datalad.api import get
from datalad.consts import LOCAL_CENTRAL_PATH
from datalad.utils import chpwd, getpwd, rmtree
from datalad.utils import _path_
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_equal, assert_true
from datalad.tests.utils import with_tempfile, assert_in, with_tree, with_testrepos
from datalad.tests.utils import assert_cwd_unchanged
from datalad.tests.utils import assert_raises
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import PathOutsideRepositoryError


def test_EnsureDataset():

    c = EnsureDataset()

    # fails with anything else than a string or a Dataset:
    assert_raises(ValueError, c, 1)
    assert_raises(ValueError, c, ['a', 'list'])
    assert_raises(ValueError, c, (1, 2, 3))
    assert_raises(ValueError, c, {"what": "ever"})

    # returns Dataset, when string or Dataset passed
    res = c(opj("some", "path"))
    ok_(isinstance(res, Dataset))
    ok_(isinstance(c(res), Dataset))
    ok_(c(res) is res)

    # Note: Ensuring that string is valid path is not
    # part of the constraint itself, so not explicitly tested here.


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
def test_resolve_path(somedir):

    abs_path = abspath(somedir)  # just to be sure
    rel_path = "some"
    expl_path_cur = opj(os.curdir, rel_path)
    expl_path_par = opj(os.pardir, rel_path)

    eq_(resolve_path(abs_path), abs_path)

    current = getpwd()
    # no Dataset => resolve using cwd:
    eq_(resolve_path(abs_path), abs_path)
    eq_(resolve_path(rel_path), opj(current, rel_path))
    eq_(resolve_path(expl_path_cur), normpath(opj(current, expl_path_cur)))
    eq_(resolve_path(expl_path_par), normpath(opj(current, expl_path_par)))

    # now use a Dataset as reference:
    ds = Dataset(abs_path)
    eq_(resolve_path(abs_path, ds), abs_path)
    eq_(resolve_path(rel_path, ds), opj(abs_path, rel_path))
    eq_(resolve_path(expl_path_cur, ds), normpath(opj(current, expl_path_cur)))
    eq_(resolve_path(expl_path_par, ds), normpath(opj(current, expl_path_par)))


# TODO: test remember/recall more extensive?

@with_testrepos(flavors=['local', 'local-url'])
@with_tempfile(mkdir=True)
def test_register_sibling(remote, path):
    AnnexRepo(path)
    ds = Dataset(path)
    ds.register_sibling('my_sibling', remote)
    assert_in('my_sibling', ds.repo.get_remotes())
    eq_(ds.repo.get_remote_url('my_sibling'), remote)

    ds.register_sibling('my_other_sibling', remote,
                        publish_url='http://fake.pushurl.com')
    assert_in('my_other_sibling', ds.repo.get_remotes())
    eq_(ds.repo.get_remote_url('my_other_sibling'), remote)
    # TODO: GitRepo method for push-url!

    # TODO: Validation!


@with_testrepos('.*nested_submodule.*', flavors=['local'])
def test_get_subdatasets(path):
    ds = Dataset(path)
    eq_(set(ds.get_subdatasets()), {'sub dataset1'})
    eq_(set(ds.get_subdatasets(recursive=True)),
        {'sub dataset1/sub sub dataset1', 'sub dataset1/sub sub dataset1/subm 1',
         'sub dataset1/sub sub dataset1/subm 2', 'sub dataset1/subm 1',
         'sub dataset1/subm 2', 'sub dataset1'})
    eq_(set(ds.get_subdatasets(recursive=True, recursion_limit=0)),
        set([]))
    eq_(set(ds.get_subdatasets(recursive=True, recursion_limit=1)),
        {'sub dataset1'})
    eq_(set(ds.get_subdatasets(recursive=True, recursion_limit=2)),
        {'sub dataset1', 'sub dataset1/sub sub dataset1', 'sub dataset1/subm 1',
         'sub dataset1/subm 2'})

    # TODO:  More Flavors!


# TODO: There's something wrong with the nested testrepo!
# Fear mongering detected!
@with_testrepos('submodule_annex')
@with_tempfile(mkdir=True)
def test_is_installed(src, path):
    ds = Dataset(path)
    assert_false(ds.is_installed())

    # get a clone:
    AnnexRepo(path, src)
    ok_(ds.is_installed())
    # submodule still not installed:
    subds = Dataset(opj(path, 'subm 1'))
    assert_false(subds.is_installed())
    # get the submodule
    # This would init so there is a .git file with symlink info, which is
    # as we agreed is more pain than gain, so let's use our install which would
    # do it right, after all we are checking 'is_installed' ;)
    # from datalad.cmd import Runner
    # Runner().run(['git', 'submodule', 'update', '--init', 'subm 1'], cwd=path)
    with chpwd(path):
        get('subm 1')
    ok_(subds.is_installed())
    # wipe it out
    rmtree(ds.path)
    assert_false(ds.is_installed())


@with_tempfile(mkdir=True)
def test_dataset_contructor(path):
    # dataset needs a path
    assert_raises(TypeError, Dataset)
    assert_raises(AttributeError, Dataset, None)
    dsabs = Dataset(path)
    # always abspath
    ok_(os.path.isabs(dsabs.path))
    eq_(path, dsabs.path)
    # no repo
    eq_(dsabs.repo, None)
    # same result when executed in that path and using relative paths
    with chpwd(path):
        dsrel = Dataset('.')
        eq_(dsrel.path, dsabs.path)
        # no repo either, despite directory existing now
        eq_(dsrel.repo, None)


@with_tempfile(mkdir=True)
def test_repo_cache(path):
    ds = Dataset(path)
    # none by default
    eq_(ds.repo, None)
    # make Git repo manually
    git = GitRepo(path=path, create=True)
    repo = ds.repo
    # got one
    assert_false(repo is None)
    # stays that one
    assert_true(ds.repo is repo)
    # now turn into an annex
    annex = AnnexRepo(path=path, create=True)
    # repo instance must change
    assert_false(ds.repo is repo)
    assert_true(isinstance(ds.repo, AnnexRepo))


@with_tempfile(mkdir=True)
def test_subdatasets(path):
    # from scratch
    ds = Dataset(path)
    assert_false(ds.is_installed())
    eq_(ds.get_subdatasets(), [])
    ds = ds.create()
    assert_true(ds.is_installed())
    eq_(ds.get_subdatasets(), [])
    # create some file and commit it
    open(os.path.join(ds.path, 'test'), 'w').write('some')
    ds.add(path='test')
    assert_true(ds.is_installed())
    ds.save("Hello!", version_tag=1)
    # Assuming that tmp location was not under a super-dataset
    eq_(ds.get_superdataset(), None)
    eq_(ds.get_superdataset(topmost=True), ds)

    # add itself as a subdataset (crazy, isn't it?)
    subds = ds.install('subds', source=path)
    assert_true(subds.is_installed())
    eq_(subds.get_superdataset(), ds)
    eq_(subds.get_superdataset(topmost=True), ds)

    subdss = ds.get_subdatasets()
    eq_(len(subdss), 1)
    eq_(os.path.join(path, subdss[0]), subds.path)
    eq_(subds.path, ds.get_subdatasets(absolute=True)[0])
    eq_(subdss, ds.get_subdatasets(recursive=True))
    eq_(subdss, ds.get_subdatasets(fulfilled=True))
    # don't have that right now
    assert_raises(NotImplementedError, ds.get_subdatasets, pattern='sub*')
    ds.save("with subds", version_tag=2)
    ds.recall_state(1)
    assert_true(ds.is_installed())
    eq_(ds.get_subdatasets(), [])

    # very nested subdataset to test topmost
    subsubds = subds.install(_path_('d1/subds'), source=path)
    assert_true(subsubds.is_installed())
    eq_(subsubds.get_superdataset(), subds)
    eq_(subsubds.get_superdataset(topmost=True), ds)

    # verify that '^' alias would work
    with chpwd(subsubds.path):
        dstop = Dataset('^')
        eq_(dstop, ds)
        # and while in the dataset we still can resolve into central one
        dscentral = Dataset('///')
        eq_(dscentral.path, LOCAL_CENTRAL_PATH)

    with chpwd(ds.path):
        dstop = Dataset('^')
        eq_(dstop, ds)

    # TODO actual submodule checkout is still there


@with_tree(tree={'test.txt': 'whatever'})
def test_get_containing_subdataset(path):

    ds = create(path, force=True)
    ds.add(path='test.txt')
    ds.save("Initial commit")
    subds = ds.create("sub")
    subsubds = subds.create("subsub")

    eq_(ds.get_containing_subdataset(opj("sub", "subsub", "some")).path, subsubds.path)
    # the top of a subdataset belongs to the subdataset
    eq_(ds.get_containing_subdataset(opj("sub", "subsub")).path, subsubds.path)
    eq_(GitRepo.get_toppath(opj(ds.path, "sub", "subsub")), subsubds.path)
    eq_(ds.get_containing_subdataset(opj("sub", "some")).path, subds.path)
    eq_(ds.get_containing_subdataset("sub").path, subds.path)
    eq_(ds.get_containing_subdataset("some").path, ds.path)
    # make sure the subds is found, even when it is not present, but still
    # known
    shutil.rmtree(subds.path)
    eq_(ds.get_containing_subdataset(opj("sub", "some")).path, subds.path)
    eq_(ds.get_containing_subdataset("sub").path, subds.path)
    # # but now GitRepo disagrees...
    eq_(GitRepo.get_toppath(opj(ds.path, "sub")), ds.path)
    # and this stays, even if we give the mount point directory back
    os.makedirs(subds.path)
    eq_(GitRepo.get_toppath(opj(ds.path, "sub")), ds.path)

    outside_path = opj(os.pardir, "somewhere", "else")
    assert_raises(PathOutsideRepositoryError, ds.get_containing_subdataset,
                  outside_path)
    assert_raises(PathOutsideRepositoryError, ds.get_containing_subdataset,
                  opj(os.curdir, outside_path))
    assert_raises(PathOutsideRepositoryError, ds.get_containing_subdataset,
                  abspath(outside_path))


@with_tempfile(mkdir=True)
def test_require_dataset(path):
    with chpwd(path):
        assert_raises(
            InsufficientArgumentsError,
            require_dataset,
            None)
        create('.')
        # in this folder by default
        assert_equal(
            require_dataset(None).path,
            path)

        assert_equal(
            require_dataset('some', check_installed=False).path,
            abspath('some'))
        assert_raises(
            ValueError,
            require_dataset,
            'some',
            check_installed=True)


@with_tempfile(mkdir=True)
def test_dataset_id(path):
    ds = Dataset(path)
    assert_equal(ds.id, None)
    ds.create()
    dsorigid = ds.id
    # ID is always a UUID
    assert_equal(ds.id.count('-'), 4)
    assert_equal(len(ds.id), 36)
    # creating a new object for the same path
    # yields the same ID
    newds = Dataset(path)
    assert_false(ds is newds)
    assert_equal(ds.id, newds.id)
    # recreating the dataset does NOT change the id
    ds.create(no_annex=True, force=True)
    assert_equal(ds.id, dsorigid)
    # even adding an annex doesn't
    ds.create(force=True)
    assert_equal(ds.id, dsorigid)
    # dataset ID and annex UUID have nothing to do with each other
    # if an ID was already generated
    assert_true(ds.repo.uuid != ds.id)
    # creating a new object for the same dataset with an ID on record
    # yields the same ID
    newds = Dataset(path)
    assert_false(ds is newds)
    assert_equal(ds.id, newds.id)
    # even if we generate a dataset from scratch with an annex UUID right away,
    # this is also not the ID
    annexds = Dataset(opj(path, 'scratch')).create()
    assert_true(annexds.id != annexds.repo.uuid)
