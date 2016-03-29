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
from os.path import join as opj, abspath, normpath
from ..dataset import Dataset, EnsureDataset, resolve_path
from datalad.utils import chpwd, getpwd
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_equal, assert_true
from datalad.tests.utils import with_tempfile, assert_in, with_tree
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_cwd_unchanged, skip_if_on_windows
from datalad.tests.utils import assure_dict_from_str, assure_list_from_str
from datalad.tests.utils import ok_generator
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module


def test_EnsureDataset():

    c = EnsureDataset()

    # fails with anything else than a string or an Dataset:
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
# TODO: proper testrepos needed!
def register_sibling():
    # Validation!
    raise SkipTest("TODO")


def test_get_dataset_handles():
    # Flavors!
    raise SkipTest("TODO")


def test_is_installed():
    # different platforms, direct mode, etc.
    raise SkipTest("TODO")


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
    from datalad.api import install
    # from scratch
    ds = Dataset(path)
    assert_false(ds.is_installed())
    eq_(ds.get_dataset_handles(), None)
    ds = ds.install()
    assert_true(ds.is_installed())
    eq_(ds.get_dataset_handles(), [])
    # create some file and commit it
    open(os.path.join(ds.path, 'test'), 'w').write('some')
    ds.install(path='test')
    assert_true(ds.is_installed())
    # TODO change to remember_state()
    ds.remember_state("Hello!", version=1)
    # add a subdataset
    subds = ds.install('subds', source=path)
    assert_true(subds.is_installed())
    subdss = ds.get_dataset_handles()
    eq_(len(subdss), 1)
    eq_(os.path.join(path, subdss[0]), subds.path)
    eq_(subds.path, ds.get_dataset_handles(absolute=True)[0])
    eq_(subdss, ds.get_dataset_handles(recursive=True))
    eq_(subdss, ds.get_dataset_handles(fulfilled=True))
    # don't have that right now
    assert_raises(NotImplementedError, ds.get_dataset_handles, pattern='sub*')
    ds.remember_state("with subds", version=2)
    ds.recall_state(1)
    assert_true(ds.is_installed())
    eq_(ds.get_dataset_handles(), [])
    # TODO actual submodule checkout is still there
