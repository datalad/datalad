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

import logging

from copy import deepcopy

import os
from os.path import (
    join as opj,
    basename,
    lexists,
    normpath,
    abspath,
)
from datalad.tests.utils import (
    with_tree,
    with_tempfile,
    eq_,
    assert_repo_status,
    assert_result_count,
    assert_raises,
    assert_not_in,
    create_tree,
    slow,
    swallow_logs,
    known_failure_githubci_win,
    assert_cwd_unchanged,
    SkipTest,
)
from datalad.distribution.dataset import Dataset
from datalad.api import (
    annotate_paths,
    install,
)
from datalad.interface.annotate_paths import (
    get_modified_subpaths,
    _resolve_path,
)
from datalad.utils import (
    chpwd,
    getpwd,
    on_windows,
)
from datalad.interface.tests.test_utils import make_demo_hierarchy_datasets

if on_windows:
    raise SkipTest('Deprecated code, will never work on Windows')


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


@slow  # 15.3509s
@with_tree(demo_hierarchy)
@with_tempfile(mkdir=True)
def test_annotate_paths(dspath, nodspath):
    # this test doesn't use API`remove` to avoid circularities
    ds = make_demo_hierarchy_datasets(dspath, demo_hierarchy)
    ds.save(recursive=True)
    assert_repo_status(ds.path)

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

        # when we point to a list of directories, there should be no
        # multiple rediscoveries of the subdatasets
        with swallow_logs(new_level=logging.DEBUG) as cml:
            annotate_paths(path=['a', 'b'])
            eq_(cml.out.count('Resolved dataset for subdataset reporting/modification'), 1)

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
        base_res, 1, type='dataset', parentds=parentds.path,
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
    before_res = ds.annotate_paths(subdspath, recursive=True,
                                   unavailable_path_status='error')
    assert_result_count(before_res, 3, status='', type='dataset')
    uninstall_res = ds.uninstall(subdspath, recursive=True, check=False)
    assert_result_count(uninstall_res, 3, status='ok', type='dataset')
    # after
    after_res = ds.annotate_paths(subdspath,
                                  unavailable_path_status='error',
                                  on_failure='ignore')
    # uninstall hides all low-level datasets
    assert_result_count(after_res, 1)
    # but for the top-most uninstalled one it merely reports absent state now
    assert_result_count(
        after_res, 1, state='absent',
        **{k: before_res[0][k] for k in before_res[0] if k not in ('state', 'status')})
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


@known_failure_githubci_win
@slow  # 11.0891s
@with_tree(demo_hierarchy['b'])
def test_get_modified_subpaths(path):
    ds = Dataset(path).create(force=True)
    suba = ds.create('ba', force=True)
    subb = ds.create('bb', force=True)
    subsub = ds.create(opj('bb', 'bba', 'bbaa'), force=True)
    ds.save(recursive=True)
    assert_repo_status(path)

    orig_base_commit = ds.repo.get_hexsha()

    # nothing was modified compared to the status quo, output must be empty
    eq_([],
        list(get_modified_subpaths(
            [dict(path=ds.path)],
            ds, orig_base_commit)))

    # modify one subdataset
    create_tree(subsub.path, {'added': 'test'})
    subsub.save('added')

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
    ds.save(recursive=True)
    assert_repo_status(path)
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
    assert_repo_status(path)
    res = list(get_modified_subpaths([dict(path=ds.path)], ds, 'HEAD~1..HEAD'))
    # removed submodule + .gitmodules update
    assert_result_count(res, 2)
    assert_result_count(
        res, 1,
        type_src='dataset', path=suba.path)


@slow  # 41.5367s
@with_tree(demo_hierarchy)
@with_tempfile(mkdir=True)
def test_recurseinto(dspath, dest):
    # make fresh dataset hierarchy
    ds = make_demo_hierarchy_datasets(dspath, demo_hierarchy)
    ds.save(recursive=True)
    # label intermediate dataset as 'norecurseinto'
    res = Dataset(opj(ds.path, 'b')).subdatasets(
        contains='bb',
        set_property=[('datalad-recursiveinstall', 'skip')])
    assert_result_count(res, 1, path=opj(ds.path, 'b', 'bb'))
    ds.save('b', recursive=True)
    assert_repo_status(ds.path)

    # recursive install, should skip the entire bb branch
    res = install(source=ds.path, path=dest, recursive=True,
                  result_xfm=None, result_filter=None)
    assert_result_count(res, 5)
    assert_result_count(res, 5, type='dataset')
    # we got the neighbor subdataset
    assert_result_count(res, 1, type='dataset',
                        path=opj(dest, 'b', 'ba'))
    # we did not get the one we wanted to skip
    assert_result_count(res, 0, type='dataset',
                        path=opj(dest, 'b', 'bb'))
    assert_not_in(
        opj(dest, 'b', 'bb'),
        Dataset(dest).subdatasets(fulfilled=True, result_xfm='paths'))
    assert(not Dataset(opj(dest, 'b', 'bb')).is_installed())

    # cleanup
    Dataset(dest).remove(recursive=True)
    assert(not lexists(dest))
    # again but just clone the base, and then get content and grab 'bb'
    # explicitly -- must get it installed
    dest = install(source=ds.path, path=dest)
    res = dest.get(['.', opj('b', 'bb')], get_data=False, recursive=True)
    assert_result_count(res, 7)
    assert_result_count(res, 7, type='dataset')
    assert_result_count(res, 1, type='dataset',
                        path=opj(dest.path, 'b', 'bb'))
    assert(Dataset(opj(dest.path, 'b', 'bb')).is_installed())


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
def test_resolve_path(somedir):

    abs_path = abspath(somedir)  # just to be sure
    rel_path = "some"
    expl_path_cur = opj(os.curdir, rel_path)
    expl_path_par = opj(os.pardir, rel_path)

    eq_(_resolve_path(abs_path), abs_path)

    current = getpwd()
    # no Dataset => resolve using cwd:
    eq_(_resolve_path(abs_path), abs_path)
    eq_(_resolve_path(rel_path), opj(current, rel_path))
    eq_(_resolve_path(expl_path_cur), normpath(opj(current, expl_path_cur)))
    eq_(_resolve_path(expl_path_par), normpath(opj(current, expl_path_par)))

    # now use a Dataset as reference:
    ds = Dataset(abs_path)
    eq_(_resolve_path(abs_path, ds), abs_path)
    eq_(_resolve_path(rel_path, ds), opj(abs_path, rel_path))
    eq_(_resolve_path(expl_path_cur, ds), normpath(opj(current, expl_path_cur)))
    eq_(_resolve_path(expl_path_par, ds), normpath(opj(current, expl_path_par)))
