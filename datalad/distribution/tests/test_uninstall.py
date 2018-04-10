# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test uninstall action

"""

from datalad.tests.utils import known_failure_v6
from datalad.tests.utils import known_failure_direct_mode


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
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import IncompleteResultsError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_result_values_cond
from datalad.tests.utils import ok_file_under_git
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import create_tree
from datalad.tests.utils import skip_if_no_network
from datalad.tests.utils import use_cassette
from datalad.tests.utils import usecase
from datalad.utils import chpwd
from datalad.utils import _path_
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
                assert_status(
                    ('error', 'impossible'),
                    uninstall(path=target, on_failure='ignore'))


@with_tempfile()
def test_uninstall_uninstalled(path):
    # goal oriented error reporting. here:
    # nothing installed, any removal was already a success before it started
    ds = Dataset(path)
    assert_status('error', ds.drop(on_failure="ignore"))
    assert_status('error', ds.uninstall(on_failure='ignore'))
    assert_status('notneeded', ds.remove())


@with_tempfile()
@known_failure_direct_mode  #FIXME
def test_clean_subds_removal(path):
    ds = Dataset(path).create()
    subds1 = ds.create('one')
    subds2 = ds.create('two')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['one', 'two'])
    ok_clean_git(ds.path)
    # now kill one
    res = ds.remove('one', result_xfm=None)
    # subds1 got uninstalled, and ds got the removal of subds1 saved
    assert_result_count(res, 1, path=subds1.path, action='uninstall', status='ok')
    assert_result_count(res, 1, path=subds1.path, action='remove', status='ok')
    assert_result_count(res, 1, path=ds.path, action='save', status='ok')
    ok_(not subds1.is_installed())
    ok_clean_git(ds.path)
    # two must remain
    eq_(ds.subdatasets(result_xfm='relpaths'), ['two'])
    # one is gone
    assert(not exists(subds1.path))
    # and now again, but this time remove something that is not installed
    ds.create('three')
    ds.save()
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['three', 'two'])
    ds.uninstall('two')
    ok_clean_git(ds.path)
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['three', 'two'])
    ok_(not subds2.is_installed())
    assert(exists(subds2.path))
    res = ds.remove('two', result_xfm='datasets')
    ok_clean_git(ds.path)
    # subds2 was already uninstalled, now ds got the removal of subds2 saved
    assert(not exists(subds2.path))
    eq_(ds.subdatasets(result_xfm='relpaths'), ['three'])
    eq_(res, [subds2, ds])


@with_testrepos('.*basic.*', flavors=['clone'])
def test_uninstall_invalid(path):
    ds = Dataset(path).create(force=True)
    for method in (uninstall, remove, drop):
        assert_raises(InsufficientArgumentsError, method)
        # refuse to touch stuff outside the dataset
        assert_status('error', method(dataset=ds, path='..', on_failure='ignore'))
        # same if it doesn't exist, for consistency
        assert_status('error', method(dataset=ds, path='../madeupnonexist', on_failure='ignore'))


@with_testrepos('basic_annex', flavors=['clone'])
def test_uninstall_annex_file(path):
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_file_under_git(ds.repo.path, 'test-annex.dat', annexed=True)
    ds.repo.get('test-annex.dat')
    ok_(ds.repo.file_has_content('test-annex.dat'))

    # remove file's content:
    res = ds.drop(path='test-annex.dat', result_xfm='paths')
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


@known_failure_v6  # FIXME: git files end up in annex, therefore drop result is different
@with_testrepos('.*basic.*', flavors=['clone'])
def test_uninstall_git_file(path):
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_(exists(opj(path, 'INFO.txt')))
    ok_file_under_git(ds.repo.path, 'INFO.txt')

    # drop file in Git in an annex repo
    # regardless of the type of repo this is 'notneeded'...
    # it is less about education that about "can we
    # we get the content back?", and for a file in Git we can
    assert_result_count(
        ds.drop(path='INFO.txt'),
        1,
        status='notneeded',
        message="no annex'ed content")

    res = ds.uninstall(path="INFO.txt", on_failure='ignore')
    assert_result_count(
        res, 1,
        status='impossible',
        message='can only uninstall datasets (consider the `drop` command)')

    # remove the file:
    res = ds.remove(path='INFO.txt', result_xfm='paths',
                    result_filter=lambda x: x['action'] == 'remove')
    assert_raises(AssertionError, ok_file_under_git, ds.repo.path, 'INFO.txt')
    ok_(not exists(opj(path, 'INFO.txt')))
    eq_(res, ['INFO.txt'])


@known_failure_v6  #FIXME  Note: Failure seems to somehow be depend on PY2/PY3
@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_uninstall_subdataset(src, dst):

    ds = install(dst, source=src, recursive=True)
    ok_(ds.is_installed())
    known_subdss = ds.subdatasets(result_xfm='datasets')
    for subds in ds.subdatasets(result_xfm='datasets'):
        ok_(subds.is_installed())

        annexed_files = subds.repo.get_annexed_files()
        subds.repo.get(annexed_files)

        # drop data of subds:
        res = ds.drop(path=subds.path, result_xfm='paths')

        ok_(all([opj(subds.path, f) in res for f in annexed_files]))
        ok_(all([not i for i in subds.repo.file_has_content(annexed_files)]))
        # subdataset is still known
        assert_in(subds.path, ds.subdatasets(result_xfm='paths'))

    eq_(ds.subdatasets(result_xfm='datasets'), known_subdss)

    for subds in ds.subdatasets(result_xfm='datasets'):
        # uninstall subds itself:
        if os.environ.get('DATALAD_TESTS_DATALADREMOTE') \
                and external_versions['git'] < '2.0.9':
            raise SkipTest(
                "Known problem with GitPython. See "
                "https://github.com/gitpython-developers/GitPython/pull/521")
        res = ds.uninstall(path=subds.path, result_xfm='datasets')
        eq_(res[0], subds)
        ok_(not subds.is_installed())
        # just a deinit must not remove the subdataset registration
        eq_(ds.subdatasets(result_xfm='datasets'), known_subdss)
        # mountpoint of subdataset should still be there
        ok_(exists(subds.path))


@with_tree({
    'deep': {
        'dir': {
            'keep': 'keep1', 'kill': 'kill1'}},
    'keep': 'keep2',
    'kill': 'kill2'})
@known_failure_direct_mode  #FIXME
def test_uninstall_multiple_paths(path):
    ds = Dataset(path).create(force=True, save=False)
    subds = ds.create('deep', force=True)
    subds.add('.', recursive=True)
    ok_clean_git(subds.path)
    # needs to be able to add a combination of staged files, modified submodule,
    # and untracked files
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
    assert_raises(IncompleteResultsError, ds.uninstall)
    ds.remove()
    # completely gone
    ok_(not ds.is_installed())
    ok_(not exists(ds.path))


@with_tree({'one': 'test', 'two': 'test', 'three': 'test2'})
@known_failure_direct_mode  #FIXME
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
    ds.remove('two', check=False, message="custom msg")
    eq_(ds.repo.repo.head.commit.message.rstrip(), "custom msg")
    eq_(rpath_one, realpath(opj(ds.path, 'one')))
    ok_(exists(rpath_one))
    ok_(not exists(path_two))
    # remove file without specifying the dataset -- shouldn't fail
    with chpwd(path):
        remove('one', check=False)
        ok_(not exists("one"))
    # and we should be able to remove without saving
    ds.remove('three', check=False, save=False)
    ok_(ds.repo.is_dirty())


@with_tree({'deep': {'dir': {'test': 'testcontent'}}})
@known_failure_direct_mode  #FIXME
def test_uninstall_recursive(path):
    ds = Dataset(path).create(force=True)
    subds = ds.create('deep', force=True)
    # we add one file, but we get a response for the requested
    # directory too
    res = subds.add('.')
    assert_result_count(res, 1, action='add', status='ok', type='file')
    assert_result_count(res, 1, action='save', status='ok', type='dataset')
    # save all -> all clean
    ds.save(recursive=True)
    ok_clean_git(subds.path)
    ok_clean_git(ds.path)
    # now uninstall in subdataset through superdataset
    target_fname = opj('deep', 'dir', 'test')
    # sane starting point
    ok_(exists(opj(ds.path, target_fname)))
    # doesn't have the minimum number of copies for a safe drop
    res = ds.drop(target_fname, recursive=True, on_failure='ignore')
    assert_status('error', res)
    assert_result_values_cond(
        res, 'message',
        lambda x: "configured minimum number of copies not found" in x or
        "Could only verify the existence of 0 out of 1 necessary copies" in x
    )

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
    ok_clean_git(ds.path)
    # fail on missing --recursive because subdataset is present
    assert_raises(IncompleteResultsError, ds.remove)
    ok_clean_git(ds.path)
    ds.remove(recursive=True)
    # completely gone
    ok_(not ds.is_installed())
    ok_(not exists(ds.path))
    # now do it again, but without a reference dataset
    ds = Dataset(path).create()
    ds.create('deep')
    ok_clean_git(ds.path)
    remove(ds.path, recursive=True)
    # completely gone
    ok_(not ds.is_installed())
    ok_(not exists(ds.path))


@with_tempfile()
@known_failure_direct_mode  #FIXME
def test_careless_subdataset_uninstall(path):
    # nested datasets
    ds = Dataset(path).create()
    subds1 = ds.create('deep1')
    ds.create('deep2')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['deep1', 'deep2'])
    ok_clean_git(ds.path)
    # now we kill the sub without the parent knowing
    subds1.uninstall()
    ok_(not subds1.is_installed())
    # mountpoint exists
    ok_(exists(subds1.path))
    ok_clean_git(ds.path)
    # parent still knows the sub
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['deep1', 'deep2'])


@with_tempfile()
@known_failure_direct_mode  #FIXME
def test_kill(path):
    # nested datasets with load
    ds = Dataset(path).create()
    testfile = opj(ds.path, "file.dat")
    with open(testfile, 'w') as f:
        f.write("load")
    ds.add("file.dat")
    subds = ds.create('deep1')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['deep1'])
    ok_clean_git(ds.path)

    # and we fail to remove since content can't be dropped
    res = ds.remove(on_failure='ignore')
    assert_result_count(
        res, 1,
        status='error', path=testfile)
    # Following two assertions on message are relying on the actual error.
    # We have a second result with status 'impossible' for the ds, that we need
    # to filter out for those assertions:
    err_result = [r for r in res if r['status'] == 'error'][0]
    assert_result_values_cond(
        [err_result], 'message',
        lambda x: "configured minimum number of copies not found" in x or
        "Could only verify the existence of 0 out of 1 necessary copies" in x
    )
    eq_(ds.remove(recursive=True, check=False, result_xfm='datasets'),
        [subds, ds])
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


@with_tempfile()
def test_no_interaction_with_untracked_content(path):
    # extracted from what was a metadata test originally
    ds = Dataset(opj(path, 'origin')).create(force=True)
    create_tree(ds.path, {'sub': {'subsub': {'dat': 'lots of data'}}})
    subds = ds.create('sub', force=True)
    subds.remove(opj('.datalad', 'config'), if_dirty='ignore')
    ok_(not exists(opj(subds.path, '.datalad', 'config')))
    # this will only work, if `remove` didn't do anything stupid and
    # caused all content to be saved
    subds.create('subsub', force=True)


@with_tempfile()
def test_remove_nowhining(path):
    # when removing a dataset under a dataset (but not a subdataset)
    # should not provide a meaningless message that something was not right
    ds = create(path)
    # just install/clone inside of it
    subds_path = _path_(path, 'subds')
    install(subds_path, source=path)
    remove(subds_path)  # should remove just fine


@usecase
@known_failure_v6  # https://github.com/datalad/datalad/pull/2391#issuecomment-379414293
@skip_if_no_network
@with_tempfile(mkdir=True)
@use_cassette('test_remove_recursive_2')
def test_remove_recursive_2(tdir):
    # fails in some cases https://github.com/datalad/datalad/issues/1573
    with chpwd(tdir):
        install('///labs')
        install('labs/tarr/face_place')
        remove('labs', recursive=True)


@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_failon_nodrop(path):
    # test to make sure that we do not wipe out data when checks are enabled
    # despite the general error behavior mode
    ds = Dataset(path).create()
    # we play with a subdataset to bypass the tests that prevent the removal
    # of top-level datasets
    sub = ds.create('sub')
    create_tree(sub.path, {'test': 'content'})
    ds.add(opj('sub', 'test'))
    ok_clean_git(ds.path)
    eq_(['test'], sub.repo.get_annexed_files(with_content_only=True))
    # we put one file into the dataset's annex, no redundant copies
    # neither uninstall nor remove should work
    res = ds.uninstall('sub', check=True, on_failure='ignore')
    assert_status(['error', 'impossible'], res)
    eq_(['test'], sub.repo.get_annexed_files(with_content_only=True))
    # same with remove
    res = ds.remove('sub', check=True, on_failure='ignore')
    assert_status(['error', 'impossible'], res)
    eq_(['test'], sub.repo.get_annexed_files(with_content_only=True))


@with_tempfile(mkdir=True)
def test_uninstall_without_super(path):
    # a parent dataset with a proper subdataset, and another dataset that
    # is just placed underneath the parent, but not an actual subdataset
    parent = Dataset(path).create()
    sub = parent.create('sub')
    ok_clean_git(parent.path)
    nosub = create(opj(parent.path, 'nosub'))
    ok_clean_git(nosub.path)
    subreport = parent.subdatasets()
    assert_result_count(subreport, 1, path=sub.path)
    assert_result_count(subreport, 0, path=nosub.path)
    # it should be possible to uninstall the proper subdataset, even without
    # explicitly calling the uninstall methods of the parent -- things should
    # be figured out by datalad
    uninstall(sub.path)
    assert not sub.is_installed()
    # no present subdatasets anymore
    subreport = parent.subdatasets()
    assert_result_count(subreport, 1)
    assert_result_count(subreport, 1, path=sub.path, state='absent')
    assert_result_count(subreport, 0, path=nosub.path)
    # but we should fail on an attempt to uninstall the non-subdataset
    res = uninstall(nosub.path, on_failure='ignore')
    assert_result_count(
        res, 1, path=nosub.path, status='error',
        message="will not uninstall top-level dataset (consider `remove` command)")


@with_tempfile(mkdir=True)
def test_drop_nocrash_absent_subds(path):
    parent = Dataset(path).create()
    sub = parent.create('sub')
    parent.uninstall('sub')
    ok_clean_git(parent.path)
    with chpwd(path):
        assert_status('notneeded', drop('.', recursive=True))


@with_tree({'one': 'one', 'two': 'two', 'three': 'three'})
def test_remove_more_than_one(path):
    ds = Dataset(path).create(force=True)
    ds.add('.')
    ok_clean_git(path)
    # ensure #1912 stays resolved
    ds.remove(['one', 'two'], check=False)
    ok_clean_git(path)
