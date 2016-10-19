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
from os.path import join as opj, split as psplit
from os.path import exists, lexists
from os.path import realpath
from os.path import isdir
from glob import glob

from datalad.api import uninstall
from datalad.api import install
from datalad.support.exceptions import InsufficientArgumentsError, CommandError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.tests.utils import ok_file_under_git
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.utils import chpwd
from datalad.support.external_versions import external_versions

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
def test_uninstall_nonexisting(path):
    ds = Dataset(path)
    assert_raises(ValueError, uninstall, dataset=ds)


@with_tempfile()
def test_clean_subds_removal(path):
    ds = Dataset(path).create()
    subds1 = ds.create('one')
    ds.create('two')
    ds.save(auto_add_changes=True)
    eq_(sorted(ds.get_subdatasets()), ['one', 'two'])
    ok_clean_git(ds.path)
    # now kill one
    assert_raises(ValueError, ds.uninstall, 'one', remove_handles=True,
                  remove_history=True)
    res = ds.uninstall('one', remove_handles=True, remove_history=True,
                       recursive=True)
    eq_(res, [subds1])
    ok_(not subds1.is_installed())
    ok_clean_git(ds.path)
    # two must remain
    eq_(ds.get_subdatasets(), ['two'])
    # one is gone
    assert(not exists(subds1.path))


@with_testrepos('.*basic.*', flavors=['local'])
def test_uninstall_invalid(path):
    assert_raises(InsufficientArgumentsError, uninstall)
    # makes no sense to call uninstall, but ask it to do nothing
    assert_raises(ValueError, uninstall, remove_handles=False, remove_data=False)
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

    ds = install(dst, source=src, recursive=True)[0]
    ok_(ds.is_installed())
    for subds_path in ds.get_subdatasets():
        subds = Dataset(opj(ds.path, subds_path))
        ok_(subds.is_installed())

        annexed_files = subds.repo.get_annexed_files()
        subds.repo.get(annexed_files)

        # uninstall data of subds:
        assert_raises(ValueError, ds.uninstall, path=subds_path)
        res = ds.uninstall(path=subds_path, recursive=True)
        ok_(all([f in res for f in annexed_files]))
        ok_(all([not i for i in subds.repo.file_has_content(annexed_files)]))
        # subdataset is still known
        assert_in(subds_path, ds.get_subdatasets())

    for subds_path in ds.get_subdatasets():
        # uninstall subds itself:
        assert_raises(ValueError, ds.uninstall,
                      path=subds_path, remove_handles=True, remove_history=True)
        if os.environ.get('DATALAD_TESTS_DATALADREMOTE') \
                and external_versions['git'] < '2.0.9':
            raise SkipTest("Known problem with GitPython. See "
                "https://github.com/gitpython-developers/GitPython/pull/521")
        res = ds.uninstall(path=subds_path, remove_handles=True, remove_history=True,
                           recursive=True)
        subds = Dataset(opj(ds.path, subds_path))
        eq_(res[0], subds)
        ok_(not subds.is_installed())
        ok_(not exists(subds.path))


@with_tree({
    'deep': {
        'dir': {
            'keep': 'keep1', 'kill': 'kill1'}},
    'keep': 'keep2',
    'kill': 'kill2'})
def test_uninstall_multiple_paths(path):
    ds = Dataset(path).create(force=True, save=False)
    subds = ds.create('deep', force=True, if_dirty='ignore')
    subds.add('.', recursive=True)
    ds.add('.', recursive=True)
    ds.save(auto_add_changes=True)
    ok_clean_git(ds.path)
    # drop content of all 'kill' files
    # must not work without recursive
    topfile = 'kill'
    deepfile = opj('deep', 'dir', 'kill')
    assert_raises(ValueError, ds.uninstall, [topfile, deepfile], check=False)
    # use a tuple not a list! should also work
    ds.uninstall((topfile, deepfile), recursive=True, check=False)
    ok_clean_git(ds.path)
    files_left = glob(opj(ds.path, '*', '*', '*')) + glob(opj(ds.path, '*'))
    ok_(all([f.endswith('keep') for f in files_left if exists(f) and not isdir(f)]))
    ok_(not ds.repo.file_has_content(topfile))
    ok_(not subds.repo.file_has_content(opj(*psplit(deepfile)[1:])))
    # drop handles for all 'kill' files
    ds.uninstall([topfile, deepfile], recursive=True, check=False,
                 remove_handles=True)
    ok_clean_git(ds.path)
    files_left = glob(opj(ds.path, '*', '*', '*')) + glob(opj(ds.path, '*'))
    ok_(all([f.endswith('keep') for f in files_left if exists(f) and not isdir(f)]))
    ok_(not any([f.endswith(topfile) for f in files_left]))


@with_tempfile()
def test_uninstall_dataset(path):
    ds = Dataset(path)
    ok_(not ds.is_installed())
    ds.create()
    ok_(ds.is_installed())
    ok_clean_git(ds.path)
    # would only drop data
    ds.uninstall()
    # actually same as this, for cmdline compat reasons
    ds.uninstall(path=[])
    ok_clean_git(ds.path)
    # removing all handles equal removal of entire dataset, needs safety switch
    assert_raises(ValueError, ds.uninstall, remove_handles=True)
    ds.uninstall(remove_handles=True, remove_history=True)
    # completely gone
    ok_(not ds.is_installed())
    ok_(not exists(ds.path))


@with_tree({'one': 'test', 'two': 'test'})
def test_remove_file_handle_only(path):
    ds = Dataset(path).create(force=True)
    ds.add(os.curdir)
    ok_clean_git(ds.path)
    # make sure there is any key
    ok_(len(ds.repo.get_file_key('one')))
    # both files link to the same key
    eq_(ds.repo.get_file_key('one'),
        ds.repo.get_file_key('two'))
    rpath_one = realpath(opj(ds.path, 'one'))
    eq_(rpath_one, realpath(opj(ds.path, 'two')))
    path_two = opj(ds.path, 'two')
    ok_(exists(path_two))
    # remove one handle, should not affect the other
    ds.uninstall('two', remove_data=False, remove_handles=True)
    eq_(rpath_one, realpath(opj(ds.path, 'one')))
    ok_(exists(rpath_one))
    ok_(not exists(path_two))


@with_tree({'deep': {'dir': {'test': 'testcontent'}}})
def test_uninstall_recursive(path):
    ds = Dataset(path).create(force=True, if_dirty='ignore')
    subds = ds.create('deep', force=True, if_dirty='ignore')
    # we add one file
    eq_(len(subds.add('.', if_dirty='ignore')), 1)
    # save all -> all clean
    ds.save(auto_add_changes=True, recursive=True)
    ok_clean_git(subds.path)
    ok_clean_git(ds.path)
    # now uninstall in subdataset through superdataset
    target_fname = opj('deep', 'dir', 'test')
    # sane starting point
    ok_(exists(opj(ds.path, target_fname)))
    # uninstallation fails without --recursive
    assert_raises(ValueError, ds.uninstall, target_fname)
    # doesn't have the minimum number of copies for a safe drop
    # TODO: better exception
    assert_raises(CommandError, ds.uninstall, target_fname, recursive=True)
    # this should do it
    ds.uninstall(target_fname, check=False, recursive=True)
    # link is dead
    lname = opj(ds.path, target_fname)
    ok_(not exists(lname))
    # entire hierarchy saved
    ok_clean_git(subds.path)
    ok_clean_git(ds.path)
    # now same with actual handle removal
    assert_raises(ValueError, ds.uninstall, target_fname, remove_handles=True)
    # content is dropped already, so no checks in place anyway
    ds.uninstall(target_fname, check=True, remove_handles=True, recursive=True)
    ok_(not exists(lname) and not lexists(lname))
    ok_clean_git(subds.path)
    ok_clean_git(ds.path)


@with_tempfile()
def test_remove_dataset_hierarchy(path):
    ds = Dataset(path).create()
    ds.create('deep')
    ds.save(auto_add_changes=True)
    ok_clean_git(ds.path)
    # fail on missing `remove_handles`, always needs to come with `remove_handles`
    assert_raises(ValueError, ds.uninstall, remove_history=True)
    # fail on missing --recursive because subdataset is present
    assert_raises(ValueError, ds.uninstall, remove_handles=True, remove_history=True)
    ds.uninstall(remove_history=True, remove_handles=True, recursive=True)
    # completely gone
    ok_(not ds.is_installed())
    ok_(not exists(ds.path))


@with_tempfile()
def test_careless_subdataset_uninstall(path):
    # nested datasets
    ds = Dataset(path).create()
    subds1 = ds.create('deep1')
    ds.create('deep2')
    eq_(sorted(ds.get_subdatasets()), ['deep1', 'deep2'])
    ok_clean_git(ds.path)
    # now we kill the sub without the parent knowing
    subds1.uninstall(remove_history=True, remove_handles=True)
    ok_(not exists(subds1.path))
    ok_(ds.repo.dirty)
    # parent still knows the sub
    eq_(sorted(ds.get_subdatasets()), ['deep1', 'deep2'])
    # save the parent later on
    ds.save(auto_add_changes=True)
    # subds still gone
    # subdataset appearance is normalized to an empty directory
    ok_(exists(subds1.path))
    # parent still knows the sub
    eq_(ds.get_subdatasets(), ['deep1', 'deep2'])
    # and they lived happily ever after
    ok_clean_git(ds.path)


@with_tempfile()
def test_kill(path):
    # nested datasets with load
    ds = Dataset(path).create()
    with open(opj(ds.path, "file.dat"), 'w') as f:
        f.write("load")
    ds.repo.add("file.dat")
    subds1 = ds.create('deep1')
    eq_(sorted(ds.get_subdatasets()), ['deep1'])
    ok_clean_git(ds.path)

    # and we fail to uninstall since content can't be dropped
    assert_raises(CommandError, ds.uninstall)
    eq_(ds.uninstall(kill=True), [path])
    ok_(not exists(path))
