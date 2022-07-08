# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test remove command"""

import os.path as op

from datalad.api import (
    clone,
    remove,
)
from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_not_in_results,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    chpwd,
    create_tree,
    eq_,
    get_deeply_nested_structure,
    nok_,
    ok_,
    with_tempfile,
    with_tree,
)


@with_tempfile
def test_remove(path=None):
    # see docstring for test data structure
    ds = get_deeply_nested_structure(path)
    gitfile = op.join("subdir", "git_file.txt")

    ok_((ds.pathobj / gitfile).exists())
    res = ds.remove(gitfile, drop='all')
    assert_result_count(res, 3)
    # git file needs no dropping
    assert_in_results(
        res,
        action='drop',
        path=str(ds.pathobj / gitfile),
        status='notneeded',
        type='file',
    )
    # removed from working tree
    assert_in_results(
        res,
        action='remove',
        path=str(ds.pathobj / gitfile),
        status='ok',
        type='file',
    )
    # saved removal in dataset
    assert_in_results(
        res,
        action='save',
        path=ds.path,
        type='dataset',
        status='ok',
    )
    nok_((ds.pathobj / gitfile).exists())

    # now same for an annexed files
    annexedfile = op.join("subdir", "annexed_file.txt")
    # drop failure prevents removal
    res = ds.remove(annexedfile, drop='all', on_failure='ignore')
    assert_result_count(res, 1)
    assert_in_results(res, status='error', action='drop',
                      path=str(ds.pathobj / annexedfile))
    ok_((ds.pathobj / annexedfile).exists())

    # now remove the file, but actually not drop the underlying
    # key -- hence no availability loss -- default mode of operation
    # remember the key
    key = ds.repo.get_file_annexinfo(annexedfile)['key']
    res = ds.remove(annexedfile, drop='datasets',
                    message="custom msg",
                    on_failure='ignore')
    # removal and dataset save
    assert_result_count(res, 2)
    eq_(
        ds.repo.format_commit(
            "%B",
            ds.repo.get_corresponding_branch()).rstrip(),
        "custom msg")
    assert_in_results(res, action='remove', status='ok',
                      path=str(ds.pathobj / annexedfile))
    assert_not_in_results(res, action='drop')
    nok_((ds.pathobj / annexedfile).exists())
    res = ds.repo.call_annex_records(['whereis', '--key', key, '--json'])
    assert_in_results(res, key=key, success=True)

    # now remove entire directory
    res = ds.remove('subdir', on_failure='ignore')
    assert_in_results(res, status='impossible', state='untracked')
    ok_((ds.pathobj / 'subdir').exists())

    ds.save('subdir')
    res = ds.remove('subdir', on_failure='ignore')
    assert_in_results(res, status='ok', action='remove')
    assert_in_results(res, status='ok', action='save', type='dataset')
    nok_((ds.pathobj / 'subdir').exists())

    # now remove an entire subdataset
    # prep: make clean
    rmdspath = ds.pathobj / 'subds_modified' / 'subds_lvl1_modified'
    ds.save(rmdspath, recursive=True)
    res = ds.remove(rmdspath, on_failure='ignore')
    # unique dataset, with unique keys -- must fail
    assert_in_results(res, status='error', action='uninstall', path=str(rmdspath))

    # go reckless
    assert_in(str(rmdspath),
              ds.subdatasets(path='subds_modified',
                             recursive=True,
                             result_xfm='paths',
                             result_renderer='disabled'))
    res = ds.remove(rmdspath, reckless='availability', on_failure='ignore')
    assert_status('ok', res)
    assert_in_results(res, action='uninstall', path=str(rmdspath))
    assert_in_results(res, action='remove', path=str(rmdspath))
    nok_(rmdspath.exists())
    # properly unlinked
    assert_not_in(str(rmdspath),
                  ds.subdatasets(path='subds_modified',
                                 recursive=True,
                                 result_xfm='paths',
                                 result_renderer='disabled'))

    # lastly, remove an uninstalled subdataset
    # we save all to be able to check whether removal was committed and
    # the ds is clean at the end
    ds.save()
    # uninstall, we don't care about the existing modifications here
    res = ds.drop('subds_modified', what='all',
                  reckless='kill', recursive=True)
    # even remove the empty mount-point, such that is is invisible on the
    # file system
    (ds.pathobj / 'subds_modified').rmdir()
    res = ds.remove('subds_modified', on_failure='ignore')
    assert_in_results(
        res, action='remove', path=str(ds.pathobj / 'subds_modified'))
    # removal was committed
    assert_repo_status(ds.path)

    # and really finally, removing top-level is just a drop
    res = ds.remove(reckless='kill')
    assert_in_results(res, action='uninstall', path=ds.path, status='ok')
    nok_(ds.is_installed())


@with_tempfile
def test_remove_subdataset_nomethod(path=None):
    ds = Dataset(path).create()
    ds.create('subds')
    with chpwd(path):
        # fails due to unique state
        res = remove('subds', on_failure='ignore')
        assert_in_results(res, action='uninstall', status='error', type='dataset')
        res = remove('subds', reckless='availability', on_failure='ignore')
        assert_in_results(res, action='uninstall', status='ok', type='dataset')
        assert_in_results(res, action='remove', status='ok')
        assert_in_results(res, action='save', status='ok')


@with_tempfile()
def test_remove_uninstalled(path=None):
    ds = Dataset(path)
    assert_raises(ValueError, ds.remove)


@with_tempfile()
def test_remove_nowhining(path=None):
    # when removing a dataset under a dataset (but not a subdataset)
    # should not provide a meaningless message that something was not right
    ds = Dataset(path).create()
    # just install/clone inside of it
    subds_path = ds.pathobj / 'subds'
    clone(path=subds_path, source=path)
    remove(dataset=subds_path)  # should remove just fine


@with_tempfile()
def test_remove_recreation(path=None):
    # test recreation is possible and doesn't conflict with in-memory
    # remainings of the old instances
    # see issue #1311
    ds = Dataset(path).create()
    ds.remove(reckless='availability')
    ds = Dataset(path).create()
    assert_repo_status(ds.path)
    ok_(ds.is_installed())


@with_tree({'one': 'one', 'two': 'two', 'three': 'three'})
def test_remove_more_than_one(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    assert_repo_status(path)
    # ensure #1912 stays resolved
    ds.remove(['one', 'two'], reckless='availability')
    assert_repo_status(path)


@with_tempfile()
def test_no_interaction_with_untracked_content(path=None):
    # extracted from what was a metadata test originally
    ds = Dataset(op.join(path, 'origin')).create(force=True)
    create_tree(ds.path, {'sub': {'subsub': {'dat': 'lots of data'}}})
    subds = ds.create('sub', force=True)
    subds.remove(op.join('.datalad', 'config'))
    nok_((subds.pathobj / '.datalad' / 'config').exists())
    # this will only work, if `remove` didn't do anything stupid and
    # caused all content to be saved
    subds.create('subsub', force=True)


@with_tempfile()
def test_kill(path=None):
    # nested datasets with load
    ds = Dataset(path).create()
    (ds.pathobj / 'file.dat').write_text('load')
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
    eq_(ds.remove(reckless='availability',
                  result_xfm='datasets'),
        [subds, ds])
    nok_(ds.pathobj.exists())


@with_tempfile()
def test_clean_subds_removal(path=None):
    ds = Dataset(path).create()
    subds1 = ds.create('one')
    subds2 = ds.create('two')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['one', 'two'])
    assert_repo_status(ds.path)
    # now kill one
    res = ds.remove('one', reckless='availability', result_xfm=None)
    # subds1 got uninstalled, and ds got the removal of subds1 saved
    assert_result_count(res, 1, path=subds1.path, action='uninstall', status='ok')
    assert_result_count(res, 1, path=subds1.path, action='remove', status='ok')
    assert_result_count(res, 1, path=ds.path, action='save', status='ok')
    ok_(not subds1.is_installed())
    assert_repo_status(ds.path)
    # two must remain
    eq_(ds.subdatasets(result_xfm='relpaths'), ['two'])
    # one is gone
    nok_(subds1.pathobj.exists())
    # and now again, but this time remove something that is not installed
    ds.create('three')
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['three', 'two'])
    ds.drop('two', what='all', reckless='availability')
    assert_repo_status(ds.path)
    eq_(sorted(ds.subdatasets(result_xfm='relpaths')), ['three', 'two'])
    nok_(subds2.is_installed())
    # oderly empty mountpoint is maintained
    ok_(subds2.pathobj.exists())
    res = ds.remove('two', reckless='availability')
    assert_in_results(
        res,
        path=str(ds.pathobj / 'two'),
        action='remove')
    assert_repo_status(ds.path)
    # subds2 was already uninstalled, now ds got the removal of subds2 saved
    nok_(subds2.pathobj.exists())
    eq_(ds.subdatasets(result_xfm='relpaths'), ['three'])
