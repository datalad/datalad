# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test install action

"""

import os
from os.path import join as opj, abspath
from ..dataset import Dataset
from datalad.api import install
from datalad.distribution.install import get_containing_subdataset
from datalad.utils import chpwd
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false
from datalad.tests.utils import with_tempfile, assert_in, with_tree, with_testrepos, assert_not_in
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_cwd_unchanged, skip_if_on_windows
from datalad.tests.utils import assure_dict_from_str, assure_list_from_str
from datalad.tests.utils import ok_generator
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module
from datalad.tests.utils import ok_clean_git


@with_tree(tree={'test.txt': 'whatever'})
def test_get_containing_subdataset(path):

    ds = Dataset(path).install()
    ds.install(path='test.txt')
    ds.remember_state("Initial commit")
    subds = ds.install("sub", source=path)
    eq_(get_containing_subdataset(ds, opj("sub", "some")).path, subds.path)
    eq_(get_containing_subdataset(ds, "some").path, ds.path)

    outside_path = opj(os.pardir, "somewhere", "else")
    assert_raises(ValueError, get_containing_subdataset, ds, outside_path)
    assert_raises(ValueError, get_containing_subdataset, ds,
                  opj(os.curdir, outside_path))
    assert_raises(ValueError, get_containing_subdataset, ds,
                  abspath(outside_path))


@with_tempfile
def test_create(path):
    # only needs a path
    ds = install(path)
    ok_(ds.is_installed())
    ok_clean_git(path, annex=False)

    sub_path_1 = opj(path, "sub")
    subds1 = install(sub_path_1)
    ok_(subds1.is_installed())
    ok_clean_git(sub_path_1, annex=False)
    # wasn't installed into ds:
    assert_not_in("sub", ds.get_dataset_handles())
    # => TODO: inplace; see below

    sub_path_2 = opj(path, "sub2")
    subds2 = install(ds, path=sub_path_2)
    ok_(subds2.is_installed())
    ok_clean_git(sub_path_2, annex=False)
    # was installed into ds:
    assert_in("sub2", ds.get_dataset_handles())
    # TODO: Fails => Fix it. Line 281


@with_tree(tree={'test.txt': 'some',
                 'dir': {'testindir': 'someother',
                         'testindir2': 'none'}})
def test_install_files(path):
    ds = install(path)
    # install a single file
    eq_(ds.install('test.txt'), opj(path, 'test.txt'))
    # install it again, should given same result
    eq_(ds.install('test.txt'), opj(path, 'test.txt'))
    # install multiple files in a dir
    eq_(ds.install('dir', recursive=True),
        [opj(path, 'dir', 'testindir'),
         opj(path, 'dir', 'testindir2')])
    # TODO: check git


@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_install_dataset_from(url, path):
    ds = install(path=path, source=url)
    eq_(ds.path, path)
    ok_(ds.is_installed())
    ok_clean_git(path, annex=False)


@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_install_into_dataset(source, top_path):
    ds = install(top_path)
    subds = ds.install(path="sub", source=source)
    ok_(subds.is_installed())
    # sub is clean:
    ok_clean_git(subds.path, annex=False)
    # top is not:
    assert_raises(AssertionError, ok_clean_git, ds.path, annex=False)
    assert_in("sub", ds.get_dataset_handles())


def test_install_subdataset():
    # needs nested dataset installed non-recursively
    raise SkipTest("TODO")


def test_install_list():
    raise SkipTest("TODO")


def test_install_missing_arguments():
    raise SkipTest("TODO")


def test_install_recursive():
    raise SkipTest("TODO")


# TODO: Is there a way to test result renderer?

