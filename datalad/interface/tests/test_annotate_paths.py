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
from datalad.tests.utils import assert_raises
from datalad.tests.utils import create_tree

from datalad.distribution.dataset import Dataset
from datalad.api import annotate_paths
from datalad.interface.annotate_paths import get_modified_subpaths
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
        parent = Dataset(path).create(force=True)
    for node, items in tree.items():
        if isinstance(items, dict):
            node_path = opj(path, node)
            nodeds = Dataset(node_path).create(force=True)
            make_demo_hierarchy_datasets(node_path, items, parent=nodeds)
    return parent


@with_tempfile(mkdir=True)
def test_invalid_call(path):
    # inter-option dependencies
    assert_raises(
        ValueError,
        annotate_paths, '',
        force_subds_discovery=True, force_parentds_discovery=False)
    # modified_since needs a actual dataset
    assert_raises(
        ValueError,
        annotate_paths, dataset=path, modified="something")


@with_tree(demo_hierarchy)
@with_tempfile(mkdir=True)
def test_annotate_paths(dspath, nodspath):
    # this test doesn't use API`remove` to avoid circularities
    ds = make_demo_hierarchy_datasets(dspath, demo_hierarchy)
    ds.add('.', recursive=True)
    ok_clean_git(ds.path)

    with chpwd(dspath):
        # with and without an explicitly given path the result is almost the
        # same inside a dataset
        without_path = annotate_paths(on_failure='ignore')
        pwd_res = annotate_paths(path='.', on_failure='ignore')
        assert_result_count(
            without_path, 1, type='dataset', path=dspath)
        assert_result_count(
            pwd_res, 1, type='dataset', path=dspath, orig_request='.',
            raw_input=True)
        # make sure going into a subdataset vs giving it as a path has no
        # structural impact
        eq_(
            [{k: v for k, v in ap.items()
              if k not in ('registered_subds', 'raw_input', 'orig_request', 'refds')}
             for ap in annotate_paths(path='b', recursive=True)],
            [{k: v for k, v in ap.items()
              if k not in ('registered_subds', 'raw_input', 'orig_request', 'refds')}
             for ap in annotate_paths(dataset='b', recursive=True)])
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
    # needs to find 'aa' and the base
    assert_result_count(base_res, 2)
    assert_result_count(base_res, 2, type='dataset')
    assert_result_count(
        base_res, 1, type='dataset', state='clean', parentds=parentds.path,
        path=opj(parentds.path, 'aa'), status='')
    # same recursion but without a base dataset
    res = annotate_paths(path=opj(dspath, 'a'), recursive=True)
    # needs to find 'aa' and 'a' again
    assert_result_count(res, 2)
    eq_(res[-1],
        {k: base_res[-1][k] for k in base_res[-1]
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
        res, 1, orig_request=fpath, raw_input=True, type='file',
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
    # but for the top-most uninstalled one it merely reports absent state now
    assert_result_count(
        after_res, 1, state='absent',
        **{k: before_res[0][k] for k in before_res[0] if k not in ('state',)})
    # however, this beauty doesn't come for free, so it can be disabled
    # which will make the uninstalled subdataset like a directory in the
    # parent (or even just a non-existing path, if the mountpoint dir isn't
    # present
    after_res = ds.annotate_paths(subdspath, force_subds_discovery=False)
    assert_result_count(
        after_res, 1, type='directory',
        path=before_res[0]['path'],
        parentds=before_res[0]['parentds'])
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
    eq_(orig_res, res_recursion_again)


@with_tree(demo_hierarchy['b'])
def test_get_modified_subpaths(path):
    ds = Dataset(path).create(force=True)
    suba = ds.create('ba', force=True)
    subb = ds.create('bb', force=True)
    subsub = ds.create(opj('bb', 'bba', 'bbaa'), force=True)
    ds.add('.', recursive=True)
    ok_clean_git(path)

    orig_base_commit = ds.repo.repo.commit().hexsha

    # nothing was modified compared to the status quo, output must be empty
    eq_([],
        list(get_modified_subpaths(
            [dict(path=ds.path)],
            ds, orig_base_commit)))

    # modify one subdataset
    create_tree(subsub.path, {'added': 'test'})
    subsub.add('added')

    # it will replace the requested path with the path of the closest
    # submodule that is modified
    assert_result_count(
        get_modified_subpaths(
            [dict(path=ds.path)],
            ds, orig_base_commit),
        1,
        type='dataset', path=subb.path)

    # make another one dirty
    create_tree(suba.path, {'added': 'test'})

    # now a single query path will result in the two modified subdatasets
    assert_result_count(
        get_modified_subpaths(
            [dict(path=ds.path)],
            ds, orig_base_commit),
        2,
        type='dataset')

    # now save uptop, this will the new state of subb, but keep suba dirty
    ds.save(subb.path, recursive=True)
    # now if we ask for what was last saved, we only get the new state of subb
    assert_result_count(
        get_modified_subpaths(
            [dict(path=ds.path)],
            ds,
            'HEAD~1..HEAD'),
        1,
        type='dataset', path=subb.path)
    # comparing the working tree to head will the dirty suba instead
    assert_result_count(
        get_modified_subpaths(
            [dict(path=ds.path)],
            ds,
            'HEAD'),
        1,
        type='dataset', path=suba.path)

    # add/save everything, become clean
    ds.add('.', recursive=True)
    ok_clean_git(path)
    # nothing is reported as modified
    assert_result_count(
        get_modified_subpaths(
            [dict(path=ds.path)],
            ds,
            'HEAD'),
        0)
    # but looking all the way back, we find all changes
    assert_result_count(
        get_modified_subpaths(
            [dict(path=ds.path)],
            ds,
            orig_base_commit),
        2,
        type='dataset')

    # now we ask specifically for the file we added to subsub above
    query = [dict(path=opj(subsub.path, 'added'))]
    res = list(get_modified_subpaths(query, ds, orig_base_commit))
    # we only get this one result back, and not all the submodule state changes
    # that were also saved in the superdatasets
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, type='file', path=opj(subsub.path, 'added'), state='added')
    # but if we are only looking at the last saved change (suba), we will not
    # find our query return something
    res = get_modified_subpaths(query, ds, 'HEAD^')
    assert_result_count(res, 0)

    # deal with removal (force insufiicient copies error)
    ds.remove(suba.path, check=False)
    ok_clean_git(path)
    res = list(get_modified_subpaths([dict(path=ds.path)], ds, 'HEAD~1..HEAD'))
    # removed submodule + .gitmodules update
    assert_result_count(res, 2)
    assert_result_count(
        res, 1,
        type_src='dataset', path=suba.path)
