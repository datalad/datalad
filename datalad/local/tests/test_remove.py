# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test remove command"""

import os.path as op

from datalad.tests.utils import (
    assert_false,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_not_in_results,
    assert_repo_status,
    assert_result_count,
    assert_status,
    assert_true,
    get_deeply_nested_structure,
    with_tempfile,
)


@with_tempfile
def test_remove(path):
    # see docstring for test data structure
    ds = get_deeply_nested_structure(path)
    gitfile = op.join("subdir", "git_file.txt")

    assert_true((ds.pathobj / gitfile).exists())
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
    assert_false((ds.pathobj / gitfile).exists())

    # now same for an annexed files
    annexedfile = op.join("subdir", "annexed_file.txt")
    # drop failure prevents removal
    res = ds.remove(annexedfile, drop='all', on_failure='ignore')
    assert_result_count(res, 1)
    assert_in_results(res, status='error', action='drop',
                      path=str(ds.pathobj / annexedfile))
    assert_true((ds.pathobj / annexedfile).exists())

    # now remove the file, but actually not drop the underlying
    # key -- hence no availability loss -- default mode of operation
    # remember the key
    key = ds.repo.get_file_annexinfo(annexedfile)['key']
    res = ds.remove(annexedfile, drop='datasets',
                    on_failure='ignore')
    # removal and dataset save
    assert_result_count(res, 2)
    assert_in_results(res, action='remove', status='ok',
                      path=str(ds.pathobj / annexedfile))
    assert_not_in_results(res, action='drop')
    assert_false((ds.pathobj / annexedfile).exists())
    res = ds.repo.call_annex_records(['whereis', '--key', key, '--json'])
    assert_in_results(res, key=key, success=True)

    # now remove entire directory
    res = ds.remove('subdir', on_failure='ignore')
    assert_in_results(res, status='impossible', state='untracked')
    assert_true((ds.pathobj / 'subdir').exists())

    ds.save('subdir')
    res = ds.remove('subdir', on_failure='ignore')
    assert_in_results(res, status='ok', action='remove')
    assert_in_results(res, status='ok', action='save', type='dataset')
    assert_false((ds.pathobj / 'subdir').exists())

    # now remove an entire subdataset
    # prep: make clean
    rmdspath = ds.pathobj / 'subds_modified' / 'subds_lvl1_modified'
    ds.save(rmdspath, recursive=True)
    res = ds.remove(rmdspath, on_failure='ignore')
    # unique dataset, with unique keys -- must fail
    assert_in_results(res, status='error', action='drop', path=str(rmdspath))

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
    assert_false(rmdspath.exists())
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
    assert_false(ds.is_installed())
