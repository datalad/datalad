# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test status command"""

import os.path as op
from six import text_type
import datalad.utils as ut

from datalad.utils import (
    chpwd,
    on_windows,
)
from datalad.tests.utils import (
    eq_,
    assert_in,
    assert_raises,
    assert_status,
    assert_result_count,
    with_tempfile,
)
from datalad.support.exceptions import (
    NoDatasetArgumentFound,
    IncompleteResultsError,
)
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import (
    get_deeply_nested_structure,
    has_symlink_capability,
    assert_repo_status,
    OBSCURE_FILENAME,
)
from datalad.api import (
    status,
)


@with_tempfile(mkdir=True)
def test_runnin_on_empty(path):
    # empty repo
    repo = AnnexRepo(path, create=True)
    # just wrap with a dataset
    ds = Dataset(path)
    # and run status ... should be good and do nothing
    eq_([], ds.status())


@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile(mkdir=True)
def test_status_basics(path, linkpath, otherdir):
    if not on_windows:
        # make it more complicated by default
        ut.Path(linkpath).symlink_to(path, target_is_directory=True)
        path = linkpath

    with chpwd(path):
        assert_raises(NoDatasetArgumentFound, status)
    ds = Dataset(path).create()
    # outcome identical between ds= and auto-discovery
    with chpwd(path):
        assert_raises(IncompleteResultsError, status, path=otherdir)
        stat = status()
    eq_(stat, ds.status())
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
def test_status_nods(path, otherpath):
    ds = Dataset(path).create()
    assert_result_count(
        ds.status(path=otherpath, on_failure='ignore'),
        1,
        status='error',
        message='path not underneath this dataset')
    otherds = Dataset(otherpath).create()
    assert_result_count(
        ds.status(path=otherpath, on_failure='ignore'),
        1,
        path=otherds.path,
        status='error',
        message=(
            'dataset containing given paths is not underneath the reference dataset %s: %s',
            ds, [])
        )


@with_tempfile(mkdir=True)
@with_tempfile()
def test_status(_path, linkpath):
    # do the setup on the real path, not the symlink, to have its
    # bugs not affect this test of status()
    ds = get_deeply_nested_structure(text_type(_path))
    if has_symlink_capability():
        # make it more complicated by default
        ut.Path(linkpath).symlink_to(_path, target_is_directory=True)
        path = linkpath
    else:
        path = _path

    ds = Dataset(path)
    if not on_windows:
        # TODO test should also be has_symlink_capability(), but
        # something in the repo base class is not behaving yet
        # check the premise of this test
        assert ds.pathobj != ds.repo.pathobj

    # spotcheck that annex status reporting and availability evaluation
    # works
    assert_result_count(
        ds.status(annex='all'),
        1,
        path=text_type(ds.pathobj / 'subdir' / 'annexed_file.txt'),
        key='MD5E-s5--275876e34cf609db118f3d84b799a790.txt',
        has_content=True,
        objloc=text_type(ds.repo.pathobj / '.git' / 'annex' / 'objects' /
        # hashdir is different on windows
        ('f33' if on_windows else '7p') /
        ('94b' if on_windows else 'gp') /
        'MD5E-s5--275876e34cf609db118f3d84b799a790.txt' /
        'MD5E-s5--275876e34cf609db118f3d84b799a790.txt'))

    plain_recursive = ds.status(recursive=True)
    # check integrity of individual reports with a focus on how symlinks
    # are reported
    for res in plain_recursive:
        # anything that is an "intended" symlink should be reported
        # as such. In contrast, anything that is a symlink for mere
        # technical reasons (annex using it for something in some mode)
        # should be reported as the thing it is representing (i.e.
        # a file)
        if 'link2' in text_type(res['path']):
            assert res['type'] == 'symlink', res
        else:
            assert res['type'] != 'symlink', res
        # every item must report its parent dataset
        assert_in('parentds', res)

    # bunch of smoke tests
    # query of '.' is same as no path
    eq_(plain_recursive, ds.status(path='.', recursive=True))
    # duplicate paths do not change things
    eq_(plain_recursive, ds.status(path=['.', '.'], recursive=True))
    # neither do nested paths
    eq_(plain_recursive,
        ds.status(path=['.', 'subds_modified'], recursive=True))
    # when invoked in a subdir of a dataset it still reports on the full thing
    # just like `git status`, as long as there are no paths specified
    with chpwd(op.join(path, 'directory_untracked')):
        plain_recursive = status(recursive=True)
    # should be able to take absolute paths and yield the same
    # output
    eq_(plain_recursive, ds.status(path=ds.path, recursive=True))

    # query for a deeply nested path from the top, should just work with a
    # variety of approaches
    rpath = op.join('subds_modified', 'subds_lvl1_modified',
                    OBSCURE_FILENAME + u'_directory_untracked')
    apathobj = ds.pathobj / rpath
    apath = text_type(apathobj)
    # ds.repo.pathobj will have the symlink resolved
    arealpath = ds.repo.pathobj / rpath
    # TODO include explicit relative path in test
    for p in (rpath, apath, arealpath, None):
        if p is None:
            # change into the realpath of the dataset and
            # query with an explicit path
            with chpwd(ds.repo.path):
                res = ds.status(path=op.join('.', rpath))
        else:
            res = ds.status(path=p)
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
            recursive=True),
        1,
        path=apath)
    # limiting recursion will exclude this particular path
    assert_result_count(
        ds.status(
            recursive=True,
            recursion_limit=1),
        0,
        path=apath)
    # negative limit is unlimited limit
    eq_(
        ds.status(recursive=True, recursion_limit=-1),
        ds.status(recursive=True)
    )


# https://github.com/datalad/datalad-revolution/issues/64
# breaks when the tempdir is a symlink
@with_tempfile(mkdir=True)
def test_subds_status(path):
    ds = Dataset(path).create()
    subds = ds.create('subds')
    assert_repo_status(ds.path)
    subds.create('someotherds')
    assert_repo_status(subds.path)
    assert_repo_status(ds.path, modified=['subds'])
    assert_result_count(
        ds.status(path='subds'),
        1,
        # must be modified, not added (ds was clean after it was added)
        state='modified',
        type='dataset',
        path=subds.path,
        refds=ds.path)

    # path="." gets treated as "this dataset's content" without requiring a
    # trailing "/".
    assert_result_count(
        subds.status(path="."),
        1,
        type="dataset",
        path=op.join(subds.path, "someotherds"),
        refds=subds.path)
