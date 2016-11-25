# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test dirty dataset handling

"""

__docformat__ = 'restructuredtext'

import os
from os.path import join as opj
from nose.tools import assert_raises, assert_equal
from datalad.tests.utils import with_tempfile, assert_not_equal
from datalad.tests.utils import with_tree
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import ok_
from datalad.interface.utils import handle_dirty_dataset
from datalad.interface.utils import get_paths_by_dataset
from datalad.interface.utils import save_dataset_hierarchy
from datalad.distribution.dataset import Dataset
from datalad.api import save

_dirty_modes = ('fail', 'ignore', 'save-before')


def _check_all_clean(ds, state):
    assert state is not None
    for mode in _dirty_modes:
        # nothing wrong, nothing saved
        handle_dirty_dataset(ds, mode)
        assert_equal(state, ds.repo.get_hexsha())


def _check_auto_save(ds, orig_state):
    handle_dirty_dataset(ds, 'ignore')
    assert_raises(RuntimeError, handle_dirty_dataset, ds, 'fail')
    handle_dirty_dataset(ds, 'save-before')
    state = ds.repo.get_hexsha()
    assert_not_equal(orig_state, state)
    _check_all_clean(ds, state)
    return state


@with_tempfile(mkdir=True)
def test_dirty(path):
    for mode in _dirty_modes:
        # does nothing without a dataset
        handle_dirty_dataset(None, mode)
    # placeholder, but not yet created
    ds = Dataset(path)
    # unknown mode
    assert_raises(ValueError, handle_dirty_dataset, ds, 'MADEUP')
    # not yet created is very dirty
    assert_raises(RuntimeError, handle_dirty_dataset, ds, 'fail')
    handle_dirty_dataset(ds, 'ignore')
    assert_raises(RuntimeError, handle_dirty_dataset, ds, 'save-before')
    # should yield a clean repo
    ds.create()
    orig_state = ds.repo.get_hexsha()
    _check_all_clean(ds, orig_state)
    # tainted: untracked
    with open(opj(ds.path, 'something'), 'w') as f:
        f.write('some')
    orig_state = _check_auto_save(ds, orig_state)
    # tainted: staged
    with open(opj(ds.path, 'staged'), 'w') as f:
        f.write('some')
    ds.repo.add('staged', git=True)
    orig_state = _check_auto_save(ds, orig_state)
    # tainted: submodule
    # not added to super on purpose!
    subds = ds.create('subds')
    _check_all_clean(subds, subds.repo.get_hexsha())
    ok_clean_git(ds.path)
    # subdataset must be added as a submodule!
    assert_equal(ds.get_subdatasets(), ['subds'])


@with_tempfile(mkdir=True)
def test_paths_by_dataset(path):
    ds = Dataset(path).create()
    subds = ds.create('one')
    subsubds = subds.create('two')
    d, ua, ne = get_paths_by_dataset([path])
    for t in (ua, ne):
        assert_equal(t, [])
    assert_equal(d, {ds.path: [ds.path]})

    d, ua, ne = get_paths_by_dataset([path], recursive=True)
    for t in (ua, ne):
        assert_equal(t, [])
    for t in (ds, subds, subsubds):
        assert_equal(d[t.path], [t.path])

    os.makedirs(opj(ds.path, 'one', 'some'))
    hidden = subds.create(opj('some', 'deep'))
    testpath = opj(subds.path, 'some')
    d, ua, ne = get_paths_by_dataset([testpath], recursive=True)
    for t in (ua, ne):
        assert_equal(t, [])
    # must contain the containing dataset, and the testpath exactly
    assert_equal(d[subds.path], [testpath])
    # and also the subdataset underneath
    assert_equal(d[hidden.path], [hidden.path])


demo_hierarchy = {
    'a': {
        'aa': {
            'file_aa': 'file_aa'}},
    'b': {
        'ba': {
            'file_ba': 'file_ba'},
        'bb': {
            'bba': {
                'bbaa': {
                    'file_bbaa': 'file_bbaa'}},
            'file_bb': 'file_bb'}},
    'c': {
        'ca': {
            'file_ca': 'file_ca'},
        'file_c': 'file_c'},
    'd': {
        'da': {
            'file_da': 'file_da'},
        'db': {
            'file_db': 'file_db'},
        'file_d': 'file_d'},
}


def make_demo_hierarchy_datasets(path, tree):
    for node, items in tree.items():
        node_path = opj(path, node)
        if isinstance(items, dict):
            Dataset(node_path).create(force=True)
            make_demo_hierarchy_datasets(node_path, items)
            continue
    topds = Dataset(path)
    if not topds.is_installed():
        topds.create(force=True)
        return topds


@with_tree(demo_hierarchy)
def test_save_hierarchy(path):
    # this test doesn't use API`remove` to avoid circularities
    ds = make_demo_hierarchy_datasets(path, demo_hierarchy)
    ds.save(auto_add_changes=True, recursive=True)
    ok_clean_git(ds.path)
    ds_bb = Dataset(opj(ds.path, 'b', 'bb'))
    ds_bba = Dataset(opj(ds_bb.path, 'bba'))
    ds_bbaa = Dataset(opj(ds_bba.path, 'bbaa'))
    # introduce a change at the lowest level
    ds_bbaa.repo.remove('file_bbaa')
    for d in (ds, ds_bb, ds_bba, ds_bbaa):
        ok_(d.repo.dirty)
    save_dataset_hierarchy((ds_bb.path, ds_bbaa.path))
    # it has saved all changes in the subtrees spanned
    # by the given datasets, but nothing else
    for d in (ds_bb, ds_bba, ds_bbaa):
        ok_clean_git(d.path)
    ok_(ds.repo.dirty)
    # now with two modified repos
    d = Dataset(opj(ds.path, 'd'))
    da = Dataset(opj(d.path, 'da'))
    da.repo.remove('file_da')
    db = Dataset(opj(d.path, 'db'))
    db.repo.remove('file_db')
    save_dataset_hierarchy((d.path, da.path, db.path))
    for d in (d, da, db):
        ok_clean_git(d.path)
    ok_(ds.repo.dirty)
    # and now with files all over the place and saving
    # all the way to the root
    aa = Dataset(opj(ds.path, 'a', 'aa'))
    aa.repo.remove('file_aa')
    ba = Dataset(opj(ds.path, 'b', 'ba'))
    ba.repo.remove('file_ba')
    bb = Dataset(opj(ds.path, 'b', 'bb'))
    bb.repo.remove('file_bb')
    c = Dataset(opj(ds.path, 'c'))
    c.repo.remove('file_c')
    ca = Dataset(opj(ds.path, 'c', 'ca'))
    ca.repo.remove('file_ca')
    d = Dataset(opj(ds.path, 'd'))
    d.repo.remove('file_d')
    save_dataset_hierarchy((aa.path, ba.path, bb.path, c.path, ca.path, d.path),
                           base=ds.path)
    ok_clean_git(ds.path)
