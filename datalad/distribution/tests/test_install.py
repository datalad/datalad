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
from datalad.distribution.install import _installationpath_from_url
from datalad.utils import chpwd
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import FileInGitError
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false
from datalad.tests.utils import with_tempfile, assert_in, with_tree,\
    with_testrepos, assert_equal
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_cwd_unchanged, skip_if_on_windows
from datalad.tests.utils import assure_dict_from_str, assure_list_from_str
from datalad.tests.utils import ok_generator
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import swallow_outputs


def test_insufficient_args():
    assert_raises(InsufficientArgumentsError, install)


def test_installationpath_from_url():
    for p in ('lastbit',
              'lastbit/',
              '/lastbit',
              'lastbit.git',
              'lastbit.git/',
              'http://example.com/lastbit',
              'http://example.com/lastbit.git',
              ):
        assert_equal(_installationpath_from_url(p), 'lastbit')


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

    # any dataset created from scratch has an annex
    ok_(isinstance(ds.repo, AnnexRepo))

    sub_path_1 = opj(path, "sub")
    subds1 = install(sub_path_1)
    ok_(subds1.is_installed())
    ok_clean_git(sub_path_1, annex=False)
    # wasn't installed into ds:
    assert_not_in("sub", ds.get_dataset_handles())

    # add it inplace:
    added_subds = ds.install("sub", source=sub_path_1)
    ok_(added_subds.is_installed())
    ok_clean_git(sub_path_1, annex=False)
    eq_(added_subds.path, sub_path_1)
    # will not list it unless committed
    assert_not_in("sub", ds.get_dataset_handles())
    ds.remember_state("added submodule")
    # will still not list it, because without a single commit, it doesn't enter
    # the index
    assert_not_in("sub", ds.get_dataset_handles())
    # now for reals
    open(opj(added_subds.path, 'somecontent'), 'w').write('stupid')
    # next one will auto-annex the new file
    added_subds.remember_state('initial commit')
    # as the submodule never entered the index, even this one won't work
    ds.remember_state('submodule with content')
    assert_not_in("sub", ds.get_dataset_handles())
    # we need to install the submodule again in the parent
    # an actual final commit is not required
    added_subds = ds.install("sub", source=sub_path_1)
    assert_in("sub", ds.get_dataset_handles())

    # next one directly created within ds:
    sub_path_2 = opj(path, "sub2")
    # installing something without a source into a dataset at a path
    # that has no present content should not work
    assert_raises(InsufficientArgumentsError, install, ds, path=sub_path_2)


@with_tree(tree={'test.txt': 'some', 'test2.txt': 'other'})
@with_tempfile(mkdir=True)
def test_install_plain_git(src, path):
    # make plain git repo
    gr = GitRepo(src, create=True)
    gr.git_add('test.txt')
    gr.git_commit('demo')
    # now install it somewhere else
    ds = install(path=path, source=src)
    # stays plain Git repo
    ok_(isinstance(ds.repo, GitRepo))
    # now go back to original
    ds = Dataset(src)
    ok_(isinstance(ds.repo, GitRepo))
    # installing a file must fail, as we decided not to perform magical upgrades
    # GitRepo -> AnnexRepo
    assert_raises(RuntimeError, ds.install, path='test2.txt', source=opj(src, 'test2.txt'))
    # but works when forced
    ifiles = ds.install(path='test2.txt', source=opj(src, 'test2.txt'), add_data_to_git=True)
    ok_startswith(ifiles, ds.path)
    ok_(ifiles.endswith('test2.txt'))
    ok_('test2.txt' in ds.repo.get_indexed_files())


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
def test_install_dataset_from_just_source(url, path):

    with chpwd(path, mkdir=True):
        ds = install(source=url)

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_clean_git(ds.path, annex=False)

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
    # unless committed the subds should not show up in the parent
    # this is the same behavior that 'git submodule status' implements
    assert_not_in('sub', ds.get_dataset_handles())
    ds.remember_state('addsub')
    assert_in('sub', ds.get_dataset_handles())


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_subdataset(src, path):
    # get the superdataset:
    ds = install(path=path, source=src)

    # subdataset not installed:
    subds = Dataset(opj(path, 'sub1'))
    assert_false(subds.is_installed())

    # install it:
    ds.install('sub1')

    ok_(subds.is_installed())
    # Verify that it is the correct submodule installed and not
    # new repository initiated
    assert_equal(set(subds.repo.get_indexed_files()),
                 {'test.dat', 'INFO.txt', 'test-annex.dat'})

    # Now the obnoxious install an annex file within not yet
    # initialized repository!
    with swallow_outputs():  # progress bar
        ds.install(opj('sub2', 'test-annex.dat'))
    subds2 = Dataset(opj(path, 'sub2'))
    assert(subds2.is_installed())
    assert(subds2.repo.file_has_content('test-annex.dat'))
    # we shouldn't be able silently ignore attempt to provide source while
    # "installing" file under git
    assert_raises(FileInGitError, ds.install, opj('sub2', 'INFO.txt'), source="http://bogusbogus")


def test_install_list():
    raise SkipTest("TODO")


def test_install_missing_arguments():
    raise SkipTest("TODO")


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_recursive(src, path):
    ds = install(path=path, source=src, recursive=True)
    ok_(ds.is_installed())
    for sub in ds.get_dataset_handles(recursive=True):
        ok_(Dataset(opj(path, sub)).is_installed(), "Not installed: %s" % opj(path, sub))

# TODO: Is there a way to test result renderer?
#  MIH: cmdline tests have run_main() which capture the output.
