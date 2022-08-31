# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test status command"""

import os.path as op

import datalad.utils as ut
from datalad.api import status
from datalad.core.local.status import get_paths_by_ds
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    CommandError,
    IncompleteResultsError,
    NoDatasetFound,
)
from datalad.tests.utils_pytest import (
    OBSCURE_FILENAME,
    SkipTest,
    assert_dict_equal,
    assert_in,
    assert_in_results,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    eq_,
    get_deeply_nested_structure,
    has_symlink_capability,
    with_tempfile,
)
from datalad.utils import (
    chpwd,
    on_windows,
)


@with_tempfile(mkdir=True)
def test_runnin_on_empty(path=None):
    # empty repo
    repo = AnnexRepo(path, create=True)
    # just wrap with a dataset
    ds = Dataset(path)
    # and run status ... should be good and do nothing
    eq_([], ds.status(result_renderer='disabled'))


@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile(mkdir=True)
def test_status_basics(path=None, linkpath=None, otherdir=None):
    if has_symlink_capability():
        # make it more complicated by default
        ut.Path(linkpath).symlink_to(path, target_is_directory=True)
        path = linkpath

    with chpwd(path):
        assert_raises(NoDatasetFound, status)
    ds = Dataset(path).create()
    # outcome identical between ds= and auto-discovery
    with chpwd(path):
        assert_raises(IncompleteResultsError, status, path=otherdir)
        stat = status(result_renderer='disabled')
    eq_(stat, ds.status(result_renderer='disabled'))
    assert_status('ok', stat)
    # we have a bunch of reports (be vague to be robust to future changes
    assert len(stat) > 2
    # check the composition
    for s in stat:
        eq_(s['status'], 'ok')
        eq_(s['action'], 'status')
        eq_(s['state'], 'clean')
        eq_(s['type'], 'file')
        assert_in('gitshasum', s)
        assert_in('bytesize', s)
        eq_(s['refds'], ds.path)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_status_nods(path=None, otherpath=None):
    ds = Dataset(path).create()
    assert_result_count(
        ds.status(path=otherpath, on_failure='ignore', result_renderer='disabled'),
        1,
        status='error',
        message=('path not underneath the reference dataset %s', ds.path))
    otherds = Dataset(otherpath).create()
    assert_result_count(
        ds.status(path=otherpath, on_failure='ignore', result_renderer='disabled'),
        1,
        path=otherds.path,
        status='error',
        message=('path not underneath the reference dataset %s', ds.path))


@with_tempfile(mkdir=True)
@with_tempfile()
def test_status(_path=None, linkpath=None):
    # do the setup on the real path, not the symlink, to have its
    # bugs not affect this test of status()
    ds = get_deeply_nested_structure(str(_path))
    if has_symlink_capability():
        # make it more complicated by default
        ut.Path(linkpath).symlink_to(_path, target_is_directory=True)
        path = linkpath
    else:
        path = _path

    ds = Dataset(path)
    if has_symlink_capability():
        assert ds.pathobj != ds.repo.pathobj

    # spotcheck that annex status reporting and availability evaluation
    # works
    assert_result_count(
        ds.status(annex='all', result_renderer='disabled'),
        1,
        path=str(ds.pathobj / 'subdir' / 'annexed_file.txt'),
        key='MD5E-s5--275876e34cf609db118f3d84b799a790.txt',
        has_content=True,
        objloc=str(ds.repo.pathobj / '.git' / 'annex' / 'objects' /
        # hashdir is different on windows
        ('f33' if ds.repo.is_managed_branch() else '7p') /
        ('94b' if ds.repo.is_managed_branch() else 'gp') /
        'MD5E-s5--275876e34cf609db118f3d84b799a790.txt' /
        'MD5E-s5--275876e34cf609db118f3d84b799a790.txt'))

    plain_recursive = ds.status(recursive=True, result_renderer='disabled')
    # check integrity of individual reports
    for res in plain_recursive:
        # anything that is an "intended" symlink should be reported
        # as such
        if 'link2' in str(res['path']):
            assert res['type'] == 'symlink', res
        # every item must report its parent dataset
        assert_in('parentds', res)

    # bunch of smoke tests
    # query of '.' is same as no path
    eq_(plain_recursive, ds.status(path='.', recursive=True,
                                   result_renderer='disabled'))
    # duplicate paths do not change things
    eq_(plain_recursive, ds.status(path=['.', '.'], recursive=True,
                                   result_renderer='disabled'))
    # neither do nested paths
    eq_(plain_recursive,
        ds.status(path=['.', 'subds_modified'], recursive=True,
                  result_renderer='disabled'))
    # when invoked in a subdir of a dataset it still reports on the full thing
    # just like `git status`, as long as there are no paths specified
    with chpwd(op.join(path, 'directory_untracked')):
        plain_recursive = status(recursive=True, result_renderer='disabled')
    # should be able to take absolute paths and yield the same
    # output
    eq_(plain_recursive, ds.status(path=ds.path, recursive=True,
                                   result_renderer='disabled'))

    # query for a deeply nested path from the top, should just work with a
    # variety of approaches
    rpath = op.join('subds_modified', 'subds_lvl1_modified',
                    OBSCURE_FILENAME + u'_directory_untracked')
    apathobj = ds.pathobj / rpath
    apath = str(apathobj)
    # ds.repo.pathobj will have the symlink resolved
    arealpath = ds.repo.pathobj / rpath
    # TODO include explicit relative path in test
    for p in (rpath, apath, arealpath, None):
        if p is None:
            # change into the realpath of the dataset and
            # query with an explicit path
            with chpwd(ds.repo.path):
                res = ds.status(path=op.join('.', rpath), result_renderer='disabled')
        else:
            res = ds.status(path=p, result_renderer='disabled')
        assert_result_count(
            res,
            1,
            state='untracked',
            type='directory',
            refds=ds.path,
            # path always comes out a full path inside the queried dataset
            path=apath,
        )

    assert_result_count(
        ds.status(
            recursive=True, result_renderer='disabled'),
        1,
        path=apath)
    # limiting recursion will exclude this particular path
    assert_result_count(
        ds.status(
            recursive=True,
            recursion_limit=1, result_renderer='disabled'),
        0,
        path=apath)
    # negative limit is unlimited limit
    eq_(
        ds.status(recursive=True, recursion_limit=-1, result_renderer='disabled'),
        ds.status(recursive=True, result_renderer='disabled')
    )

    # check integrity of individual reports with a focus on how symlinks
    # are reported in annex-mode
    # this is different from plain git-mode, which reports types as-is
    # from the git record
    for res in ds.status(recursive=True, annex='basic',
                         result_renderer='disabled'):
        # anything that is an "intended" symlink should be reported
        # as such. In contrast, anything that is a symlink for mere
        # technical reasons (annex using it for something in some mode)
        # should be reported as the thing it is representing (i.e.
        # a file)
        if 'link2' in str(res['path']):
            assert res['type'] == 'symlink', res
        else:
            assert res['type'] != 'symlink', res


# https://github.com/datalad/datalad-revolution/issues/64
# breaks when the tempdir is a symlink
@with_tempfile(mkdir=True)
def test_subds_status(path=None):
    ds = Dataset(path).create()
    subds = ds.create('subds')
    assert_repo_status(ds.path)
    subds.create('someotherds')
    assert_repo_status(subds.path)
    assert_repo_status(ds.path, modified=['subds'])
    assert_result_count(
        ds.status(path='subds', result_renderer='disabled'),
        1,
        # must be modified, not added (ds was clean after it was added)
        state='modified',
        type='dataset',
        path=subds.path,
        refds=ds.path)

    # path="." gets treated as "this dataset's content" without requiring a
    # trailing "/"...
    assert_result_count(
        subds.status(path=".", result_renderer='disabled'),
        1,
        type="dataset",
        path=op.join(subds.path, "someotherds"),
        refds=subds.path)

    # ... and so does path=<path/to/ds>.
    assert_result_count(
        subds.status(path=subds.path, result_renderer='disabled'),
        1,
        type="dataset",
        path=op.join(subds.path, "someotherds"),
        refds=subds.path)

    assert_result_count(
        subds.status(path=op.join(subds.path, op.pardir, "subds"),
                     result_renderer='disabled'),
        1,
        type="dataset",
        path=op.join(subds.path, "someotherds"),
        refds=subds.path)

    assert_result_count(
        subds.status(path=op.join(subds.path, op.curdir),
                     result_renderer='disabled'),
        1,
        type="dataset",
        path=op.join(subds.path, "someotherds"),
        refds=subds.path)


@with_tempfile
def test_status_symlinked_dir_within_repo(path=None):
    if not has_symlink_capability():
        raise SkipTest("Can't create symlinks")
    # <path>
    # |-- bar -> <path>/foo
    # `-- foo
    #     `-- f
    ds = Dataset(path).create()
    foo = ds.pathobj / "foo"
    foo.mkdir()
    (foo / "f").write_text("content")
    (ds.pathobj / "bar").symlink_to(foo, target_is_directory=True)
    ds.save()
    bar_f = ds.pathobj / "bar" / "f"

    def call():
        return ds.status(path=[bar_f], annex="availability",
                         on_failure="ignore", result_renderer='disabled')

    if ds.repo.git_annex_version < "8.20200522" \
        or (on_windows and ds.repo.git_annex_version < "10.20220525"):
        # version for windows is an approx guess, but stopped happening
        # somewhere around 10.20220505-g3b83224e5 may be.
        # see https://github.com/datalad/datalad/issues/6849
        assert_result_count(call(), 0)
    elif ds.repo.git_annex_version < '10.20220222':
        # As of 2a8fdfc7d (Display a warning message when asked to operate on a
        # file inside a symlinked directory, 2020-05-11), git-annex will error.
        with assert_raises(CommandError):
            call()
    elif '10.20220222' <= ds.repo.git_annex_version < '10.20220322':
        # No error on annex' side since 10.20220222;
        # However, we'd now get something like this:
        # > git annex find bar/f
        # error: pathspec 'bar/f' did not match any file(s) known to git
        # Did you forget to 'git add'?
        #
        # But exists zero until 10.20220322!
        assert_result_count(call(), 0)
    else:
        res = call()
        assert_result_count(res, 1, status='error', state='unknown',
                            path=str(bar_f))


@with_tempfile
@with_tempfile
def test_get_paths_by_ds(path=None, otherdspath=None):
    otherds = Dataset(otherdspath).create()
    ds = get_deeply_nested_structure(path)

    # for testing below, a shortcut
    subds_modified = Dataset(ds.pathobj / 'subds_modified')

    # check docstrong of get_deeply_nested_structure() to understand
    # what is being tested here
    testcases = (
        # (
        #   (<dataset_arg>, <path arg>),
        #   {<path by ds dict>}
        #   [<error list>]
        # ),

        # find main dataset, pass-through arbitrary arguments, if no paths
        # go in, also no paths come out
        ((path, None), {ds.pathobj: None}, []),
        # a simple path in the rootds, stays just that, not traversal
        # into files underneaths
        ((ds, ['subdir']), {ds.pathobj: [ds.pathobj / 'subdir']}, []),
        # same for files, any number,
        # one record per dataset with multiple files
        ((ds, [op.join('subdir', 'git_file.txt'), 'directory_untracked']),
         {ds.pathobj: [ds.pathobj / 'directory_untracked',
                       ds.pathobj / 'subdir' / 'git_file.txt']},
         []),
        # same for a subdataset root -- still reported as part of
        # the superdataset!
        ((ds, ['subds_modified']),
         {ds.pathobj: [subds_modified.pathobj]},
         []),
        # but not with a trailing slash, then it is the subdataset root
        # itself that becomes the record!!!
        ((ds, ['subds_modified' + op.sep]),
         {subds_modified.pathobj: [subds_modified.pathobj]},
         []),
        # however, regardless of the path syntax, each behavior can be forced
        ((ds, ['subds_modified'], 'sub'),
         {subds_modified.pathobj: [subds_modified.pathobj]},
         []),
        ((ds, ['subds_modified' + op.sep], 'super'),
         {ds.pathobj: [subds_modified.pathobj]},
         []),
        # subdataset content is sorted into a subdataset record
        ((ds, [op.join('subds_modified', 'subdir')]),
         {subds_modified.pathobj: [ds.pathobj / 'subds_modified' / 'subdir']},
         []),
        # content from different datasets ends up in different records
        ((ds, [op.join('subdir', 'git_file.txt'),
               op.join('subds_modified', 'subdir'),
               op.join('subds_modified', 'subds_lvl1_modified')]),
         {ds.pathobj: [ds.pathobj / 'subdir' / 'git_file.txt'],
          subds_modified.pathobj: [
              subds_modified.pathobj / 'subdir',
              subds_modified.pathobj / 'subds_lvl1_modified']},
         []),
        # paths not matching existing content are no problem
        ((ds, ['doesnotexist',
               op.join('subdir', 'nothere'),
               op.join('subds_modified', 'subdir', 'gone')]),
         {ds.pathobj: [ds.pathobj / 'doesnotexist',
                       ds.pathobj / 'subdir' / 'nothere'],
          subds_modified.pathobj: [
              subds_modified.pathobj / 'subdir' / 'gone']},
         []),
        #
        # now error case
        #
        # a path that does sort under the root dataset
        ((path, [otherds.pathobj / 'totally' / 'different']),
         {},
         [otherds.pathobj / 'totally' / 'different']),
    )
    # evaluate the test cases
    for inp, pbd_target, error_target in testcases:
        paths_by_ds, errors = get_paths_by_ds(ds, *inp)
        assert_dict_equal(pbd_target, paths_by_ds)
        eq_(error_target, errors)

    # lastly, some more specialized test
    # paths get collapsed into dataset records, even when the path
    # order is not presorted to match individual datasets sequentially
    paths_by_ds, errors = get_paths_by_ds(
        ds, ds, [
            op.join('subdir', 'git_file.txt'),
            op.join('subds_modified', 'subdir'),
            op.join('subdir', 'annexed_file.txt'),
        ])
    eq_(
        list(paths_by_ds.keys()),
        [ds.pathobj, subds_modified.pathobj]
    )
    # result order (top-level first) is stable, even when a path comes first
    # that sorts later. Also mixed types are not a problem
    paths_by_ds, errors = get_paths_by_ds(
        ds, ds, [
            ds.pathobj / 'subds_modified' / 'subdir',
            op.join('subdir', 'git_file.txt'),
            op.join('subds_modified', 'subdir', 'annexed_file.txt'),
        ])
    eq_(
        list(paths_by_ds.keys()),
        [ds.pathobj, subds_modified.pathobj]
    )
