# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test uninstall action

"""

import os
from os.path import join as opj
from os.path import exists

from datalad.api import uninstall
from datalad.api import install
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.tests.utils import ok_file_under_git
from datalad.tests.utils import with_tempfile
from datalad.utils import chpwd

from ..dataset import Dataset


@with_tempfile()
def test_safetynet(path):
    ds = Dataset(path).create()
    os.makedirs(opj(ds.path, 'deep', 'down'))
    for p in (ds.path, opj(ds.path, 'deep'), opj(ds.path, 'deep', 'down')):
        with chpwd(p):
            # will never remove PWD, or anything outside the dataset
            for target in (ds.path, os.curdir, os.pardir, opj(os.pardir, os.pardir)):
                assert_raises(ValueError, uninstall, path=target, remove_handles=True)


@with_tempfile()
def test_clean_subds_removal(path):
    ds = Dataset(path).create()
    ds.create_subdataset('one')
    ds.create_subdataset('two')
    ds.save(auto_add_changes=True)
    eq_(sorted(ds.get_subdatasets()), ['one', 'two'])
    # now kill one
    ds.uninstall('one', remove_handles=True, remove_history=True)
    # TODO: save should happen inside!!
    ds.save(auto_add_changes=True)
    # two must remain
    eq_(ds.get_subdatasets(), ['two'])


@with_testrepos('.*basic.*', flavors=['local'])
def test_uninstall_invalid(path):
    assert_raises(InsufficientArgumentsError, uninstall)
    ds = Dataset(path)
    # TODO make these two cases uniform
    if hasattr(ds.repo, 'drop'):
        assert_raises(Exception, uninstall, dataset=ds, path='not_existent')
    else:
        eq_(uninstall(dataset=ds, path='not_existent'), [])


@with_testrepos('basic_annex', flavors=['clone'])
def test_uninstall_annex_file(path):
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_file_under_git(path, 'test-annex.dat', annexed=True)
    ds.repo.get('test-annex.dat')
    ok_(ds.repo.file_has_content('test-annex.dat'))

    # remove file's content:
    res = ds.uninstall(path='test-annex.dat')
    # test it happened:
    ok_(not ds.repo.file_has_content('test-annex.dat'))
    ok_file_under_git(path, 'test-annex.dat', annexed=True)
    # test result:
    eq_(res, ['test-annex.dat'])

    ds.repo.get('test-annex.dat')

    # remove file:
    ds.uninstall(path='test-annex.dat', remove_handles=True)
    assert_raises(AssertionError, ok_file_under_git, path, 'test-annex.dat',
                  annexed=True)
    assert_raises(AssertionError, ok_file_under_git, path, 'test-annex.dat',
                  annexed=False)
    ok_(not exists(opj(path, 'test-annex.dat')))


@with_testrepos('.*basic.*', flavors=['clone'])
def test_uninstall_git_file(path):
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_(exists(opj(path, 'INFO.txt')))
    ok_file_under_git(path, 'INFO.txt')

    # uninstalling data only doesn't make sense:
    # this will only get a warning now
    #assert_raises(ValueError, ds.uninstall, path='INFO.txt', data_only=True)

    # uninstall removes the file:
    res = ds.uninstall(path='INFO.txt', remove_handles=True)
    assert_raises(AssertionError, ok_file_under_git, path, 'INFO.txt')
    ok_(not exists(opj(path, 'INFO.txt')))
    eq_(res, ['INFO.txt'])


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_uninstall_subdataset(src, dst):

    ds = install(path=dst, source=src, recursive=True)
    ok_(ds.is_installed())
    for subds_path in ds.get_subdatasets():
        subds = Dataset(opj(ds.path, subds_path))
        ok_(subds.is_installed())

        annexed_files = subds.repo.get_annexed_files()
        subds.repo.get(annexed_files)

        # uninstall data of subds:
        res = ds.uninstall(path=subds_path)
        ok_(all([f in res for f in annexed_files]))
        ok_(all([not i for i in subds.repo.file_has_content(annexed_files)]))
        # subdataset is still known
        assert_in(subds_path, ds.get_subdatasets())

    for subds_path in ds.get_subdatasets():
        # uninstall subds itself:
        res = ds.uninstall(path=subds_path, remove_handles=True, remove_history=True)
        subds = Dataset(opj(ds.path, subds_path))
        eq_(res[0], subds)
        ok_(not subds.is_installed())
        ok_(not exists(subds.path))


def test_uninstall_multiple_paths():
    raise SkipTest("TODO")


def test_uninstall_dataset():
    raise SkipTest("TODO")


def test_uninstall_recursive():
    raise SkipTest("TODO")
