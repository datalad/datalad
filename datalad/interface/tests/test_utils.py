# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test interface.utils

"""

from datalad.tests.utils import known_failure_direct_mode

import os
import logging
from os.path import join as opj
from os.path import exists
from nose.tools import assert_raises, assert_equal
from datalad.tests.utils import with_tempfile, assert_not_equal
from datalad.tests.utils import assert_true
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import with_tree
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import ok_
from datalad.tests.utils import slow
from datalad.utils import swallow_logs
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import EnsureDataset
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureKeyChoice

from ..base import Interface
from ..utils import eval_results
from ..utils import discover_dataset_trace_to_targets
from datalad.interface.base import build_doc
from ..utils import handle_dirty_dataset


__docformat__ = 'restructuredtext'
lgr = logging.getLogger('datalad.interface.tests.test_utils')
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
    # we don't want to auto-add untracked files by saving (anymore)
    assert_raises(AssertionError, _check_auto_save, ds, orig_state)
    # tainted: staged
    ds.repo.add('something', git=True)
    orig_state = _check_auto_save(ds, orig_state)
    # tainted: submodule
    # not added to super on purpose!
    subds = ds.create('subds')
    _check_all_clean(subds, subds.repo.get_hexsha())
    ok_clean_git(ds.path)
    # subdataset must be added as a submodule!
    assert_equal(ds.subdatasets(result_xfm='relpaths'), ['subds'])


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


def make_demo_hierarchy_datasets(path, tree, parent=None):
    if parent is None:
        parent = Dataset(path).create(force=True)
    for node, items in tree.items():
        if isinstance(items, dict):
            node_path = opj(path, node)
            nodeds = Dataset(node_path).create(force=True)
            make_demo_hierarchy_datasets(node_path, items, parent=nodeds)
    return parent


@slow  # 74.4509s
@with_tree(demo_hierarchy)
@known_failure_direct_mode  #FIXME
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
    # need to give file specifically, otherwise it will simply just preserve
    # staged changes
    ds_bb.save(path=opj(ds_bbaa.path, 'file_bbaa'))
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
    # generator
    d.save(recursive=True)
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
    ds.save(
        # append trailing slashes to the path to indicate that we want to
        # have the staged content in the dataset saved, rather than only the
        # subdataset state in the respective superds.
        # an alternative would have been to pass `save` annotated paths of
        # type {'path': dspath, 'process_content': True} for each dataset
        # in question, but here we want to test how this would most likely
        # by used from cmdline
        path=[opj(p, '')
               for p in (aa.path, ba.path, bb.path, c.path, ca.path, d.path)],
        super_datasets=True)


# Note: class name needs to match module's name
@build_doc
class TestUtils(Interface):
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
    def __call__(number, dataset=None):

        for i in range(number):
            # this dict will need to have the minimum info required by
            # eval_results
            yield {'path': 'some', 'status': 'ok', 'somekey': i, 'action': 'off'}


def test_eval_results_plus_build_doc():

    # test docs

    # docstring was build already:
    with swallow_logs(new_level=logging.DEBUG) as cml:
        TestUtils().__call__(1)
        assert_not_in("Building doc for", cml.out)
    # docstring accessible both ways:
    doc1 = Dataset.fake_command.__doc__
    doc2 = TestUtils().__call__.__doc__

    # docstring was built from Test_Util's definition:
    assert_equal(doc1, doc2)
    assert_in("TestUtil's fake command", doc1)
    assert_in("Parameters", doc1)
    assert_in("It's a number", doc1)

    # docstring also contains eval_result's parameters:
    assert_in("result_filter", doc1)
    assert_in("return_type", doc1)
    assert_in("list", doc1)
    assert_in("None", doc1)
    assert_in("return value behavior", doc1)
    assert_in("dictionary is passed", doc1)

    # test eval_results is able to determine the call, a method of which it is
    # decorating:
    with swallow_logs(new_level=logging.DEBUG) as cml:
        Dataset('/does/not/matter').fake_command(3)
        assert_in("Determined class of decorated function: {}"
                  "".format(TestUtils().__class__), cml.out)

    # test results:
    result = TestUtils().__call__(2)
    assert_equal(len(list(result)), 2)
    result = Dataset('/does/not/matter').fake_command(3)
    assert_equal(len(list(result)), 3)

    # test absent side-effect of popping eval_defaults
    kwargs = dict(return_type='list')
    TestUtils().__call__(2, **kwargs)
    assert_equal(list(kwargs), ['return_type'])

    # test signature:
    from inspect import getargspec
    assert_equal(getargspec(Dataset.fake_command)[0], ['number', 'dataset'])
    assert_equal(getargspec(TestUtils.__call__)[0], ['number', 'dataset'])


def test_result_filter():
    # ensure baseline without filtering
    assert_equal(
        [r['somekey'] for r in TestUtils().__call__(4)],
        [0, 1, 2, 3])
    # test two functionally equivalent ways to filter results
    # 1. Constraint-based -- filter by exception
    #    we have a full set of AND and OR operators for this
    # 2. custom filer function -- filter by boolean return value
    for filt in (
            EnsureKeyChoice('somekey', (0, 2)),
            lambda x: x['somekey'] in (0, 2)):
        assert_equal(
            [r['somekey'] for r in TestUtils().__call__(
                4,
                result_filter=filt)],
            [0, 2])
        # constraint returns full dict
        assert_dict_equal(
            TestUtils().__call__(
                4,
                result_filter=filt)[-1],
            {'action': 'off', 'path': 'some', 'status': 'ok', 'somekey': 2})

    # test more sophisticated filters that actually get to see the
    # API call's kwargs
    def greatfilter(res, **kwargs):
        assert_equal(kwargs.get('dataset', 'bob'), 'awesome')
        return True
    TestUtils().__call__(4, dataset='awesome', result_filter=greatfilter)

    def sadfilter(res, **kwargs):
        assert_equal(kwargs.get('dataset', 'bob'), None)
        return True
    TestUtils().__call__(4, result_filter=sadfilter)


@with_tree({k: v for k, v in demo_hierarchy.items() if k in ['a', 'd']})
@with_tempfile(mkdir=True)
def test_discover_ds_trace(path, otherdir):
    ds = make_demo_hierarchy_datasets(
        path,
        {k: v for k, v in demo_hierarchy.items() if k in ['a', 'd']})
    a = opj(ds.path, 'a')
    aa = opj(a, 'aa')
    d = opj(ds.path, 'd')
    db = opj(d, 'db')
    # we have to check whether we get the correct hierarchy, as the test
    # subject is also involved in this
    assert_true(exists(opj(db, 'file_db')))
    ds.add('.', recursive=True)
    ok_clean_git(ds.path)
    # now two datasets which are not available locally, but we
    # know about them (e.g. from metadata)
    dba = opj(db, 'sub', 'dba')
    dbaa = opj(dba, 'subsub', 'dbaa')
    for input, eds, goal in (
            ([], None, {}),
            ([ds.path], None, {}),
            ([otherdir], None, {}),
            ([opj(ds.path, 'nothere')], None, {}),
            ([opj(d, 'nothere')], None, {}),
            ([opj(db, 'nothere')], None, {}),
            ([a], None,
             {ds.path: set([a])}),
            ([aa, a], None,
             {ds.path: set([a]), a: set([aa])}),
            ([db], None,
             {ds.path: set([d]), d: set([db])}),
            ([opj(db, 'file_db')], None,
             {ds.path: set([d]), d: set([db])}),
            # just a regular non-existing path
            ([dba], None, {}),
            # but if we inject this knowledge it must come back out
            # as the child of the closest existing dataset
            ([dba], [dba],
             {ds.path: set([d]), d: set([db]), db: set([dba])}),
            # regardless of the depth
            ([dbaa], [dbaa],
             {ds.path: set([d]), d: set([db]), db: set([dbaa])}),
            ([dba, dbaa], [dba, dbaa],
             {ds.path: set([d]), d: set([db]), db: set([dba, dbaa])}),
            # we can simply add existing and non-existing datasets to the
            # include list get the desired result
            ([d, dba, dbaa], [d, dba, dbaa],
             {ds.path: set([d]), d: set([db]), db: set([dba, dbaa])}),
    ):
        spec = {}
        discover_dataset_trace_to_targets(ds.path, input, [], spec, includeds=eds)
        assert_dict_equal(spec, goal)
