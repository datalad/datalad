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
from os.path import relpath
from nose.tools import assert_raises, assert_equal
from datalad.tests.utils import with_tempfile, assert_not_equal
from datalad.tests.utils import assert_in
from datalad.tests.utils import with_tree
from datalad.tests.utils import create_tree
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import ok_
from datalad.interface.utils import handle_dirty_dataset
from datalad.interface.utils import get_paths_by_dataset
from datalad.interface.utils import save_dataset_hierarchy
from datalad.interface.utils import get_dataset_directories
from datalad.interface.utils import filter_unmodified
from datalad.interface.save import Save
from datalad.distribution.dataset import Dataset
from datalad.distribution.utils import _install_subds_inplace
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

    d, ua, ne = get_paths_by_dataset(
        [path], recursive=True)
    for t in (ua, ne):
        assert_equal(t, [])

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
    created_ds = []
    for node, items in tree.items():
        node_path = opj(path, node)
        if isinstance(items, dict):
            ds = make_demo_hierarchy_datasets(node_path, items)
            created_ds.append(ds)
    topds = Dataset(path)
    if not topds.is_installed():
        topds.create(force=True)
        # TODO this farce would not be necessary if add() could add subdatasets
        for ds in created_ds:
            _install_subds_inplace(ds=topds, path=ds.path, relativepath=relpath(ds.path, topds.path))
            ds.save()
        return topds


@with_tree(demo_hierarchy)
def test_save_hierarchy(path):
    # this test doesn't use API`remove` to avoid circularities
    ds = make_demo_hierarchy_datasets(path, demo_hierarchy)
    ds.add('.', recursive=True)
    ok_clean_git(ds.path)
    ds_bb = Dataset(opj(ds.path, 'b', 'bb'))
    ds_bba = Dataset(opj(ds_bb.path, 'bba'))
    ds_bbaa = Dataset(opj(ds_bba.path, 'bbaa'))
    # introduce a change at the lowest level
    ds_bbaa.repo.remove('file_bbaa')
    for d in (ds, ds_bb, ds_bba, ds_bbaa):
        ok_(d.repo.dirty)
    ds_bb.save(files=ds_bbaa.path, super_datasets=True)
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
    ds.save(files=(aa.path, ba.path, bb.path, c.path, ca.path, d.path),
            super_datasets=True)
    ok_clean_git(ds.path)


@with_tempfile(mkdir=True)
def test_get_dataset_directories(path):
    assert_raises(ValueError, get_dataset_directories, path)
    ds = Dataset(path).create()
    # ignores .git always and .datalad by default
    assert_equal(get_dataset_directories(path), [])
    assert_equal(get_dataset_directories(path, ignore_datalad=False),
                 [opj(path, '.datalad')])
    # find any directory, not just those known to git
    testdir = opj(path, 'newdir')
    os.makedirs(testdir)
    assert_equal(get_dataset_directories(path), [testdir])
    # do not find files
    with open(opj(path, 'somefile'), 'w') as f:
        f.write('some')
    assert_equal(get_dataset_directories(path), [testdir])
    # find more than one directory
    testdir2 = opj(path, 'newdir2')
    os.makedirs(testdir2)
    assert_equal(sorted(get_dataset_directories(path)), sorted([testdir, testdir2]))
    # find subdataset mount points
    subdsdir = opj(path, 'sub')
    subds = ds.create(subdsdir)
    assert_equal(sorted(get_dataset_directories(path)), sorted([testdir, testdir2, subdsdir]))
    # do not find content within subdataset dirs
    os.makedirs(opj(path, 'sub', 'deep'))
    assert_equal(sorted(get_dataset_directories(path)), sorted([testdir, testdir2, subdsdir]))
    subsubdsdir = opj(subdsdir, 'subsub')
    subds.create(subsubdsdir)
    assert_equal(sorted(get_dataset_directories(path)), sorted([testdir, testdir2, subdsdir]))
    # find nested directories
    testdir3 = opj(testdir2, 'newdir21')
    os.makedirs(testdir3)
    assert_equal(sorted(get_dataset_directories(path)), sorted([testdir, testdir2, testdir3, subdsdir]))
    # only return hits below the search path
    assert_equal(sorted(get_dataset_directories(testdir2)), sorted([testdir3]))
    # empty subdataset mount points are reported too
    ds.uninstall(subds.path, check=False, recursive=True)
    ok_(not subds.is_installed())
    ok_(os.path.exists(subds.path))
    assert_equal(sorted(get_dataset_directories(path)), sorted([testdir, testdir2, testdir3, subdsdir]))


def test_interface_prep():
    # verify sanity if nothing was given, as it would look like from the
    # cmdline
    assert_equal(Save._prep(path=[], dataset=None), ({}, []))


@with_tree(demo_hierarchy['b'])
def test_filter_unmodified(path):
    ds = Dataset(path).create(force=True)
    suba = ds.create('ba', force=True)
    subb = ds.create('bb', force=True)
    subsub = ds.create(opj('bb', 'bba', 'bbaa'), force=True)
    ds.add('.', recursive=True)
    ok_clean_git(path)

    spec, unavail = Save._prep('.', ds, recursive=True)
    # just to be sure -- find all datasets, and just datasets
    assert_equal(len(spec), 4)
    for r, p in spec.items():
        assert_equal([r], p)

    orig_base_commit = ds.repo.repo.commit()
    # nothing was modified compared to the status quo, output must be empty
    assert_equal({}, filter_unmodified(spec, ds, orig_base_commit))

    # modify one subdataset
    added_path = opj(subb.path, 'added')
    create_tree(subb.path, {'added': 'test'})
    subb.add('added')

    # still nothing was modified compared to orig commit, because the base
    # dataset does not have the recent change saved
    assert_equal({}, filter_unmodified(spec, ds, orig_base_commit))

    ds.save(all_changes=True)

    modspec, unavail = Save._prep('.', ds, recursive=True)
    # arg sorting is not affected
    assert_equal(spec, modspec)

    # only the actually modified components per dataset are kept
    assert_equal(
        {
            ds.path: [subb.path],
            subb.path: [added_path]
        },
        filter_unmodified(spec, ds, orig_base_commit))

    # deal with removal (force insufiicient copies error)
    ds.remove(opj(subsub.path, 'file_bbaa'), check=False)
    # saves all the way up
    ok_clean_git(path)

    modspec, unavail = Save._prep('.', ds, recursive=True)
    # arg sorting is again not affected
    assert_equal(spec, modspec)
    # only the actually modified components per dataset are kept
    assert_equal(
        {
            ds.path: [subb.path],
            subb.path: [added_path, subsub.path],
            subsub.path: []
        },
        {d: sorted(p) for d, p in filter_unmodified(spec, ds, orig_base_commit).items()})


from ..base import Interface
from datalad.distribution.dataset import datasetmethod, EnsureDataset
from datalad.interface.utils import eval_results, build_doc
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter


class Test_Utils(Interface):
    """TestUtil's fake command"""

    _params_ = dict(
        number=Parameter(
            args=("-n", "--number",),
            doc="""It's a number""",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to update.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),)

    @staticmethod
    @datasetmethod(name='fake_command')
    @eval_results
    @build_doc
    def __call__(number, dataset=None):

        for i in range(number):
            yield i


def test_eval_results():

    from datalad.utils import swallow_logs
    import logging
    # test eval_results is able to determine the call, a method of which it is
    # decorating:
    with swallow_logs(new_level=logging.DEBUG) as cml:
        Dataset('/does/not/matter').fake_command(3)
        cml.assert_logged("Determined class of decorated function: {}"
                          "".format(Test_Utils().__class__), level='DEBUG')

    # test docs
    doc1 = Dataset.fake_command.__doc__
    doc2 = Test_Utils().__call__.__doc__
    assert_equal(doc1, doc2)
    assert_in("TestUtil's fake command", doc1)
    assert_in("Parameters", doc1)
    assert_in("It's a number", doc1)

    # test results:
    result = Test_Utils().__call__(2)
    assert_equal(result, [0, 1])
    result = Dataset('/does/not/matter').fake_command(3)
    assert_equal(result, [0, 1, 2])
    # test signature:
    from inspect import getargspec
    assert_equal(getargspec(Dataset.fake_command)[0], ['number', 'dataset'])
    assert_equal(getargspec(Test_Utils.__call__)[0], ['number', 'dataset'])

    # test _eval_arguments:
    with swallow_logs(new_level=logging.WARNING) as cml:
        Dataset('/does/not/matter').fake_command(3, _eval_arg1="blubb")
        assert_in("_eval_arg1: blubb", cml.out)
        assert_in("_eval_arg2: default2", cml.out)
    # without anything keep defaults
    with swallow_logs(new_level=logging.WARNING) as cml:
        Dataset('/does/not/matter').fake_command(3)
        assert_in("_eval_arg1: default1", cml.out)
        assert_in("_eval_arg2: default2", cml.out)
    # same for version not bound to Dataset:
    with swallow_logs(new_level=logging.WARNING) as cml:
        Test_Utils().__call__(3, _eval_arg1="blubb")
        assert_in("_eval_arg1: blubb", cml.out)
        assert_in("_eval_arg2: default2", cml.out)
    # without anything keep defaults
    with swallow_logs(new_level=logging.WARNING) as cml:
        Test_Utils().__call__(3)
        assert_in("_eval_arg1: default1", cml.out)
        assert_in("_eval_arg2: default2", cml.out)

