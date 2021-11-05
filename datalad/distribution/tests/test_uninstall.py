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
from glob import glob
from os.path import (
    exists,
    isdir,
)
from os.path import join as opj
from os.path import lexists
from os.path import split as psplit

from datalad.api import (
    create,
    drop,
    install,
    remove,
    uninstall,
)
from datalad.support.exceptions import IncompleteResultsError
from datalad.tests.utils import (
    assert_in,
    assert_in_results,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_result_values_cond,
    assert_status,
    create_tree,
    eq_,
    known_failure_windows,
    ok_,
    ok_file_under_git,
    skip_if_no_network,
    use_cassette,
    usecase,
    with_tempfile,
    with_testrepos,
    with_tree,
)
from datalad.utils import (
    Path,
    _path_,
    chpwd,
)

from ..dataset import Dataset


@with_tempfile()
def test_uninstall_uninstalled(path):
    ds = Dataset(path)
    assert_raises(ValueError, ds.uninstall)


@with_tempfile()
def test_clean_subds_removal(path):
    ds = Dataset(path).create()
    subds1 = ds.create('one')
    subds2 = ds.create('two')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['one', 'two'])
    assert_repo_status(ds.path)
    # now kill one
    res = ds.remove('one', check=False, result_xfm=None)
    # subds1 got uninstalled, and ds got the removal of subds1 saved
    assert_result_count(res, 1, path=subds1.path, action='uninstall', status='ok')
    assert_result_count(res, 1, path=subds1.path, action='remove', status='ok')
    assert_result_count(res, 1, path=ds.path, action='save', status='ok')
    ok_(not subds1.is_installed())
    assert_repo_status(ds.path)
    # two must remain
    eq_(ds.subdatasets(result_xfm='relpaths'), ['two'])
    # one is gone
    assert(not exists(subds1.path))
    # and now again, but this time remove something that is not installed
    ds.create('three')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['three', 'two'])
    ds.uninstall('two', check=False)
    assert_repo_status(ds.path)
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['three', 'two'])
    ok_(not subds2.is_installed())
    assert(exists(subds2.path))
    res = ds.remove('two', check=False)
    assert_in_results(
        res,
        path=str(ds.pathobj / 'two'),
        action='remove')
    assert_repo_status(ds.path)
    # subds2 was already uninstalled, now ds got the removal of subds2 saved
    assert(not exists(subds2.path))
    eq_(ds.subdatasets(result_xfm='relpaths'), ['three'])


@known_failure_windows
@with_tree({
    'deep': {
        'dir': {
            'keep': 'keep1', 'kill': 'kill1'}},
    'keep': 'keep2',
    'kill': 'kill2'})
def test_uninstall_multiple_paths(path):
    ds = Dataset(path).create(force=True)
    subds = ds.create('deep', force=True)
    subds.save(recursive=True)
    assert_repo_status(subds.path)
    # needs to be able to add a combination of staged files, modified submodule,
    # and untracked files
    ds.save(recursive=True)
    assert_repo_status(ds.path)
    # drop content of all 'kill' files
    topfile = 'kill'
    deepfile = opj('deep', 'dir', 'kill')
    # use a tuple not a list! should also work
    ds.drop((topfile, deepfile), check=False)
    assert_repo_status(ds.path)
    files_left = glob(opj(ds.path, '*', '*', '*')) + glob(opj(ds.path, '*'))
    ok_(all([f.endswith('keep') for f in files_left if exists(f) and not isdir(f)]))
    ok_(not ds.repo.file_has_content(topfile))
    ok_(not subds.repo.file_has_content(opj(*psplit(deepfile)[1:])))
    # remove handles for all 'kill' files
    ds.remove([topfile, deepfile], check=False)
    assert_repo_status(ds.path)
    files_left = glob(opj(ds.path, '*', '*', '*')) + glob(opj(ds.path, '*'))
    ok_(all([f.endswith('keep') for f in files_left if exists(f) and not isdir(f)]))
    ok_(not any([f.endswith(topfile) for f in files_left]))


@with_tempfile()
def test_careless_subdataset_uninstall(path):
    # nested datasets
    ds = Dataset(path).create()
    subds1 = ds.create('deep1')
    ds.create('deep2')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['deep1', 'deep2'])
    assert_repo_status(ds.path)
    # now we kill the sub without the parent knowing
    subds1.uninstall(check=False)
    ok_(not subds1.is_installed())
    # mountpoint exists
    ok_(exists(subds1.path))
    assert_repo_status(ds.path)
    # parent still knows the sub
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['deep1', 'deep2'])


@with_tempfile()
def test_kill(path):
    # nested datasets with load
    ds = Dataset(path).create()
    testfile = opj(ds.path, "file.dat")
    with open(testfile, 'w') as f:
        f.write("load")
    ds.save("file.dat")
    subds = ds.create('deep1')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['deep1'])
    assert_repo_status(ds.path)

    # and we fail to remove for many reasons
    # - unpushed commits
    # - a subdataset present
    # - unique annex key
    res = ds.remove(on_failure='ignore')
    assert_result_count(
        res, 1,
        status='error', path=ds.path)
    eq_(ds.remove(recursive=True, reckless='availability', result_xfm='datasets'),
        [subds, ds])
    ok_(not exists(path))


@with_tempfile()
def test_remove_recreation(path):

    # test recreation is possible and doesn't conflict with in-memory
    # remainings of the old instances
    # see issue #1311

    ds = create(path)
    ds.remove(reckless='availability')
    ds = create(path)
    assert_repo_status(ds.path)
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
    remove(dataset=subds_path)  # should remove just fine


@usecase
@skip_if_no_network
@with_tempfile(mkdir=True)
@use_cassette('test_remove_recursive_2')
def test_remove_recursive_2(tdir):
    # fails in some cases https://github.com/datalad/datalad/issues/1573
    with chpwd(tdir):
        install('///labs')
        with chpwd('labs'):
            install('tarr/face_place')
        remove(dataset='labs', recursive=True)


@with_tempfile(mkdir=True)
def test_failon_nodrop(path):
    # test to make sure that we do not wipe out data when checks are enabled
    # despite the general error behavior mode
    ds = Dataset(path).create()
    # we play with a subdataset to bypass the tests that prevent the removal
    # of top-level datasets
    sub = ds.create('sub')
    create_tree(sub.path, {'test': 'content'})
    ds.save(opj('sub', 'test'))
    assert_repo_status(ds.path)
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
    assert_repo_status(parent.path)
    nosub = create(opj(parent.path, 'nosub'))
    assert_repo_status(nosub.path)
    subreport = parent.subdatasets()
    assert_result_count(subreport, 1, path=sub.path)
    assert_result_count(subreport, 0, path=nosub.path)
    # it should be possible to uninstall the proper subdataset, even without
    # explicitly calling the uninstall methods of the parent -- things should
    # be figured out by datalad
    with chpwd(parent.path):
        # check False because revisions are not pushed
        uninstall(sub.path, check=False)
    assert not sub.is_installed()
    # no present subdatasets anymore
    subreport = parent.subdatasets()
    assert_result_count(subreport, 1)
    assert_result_count(subreport, 1, path=sub.path, state='absent')
    assert_result_count(subreport, 0, path=nosub.path)
    # but we should fail on an attempt to uninstall the non-subdataset
    with chpwd(nosub.path):
        assert_raises(RuntimeError, uninstall)


@with_tempfile(mkdir=True)
def test_drop_nocrash_absent_subds(path):
    parent = Dataset(path).create()
    sub = parent.create('sub')
    parent.uninstall('sub', check=False)
    assert_repo_status(parent.path)
    with chpwd(path):
        assert_status('notneeded', drop('.', recursive=True))


@with_tree({'one': 'one', 'two': 'two', 'three': 'three'})
def test_remove_more_than_one(path):
    ds = Dataset(path).create(force=True)
    ds.save()
    assert_repo_status(path)
    # ensure #1912 stays resolved
    ds.remove(['one', 'two'], check=False)
    assert_repo_status(path)
