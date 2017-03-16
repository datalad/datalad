# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test uninstall action

"""

import logging
import os
from os.path import join as opj, split as psplit
from os.path import exists, lexists
from os.path import realpath
from os.path import isdir
from glob import glob

from datalad.api import uninstall
from datalad.api import drop
from datalad.api import remove
from datalad.api import install
from datalad.api import create
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
from datalad.utils import swallow_logs

from ..dataset import Dataset


@with_tempfile()
def test_safetynet(path):
    ds = Dataset(path).create()
    os.makedirs(opj(ds.path, 'deep', 'down'))
    for p in (ds.path, opj(ds.path, 'deep'), opj(ds.path, 'deep', 'down')):
        with chpwd(p):
            # will never remove PWD, or anything outside the dataset
            for target in (ds.path, os.curdir, os.pardir, opj(os.pardir, os.pardir)):
                assert_raises(ValueError, uninstall, path=target)


@with_tempfile()
def test_uninstall_uninstalled(path):
    # goal oriented error reporting. here:
    # nothing installed, any removal was already a success before it started
    ds = Dataset(path)
    eq_(ds.uninstall(), [])
    eq_(ds.drop(), [])
    eq_(ds.remove(), [])


@with_tempfile()
def test_clean_subds_removal(path):
    ds = Dataset(path).create()
    subds1 = ds.create('one')
    subds2 = ds.create('two')
    eq_(sorted(ds.get_subdatasets()), ['one', 'two'])
    ok_clean_git(ds.path)
    # now kill one
    res = ds.remove('one')
    eq_(res, [subds1])
    ok_(not subds1.is_installed())
    ok_clean_git(ds.path)
    # two must remain
    eq_(ds.get_subdatasets(), ['two'])
    # one is gone
    assert(not exists(subds1.path))
    # and now again, but this time remove something that is not installed
    ds.create('three')
    ds.save(all_updated=True)
    eq_(sorted(ds.get_subdatasets()), ['three', 'two'])
    ds.uninstall('two')
    ok_clean_git(ds.path)
    eq_(sorted(ds.get_subdatasets()), ['three', 'two'])
    ok_(not subds2.is_installed())
    assert(exists(subds2.path))
    res = ds.remove('two')
    ok_clean_git(ds.path)
    eq_(res, [subds2])
    eq_(ds.get_subdatasets(), ['three'])
    #import pdb; pdb.set_trace()
    assert(not exists(subds2.path))


@with_testrepos('.*basic.*', flavors=['clone'])
def test_uninstall_invalid(path):
    ds = Dataset(path).create(force=True)
    for method in (uninstall, remove, drop):
        assert_raises(InsufficientArgumentsError, method)
        # refuse to touch stuff outside the dataset
        assert_raises(ValueError, method, dataset=ds, path='..')
        # but it is only an error when there is actually something there
        eq_(method(dataset=ds, path='../madeupnonexist'), [])


@with_testrepos('basic_annex', flavors=['clone'])
def test_uninstall_annex_file(path):
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_file_under_git(ds.repo.path, 'test-annex.dat', annexed=True)
    ds.repo.get('test-annex.dat')
    ok_(ds.repo.file_has_content('test-annex.dat'))

    # remove file's content:
    res = ds.drop(path='test-annex.dat')
    # test it happened:
    ok_(not ds.repo.file_has_content('test-annex.dat'))
    ok_file_under_git(ds.repo.path, 'test-annex.dat', annexed=True)
    # test result:
    eq_(res, [opj(ds.path, 'test-annex.dat')])

    ds.repo.get('test-annex.dat')

    # remove file:
    ds.remove(path='test-annex.dat')
    assert_raises(AssertionError, ok_file_under_git, ds.repo.path, 'test-annex.dat',
                  annexed=True)
    assert_raises(AssertionError, ok_file_under_git, ds.repo.path, 'test-annex.dat',
                  annexed=False)
    ok_(not exists(opj(path, 'test-annex.dat')))


@with_testrepos('.*basic.*', flavors=['clone'])
def test_uninstall_git_file(path):
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_(exists(opj(path, 'INFO.txt')))
    ok_file_under_git(ds.repo.path, 'INFO.txt')

    if not hasattr(ds.repo, 'drop'):
        # nothing can be dropped in a plain GitRepo
        eq_([], ds.drop(path='INFO.txt'))

    with swallow_logs(new_level=logging.ERROR) as cml:
        assert_raises(ValueError, ds.uninstall, path="INFO.txt")
        assert_in("will not act on files", cml.out)

    # uninstall removes the file:
    res = ds.remove(path='INFO.txt')
    assert_raises(AssertionError, ok_file_under_git, ds.repo.path, 'INFO.txt')
    ok_(not exists(opj(path, 'INFO.txt')))
    eq_(res, ['INFO.txt'])


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_uninstall_subdataset(src, dst):

    ds = install(dst, source=src, recursive=True)[0]
    ok_(ds.is_installed())
    known_subdss = ds.get_subdatasets()
    for subds_path in ds.get_subdatasets():
        subds = Dataset(opj(ds.path, subds_path))
        ok_(subds.is_installed())

        annexed_files = subds.repo.get_annexed_files()
        subds.repo.get(annexed_files)

        # drop data of subds:
        res = ds.drop(path=subds_path)

        ok_(all([opj(subds.path, f) in res for f in annexed_files]))
        ok_(all([not i for i in subds.repo.file_has_content(annexed_files)]))
        # subdataset is still known
        assert_in(subds_path, ds.get_subdatasets())

    eq_(ds.get_subdatasets(), known_subdss)

    for subds_path in ds.get_subdatasets():
        # uninstall subds itself:
        if os.environ.get('DATALAD_TESTS_DATALADREMOTE') \
                and external_versions['git'] < '2.0.9':
            raise SkipTest(
                "Known problem with GitPython. See "
                "https://github.com/gitpython-developers/GitPython/pull/521")
        res = ds.uninstall(path=subds_path)
        subds = Dataset(opj(ds.path, subds_path))
        eq_(res[0], subds)
        ok_(not subds.is_installed())
        # just a deinit must not remove the subdataset registration
        eq_(ds.get_subdatasets(), known_subdss)
        # mountpoint of subdataset should still be there
        ok_(exists(subds.path))


@with_tree({
    'deep': {
        'dir': {
            'keep': 'keep1', 'kill': 'kill1'}},
    'keep': 'keep2',
    'kill': 'kill2'})
def test_uninstall_multiple_paths(path):
    ds = Dataset(path).create(force=True, save=False)
    subds = ds.create('deep', force=True)
    subds.add('.', recursive=True)
    ds.add('.', recursive=True)
    ok_clean_git(ds.path)
    # drop content of all 'kill' files
    topfile = 'kill'
    deepfile = opj('deep', 'dir', 'kill')
    # use a tuple not a list! should also work
    ds.drop((topfile, deepfile), check=False)
    ok_clean_git(ds.path)
    files_left = glob(opj(ds.path, '*', '*', '*')) + glob(opj(ds.path, '*'))
    ok_(all([f.endswith('keep') for f in files_left if exists(f) and not isdir(f)]))
    ok_(not ds.repo.file_has_content(topfile))
    ok_(not subds.repo.file_has_content(opj(*psplit(deepfile)[1:])))
    # remove handles for all 'kill' files
    ds.remove([topfile, deepfile], check=False)
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
    ds.drop()
    # actually same as this, for cmdline compat reasons
    ds.drop(path=[])
    ok_clean_git(ds.path)
    # removing entire dataset, uninstall will refuse to act on top-level
    # datasets
    assert_raises(ValueError, ds.uninstall)
    ds.remove()
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
    ds.remove('two', check=False)
    eq_(rpath_one, realpath(opj(ds.path, 'one')))
    ok_(exists(rpath_one))
    ok_(not exists(path_two))


@with_tree({'deep': {'dir': {'test': 'testcontent'}}})
def test_uninstall_recursive(path):
    ds = Dataset(path).create(force=True)
    subds = ds.create('deep', force=True)
    # we add one file
    eq_(len(subds.add('.')), 1)
    # save all -> all clean
    ds.save(all_updated=True, recursive=True)
    ok_clean_git(subds.path)
    ok_clean_git(ds.path)
    # now uninstall in subdataset through superdataset
    target_fname = opj('deep', 'dir', 'test')
    # sane starting point
    ok_(exists(opj(ds.path, target_fname)))
    # doesn't have the minimum number of copies for a safe drop
    # TODO: better exception
    assert_raises(CommandError, ds.drop, target_fname, recursive=True)
    # this should do it
    ds.drop(target_fname, check=False, recursive=True)
    # link is dead
    lname = opj(ds.path, target_fname)
    ok_(not exists(lname))
    # entire hierarchy saved
    ok_clean_git(subds.path)
    ok_clean_git(ds.path)
    # now same with actual handle removal
    # content is dropped already, so no checks in place anyway
    ds.remove(target_fname, check=True, recursive=True)
    ok_(not exists(lname) and not lexists(lname))
    ok_clean_git(subds.path)
    ok_clean_git(ds.path)


@with_tempfile()
def test_remove_dataset_hierarchy(path):
    ds = Dataset(path).create()
    ds.create('deep')
    ds.save(all_updated=True)
    ok_clean_git(ds.path)
    # fail on missing --recursive because subdataset is present
    assert_raises(ValueError, ds.remove)
    ok_clean_git(ds.path)
    ds.remove(recursive=True)
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
    subds1.uninstall()
    ok_(not subds1.is_installed())
    # mountpoint exists
    ok_(exists(subds1.path))
    ok_clean_git(ds.path)
    # parent still knows the sub
    eq_(sorted(ds.get_subdatasets()), ['deep1', 'deep2'])


@with_tempfile()
def test_kill(path):
    # nested datasets with load
    ds = Dataset(path).create()
    with open(opj(ds.path, "file.dat"), 'w') as f:
        f.write("load")
    ds.add("file.dat")
    subds = ds.create('deep1')
    eq_(sorted(ds.get_subdatasets()), ['deep1'])
    ok_clean_git(ds.path)

    # and we fail to remove since content can't be dropped
    assert_raises(CommandError, ds.remove)
    eq_(ds.remove(recursive=True, check=False), [subds, ds])
    ok_(not exists(path))


@with_tempfile()
def test_remove_recreation(path):

    # test recreation is possible and doesn't conflict with in-memory
    # remainings of the old instances
    # see issue #1311

    ds = create(path)
    ds.remove()
    ds = create(path)
    ok_clean_git(ds.path)
    ok_(ds.is_installed())
