# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test interface.validate_paths

"""

from copy import deepcopy

from os.path import join as opj
from os.path import basename

from datalad.tests.utils import with_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import eq_
from datalad.tests.utils import assert_result_count

from datalad.distribution.dataset import Dataset
from datalad.api import annotate_paths
from datalad.utils import chpwd


__docformat__ = 'restructuredtext'

demo_hierarchy = {
    'a': {  # dataset
        'aa': {  # dataset
            'file_aa': 'file_aa'}},
    'b': {  # dataset
        'ba': {  # dataset
            'file_ba': 'file_ba'},
        'bb': {  # dataset
            'bba': {  # dataset
                'bbaa': {  # dataset
                    'file_bbaa': 'file_bbaa'}},
            'file_bb': 'file_bb'}},
}


def make_demo_hierarchy_datasets(path, tree, parent=None):
    if parent is None:
        parent = Dataset(path).create(force=True, save=False)
    for node, items in tree.items():
        if isinstance(items, dict):
            node_path = opj(path, node)
            nodeds = Dataset(node_path).create(force=True)
            make_demo_hierarchy_datasets(node_path, items, parent=nodeds)
    return parent


@with_tree(demo_hierarchy)
@with_tempfile(mkdir=True)
def test_annotate_paths(dspath, nodspath):
    # this test doesn't use API`remove` to avoid circularities
    ds = make_demo_hierarchy_datasets(dspath, demo_hierarchy)
    ds.add('.', recursive=True)
    ok_clean_git(ds.path)

    with chpwd(dspath):
        # even when ran in a dataset, this command doesn't discover
        # any path without an input
        eq_(annotate_paths(on_failure='ignore'), [])
        # here is how this would go
        pwd_res = annotate_paths(path='.', on_failure='ignore')
        assert_result_count(
            pwd_res, 1, type='dataset', path=dspath, pristine_path='.',
            requested=True)
    # now do it again, pointing to the ds directly
    res = ds.annotate_paths(on_failure='ignore')
    # no request, no refds, but otherwise the same
    eq_(len(res), len(pwd_res))
    eq_({k: pwd_res[0][k] for k in pwd_res[0]
         if k in ('path', 'type', 'action', 'status')},
        {k: res[0][k] for k in res[0]
         if k not in ('refds',)})

    # will refuse a path that is not a dataset as refds
    res = annotate_paths(dataset=nodspath, on_failure='ignore')
    assert_result_count(
        res, 1, status='error', path=nodspath,
        message='given reference dataset is not a dataset')

    # recursion with proper base dataset
    parentds = Dataset(opj(dspath, 'a'))
    base_res = parentds.annotate_paths(recursive=True)
    # needs to find 'aa'
    assert_result_count(base_res, 1)
    assert_result_count(
        base_res, 1, type='dataset', state='clean', parentds=parentds.path,
        path=opj(parentds.path, 'aa'), status='')
    # same recursion but without a base dataset
    res = annotate_paths(path=opj(dspath, 'a'), recursive=True)
    # needs to find 'aa' again, but also 'a' now
    assert_result_count(res, 2)
    eq_(res[-1],
        {k: base_res[0][k] for k in base_res[0]
         if k not in ('refds',)})
    assert_result_count(
        res, 1, type='dataset', status='',
        # it does not auto-discover parent datasets without force or a refds
        #parentds=parentds.path,
        path=parentds.path)
    # but we can force parent discovery
    res = parentds.annotate_paths(
        path=opj(dspath, 'a'), recursive=True, force_parentds_discovery=True)
    assert_result_count(res, 2)
    assert_result_count(
        res, 1, type='dataset', status='', parentds=dspath,
        path=parentds.path)

    # recursion with multiple disjoint seeds, no common base
    eq_([basename(p) for p in annotate_paths(
         path=[opj(dspath, 'a'), opj(dspath, 'b', 'bb', 'bba')], recursive=True,
         result_xfm='paths')],
        ['a', 'aa', 'bba', 'bbaa'])

    # recursion with partially overlapping seeds, no duplicate results
    eq_([basename(p) for p in annotate_paths(
         path=[opj(dspath, 'b'), opj(dspath, 'b', 'bb', 'bba')], recursive=True,
         result_xfm='paths')],
        ['b', 'ba', 'bb', 'bba', 'bbaa'])

    # get straight from a file
    fpath = opj('a', 'aa', 'file_aa')
    res = ds.annotate_paths(fpath)
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, pristine_path=fpath, requested=True, type='file',
        path=opj(ds.path, fpath), parentds=opj(ds.path, 'a', 'aa'), status='')
    # now drop it
    dropres = ds.drop(fpath, check=False)
    assert_result_count(dropres, 1, path=res[0]['path'], status='ok')
    # ask for same file again, use 'notneeded' for unavailable to try trigger
    # any difference
    droppedres = ds.annotate_paths(fpath, unavailable_path_status='notneeded')
    # but we get the same result
    eq_(res, droppedres)

    # now try the same on an uninstalled dataset
    subdspath = opj('b', 'bb')
    # before
    before_res = ds.annotate_paths(subdspath, recursive=True)
    assert_result_count(before_res, 3, status='', type='dataset')
    uninstall_res = ds.uninstall(subdspath, recursive=True, check=False)
    assert_result_count(uninstall_res, 3, status='ok', type='dataset')
    # after
    after_res = ds.annotate_paths(subdspath)
    # uninstall hides all low-level datasets
    assert_result_count(after_res, 1)
    # but for the top-most uninstalled one it merely changes the type
    # to be a directory in the parent.
    # XXX consider making this look like a subdataset (type=dataset,
    # parentds=likenow), but add something like state=absent
    # this way we can use this info in, e.g., `get` right away and
    # don't have to rediscover the relationship
    assert_result_count(
        after_res, 1, type='directory',
        **{k: before_res[0][k] for k in before_res[0] if k not in ('type',)})

    # feed annotated paths into annotate_paths, it shouldn't change things
    # upon second run
    # datasets and file
    res = ds.annotate_paths(['.', fpath], recursive=True)
    # make a copy, just to the sure
    orig_res = deepcopy(res)
    assert_result_count(res, 7)
    # and in again, no recursion this time
    res_again = ds.annotate_paths(res)
    # doesn't change a thing
    eq_(orig_res, res_again)
    # and in again, with recursion this time
    res_recursion_again = ds.annotate_paths(res, recursive=True)
    assert_result_count(res_recursion_again, 7)
    # doesn't change a thing
    # TODO right now does change some props
    eq_(orig_res, res_recursion_again)
