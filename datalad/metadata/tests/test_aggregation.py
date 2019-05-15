# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test metadata aggregation"""


import os.path as op
from os.path import join as opj

from datalad.api import metadata
from datalad.distribution.dataset import Dataset


from datalad.tests.utils import skip_ssh
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import skip_if_on_windows


def _assert_metadata_empty(meta):
    ignore = set(['@id', '@context'])
    assert (not len(meta) or set(meta.keys()) == ignore), \
        'metadata record is not empty: {}'.format(
            {k: meta[k] for k in meta if k not in ignore})


_dataset_hierarchy_template = {
    'origin': {
        'dataset_description.json': """
{
    "Name": "mother_äöü東"
}""",
        'sub': {
            'dataset_description.json': """
{
    "Name": "child_äöü東"
}""",
            'subsub': {
                'dataset_description.json': """
            {
    "Name": "grandchild_äöü東"
}"""}}}}


@with_tree(tree=_dataset_hierarchy_template)
def test_basic_aggregate(path):
    # TODO give datasets some more metadata to actually aggregate stuff
    base = Dataset(opj(path, 'origin')).create(force=True)
    sub = base.create('sub', force=True)
    #base.metadata(sub.path, init=dict(homepage='this'), apply2global=True)
    subsub = base.create(opj('sub', 'subsub'), force=True)
    base.save(recursive=True)
    ok_clean_git(base.path)
    # we will first aggregate the middle dataset on its own, this will
    # serve as a smoke test for the reuse of metadata objects later on
    sub.aggregate_metadata()
    base.save()
    ok_clean_git(base.path)
    base.aggregate_metadata(recursive=True, update_mode='all')
    ok_clean_git(base.path)
    direct_meta = base.metadata(recursive=True, return_type='list')
    # loose the deepest dataset
    sub.uninstall('subsub', check=False)
    # no we should eb able to reaggregate metadata, and loose nothing
    # because we can aggregate aggregated metadata of subsub from sub
    base.aggregate_metadata(recursive=True, update_mode='all')
    # same result for aggregate query than for (saved) direct query
    agg_meta = base.metadata(recursive=True, return_type='list')
    for d, a in zip(direct_meta, agg_meta):
        print(d['path'], a['path'])
        assert_dict_equal(d, a)
    # no we can throw away the subdataset tree, and loose no metadata
    base.uninstall('sub', recursive=True, check=False)
    assert(not sub.is_installed())
    ok_clean_git(base.path)
    # same result for aggregate query than for (saved) direct query
    agg_meta = base.metadata(recursive=True, return_type='list')
    for d, a in zip(direct_meta, agg_meta):
        assert_dict_equal(d, a)


# tree puts aggregate metadata structures on two levels inside a dataset
@with_tree(tree={
    '.datalad': {
        'metadata': {
            'objects': {
                'someshasum': '{"homepage": "http://top.example.com"}'},
            'aggregate_v1.json': """\
{
    "sub/deep/some": {
        "dataset_info": "objects/someshasum"
    }
}
"""}},
    'sub': {
        '.datalad': {
            'metadata': {
                'objects': {
                    'someotherhash': '{"homepage": "http://sub.example.com"}'},
                'aggregate_v1.json': """\
{
    "deep/some": {
        "dataset_info": "objects/someotherhash"
    }
}
"""}}},
})
def test_aggregate_query(path):
    ds = Dataset(path).create(force=True)
    # no magic change to actual dataset metadata due to presence of
    # aggregated metadata
    res = ds.metadata(reporton='datasets', on_failure='ignore')
    assert_result_count(res, 1)
    assert_not_in('metadata', res[0])
    # but we can now ask for metadata of stuff that is unknown on disk
    res = ds.metadata(opj('sub', 'deep', 'some'), reporton='datasets')
    assert_result_count(res, 1)
    eq_({'homepage': 'http://top.example.com'}, res[0]['metadata'])
    # when no reference dataset is given the command will report the
    # aggregated metadata as it is recorded in the dataset that is the
    # closest parent on disk
    ds.create('sub', force=True)
    res = metadata(opj(path, 'sub', 'deep', 'some'), reporton='datasets')
    assert_result_count(res, 1)
    eq_({'homepage': 'http://sub.example.com'}, res[0]['metadata'])
    # when a reference dataset is given, it will be used as the metadata
    # provider
    res = ds.metadata(opj('sub', 'deep', 'some'), reporton='datasets')
    assert_result_count(res, 1)
    eq_({'homepage': 'http://top.example.com'}, res[0]['metadata'])


# this is for gh-1971
@with_tree(tree=_dataset_hierarchy_template)
def test_reaggregate_with_unavailable_objects(path):
    base = Dataset(opj(path, 'origin')).create(force=True)
    # force all metadata objects into the annex
    with open(opj(base.path, '.datalad', '.gitattributes'), 'w') as f:
        f.write(
            '** annex.largefiles=nothing\nmetadata/objects/** annex.largefiles=anything\n')
    sub = base.create('sub', force=True)
    subsub = base.create(opj('sub', 'subsub'), force=True)
    base.save(recursive=True)
    ok_clean_git(base.path)
    base.aggregate_metadata(recursive=True, update_mode='all')
    ok_clean_git(base.path)
    objpath = opj('.datalad', 'metadata', 'objects')
    objs = list(sorted(base.repo.find(objpath)))
    # we have 3x2 metadata sets (dataset/files) under annex
    eq_(len(objs), 6)
    eq_(all(base.repo.file_has_content(objs)), True)
    # drop all object content
    base.drop(objs, check=False)
    eq_(all(base.repo.file_has_content(objs)), False)
    ok_clean_git(base.path)
    # now re-aggregate, the state hasn't changed, so the file names will
    # be the same
    base.aggregate_metadata(recursive=True, update_mode='all', force_extraction=True)
    eq_(all(base.repo.file_has_content(objs)), True)
    # and there are no new objects
    eq_(
        objs,
        list(sorted(base.repo.find(objpath)))
    )


@with_tree(tree=_dataset_hierarchy_template)
@with_tempfile(mkdir=True)
def test_aggregate_with_unavailable_objects_from_subds(path, target):
    base = Dataset(opj(path, 'origin')).create(force=True)
    # force all metadata objects into the annex
    with open(opj(base.path, '.datalad', '.gitattributes'), 'w') as f:
        f.write(
            '** annex.largefiles=nothing\nmetadata/objects/** annex.largefiles=anything\n')
    sub = base.create('sub', force=True)
    subsub = base.create(opj('sub', 'subsub'), force=True)
    base.save(recursive=True)
    ok_clean_git(base.path)
    base.aggregate_metadata(recursive=True, update_mode='all')
    ok_clean_git(base.path)

    # now make that a subdataset of a new one, so aggregation needs to get the
    # metadata objects first:
    super = Dataset(target).create()
    super.install("base", source=base.path)
    ok_clean_git(super.path)
    clone = Dataset(opj(super.path, "base"))
    ok_clean_git(clone.path)
    objpath = opj('.datalad', 'metadata', 'objects')
    objs = [o for o in sorted(clone.repo.get_annexed_files(with_content_only=False)) if o.startswith(objpath)]
    eq_(len(objs), 6)
    eq_(all(clone.repo.file_has_content(objs)), False)

    # now aggregate should get those metadata objects
    super.aggregate_metadata(recursive=True, update_mode='all',
                             force_extraction=False)
    eq_(all(clone.repo.file_has_content(objs)), True)


# this is for gh-1987
@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_tree(tree=_dataset_hierarchy_template)
def test_publish_aggregated(path):
    base = Dataset(opj(path, 'origin')).create(force=True)
    # force all metadata objects into the annex
    with open(opj(base.path, '.datalad', '.gitattributes'), 'w') as f:
        f.write(
            '** annex.largefiles=nothing\nmetadata/objects/** annex.largefiles=anything\n')
    base.create('sub', force=True)
    base.save(recursive=True)
    ok_clean_git(base.path)
    base.aggregate_metadata(recursive=True, update_mode='all')
    ok_clean_git(base.path)

    # create sibling and publish to it
    spath = opj(path, 'remote')
    base.create_sibling(
        name="local_target",
        sshurl="ssh://localhost",
        target_dir=spath)
    base.publish('.', to='local_target', transfer_data='all')
    remote = Dataset(spath)
    objpath = opj('.datalad', 'metadata', 'objects')
    objs = list(sorted(base.repo.find(objpath)))
    # all object files a present in both datasets
    eq_(all(base.repo.file_has_content(objs)), True)
    eq_(all(remote.repo.file_has_content(objs)), True)
    # and we can squeeze the same metadata out
    eq_(
        [{k: v for k, v in i.items() if k not in ('path', 'refds', 'parentds')}
         for i in base.metadata('sub')],
        [{k: v for k, v in i.items() if k not in ('path', 'refds', 'parentds')}
         for i in remote.metadata('sub')],
    )


def _get_contained_objs(ds):
    return set(f for f in ds.repo.get_indexed_files()
               if f.startswith(opj('.datalad', 'metadata', 'objects', '')))


def _get_referenced_objs(ds):
    return set([op.relpath(r[f], start=ds.path)
                for r in ds.metadata(get_aggregates=True)
                for f in ('content_info', 'dataset_info')])


@with_tree(tree=_dataset_hierarchy_template)
def test_aggregate_removal(path):
    base = Dataset(opj(path, 'origin')).create(force=True)
    # force all metadata objects into the annex
    with open(opj(base.path, '.datalad', '.gitattributes'), 'w') as f:
        f.write(
            '** annex.largefiles=nothing\nmetadata/objects/** annex.largefiles=anything\n')
    sub = base.create('sub', force=True)
    subsub = sub.create(opj('subsub'), force=True)
    base.save(recursive=True)
    base.aggregate_metadata(recursive=True, update_mode='all')
    ok_clean_git(base.path)
    res = base.metadata(get_aggregates=True)
    assert_result_count(res, 3)
    assert_result_count(res, 1, path=subsub.path)
    # check that we only have object files that are listed in agginfo
    eq_(_get_contained_objs(base), _get_referenced_objs(base))
    # now delete the deepest subdataset to test cleanup of aggregated objects
    # in the top-level ds
    base.remove(opj('sub', 'subsub'), check=False)
    # now aggregation has to detect that subsub is not simply missing, but gone
    # for good
    base.aggregate_metadata(recursive=True, update_mode='all')
    ok_clean_git(base.path)
    # internally consistent state
    eq_(_get_contained_objs(base), _get_referenced_objs(base))
    # info on subsub was removed at all levels
    res = base.metadata(get_aggregates=True)
    assert_result_count(res, 0, path=subsub.path)
    assert_result_count(res, 2)
    res = sub.metadata(get_aggregates=True)
    assert_result_count(res, 0, path=subsub.path)
    assert_result_count(res, 1)


@with_tree(tree=_dataset_hierarchy_template)
def test_update_strategy(path):
    base = Dataset(opj(path, 'origin')).create(force=True)
    # force all metadata objects into the annex
    with open(opj(base.path, '.datalad', '.gitattributes'), 'w') as f:
        f.write(
            '** annex.largefiles=nothing\nmetadata/objects/** annex.largefiles=anything\n')
    sub = base.create('sub', force=True)
    subsub = sub.create(opj('subsub'), force=True)
    base.save(recursive=True)
    ok_clean_git(base.path)
    # we start clean
    for ds in base, sub, subsub:
        eq_(len(_get_contained_objs(ds)), 0)
    # aggregate the base dataset only, nothing below changes
    base.aggregate_metadata()
    eq_(len(_get_contained_objs(base)), 2)
    for ds in sub, subsub:
        eq_(len(_get_contained_objs(ds)), 0)
    # aggregate the entire tree, but by default only updates
    # the top-level dataset with all objects, none of the leaf
    # or intermediate datasets get's touched
    base.aggregate_metadata(recursive=True)
    eq_(len(_get_contained_objs(base)), 6)
    eq_(len(_get_referenced_objs(base)), 6)
    for ds in sub, subsub:
        eq_(len(_get_contained_objs(ds)), 0)
    res = base.metadata(get_aggregates=True)
    assert_result_count(res, 3)
    # it is impossible to query an intermediate or leaf dataset
    # for metadata
    for ds in sub, subsub:
        assert_status(
            'impossible',
            ds.metadata(get_aggregates=True, on_failure='ignore'))
    # get the full metadata report
    target_meta = base.metadata(return_type='list')

    # now redo full aggregation, this time updating all
    # (intermediate) datasets
    base.aggregate_metadata(recursive=True, update_mode='all')
    eq_(len(_get_contained_objs(base)), 6)
    eq_(len(_get_contained_objs(sub)), 4)
    eq_(len(_get_contained_objs(subsub)), 2)
    # it is now OK to query an intermediate or leaf dataset
    # for metadata
    for ds in sub, subsub:
        assert_status(
            'ok',
            ds.metadata(get_aggregates=True, on_failure='ignore'))

    # all of that has no impact on the reported metadata
    eq_(target_meta, base.metadata(return_type='list'))


@with_tree({
    'this': 'that',
    'sub1': {'here': 'there'},
    'sub2': {'down': 'under'}})
def test_partial_aggregation(path):
    ds = Dataset(path).create(force=True)
    sub1 = ds.create('sub1', force=True)
    sub2 = ds.create('sub2', force=True)
    ds.save(recursive=True)

    # if we aggregate a path(s) and say to recurse, we must not recurse into
    # the dataset itself and aggregate others
    ds.aggregate_metadata(path='sub1', recursive=True)
    res = ds.metadata(get_aggregates=True)
    assert_result_count(res, 1, path=ds.path)
    assert_result_count(res, 1, path=sub1.path)
    # so no metadata aggregates for sub2 yet
    assert_result_count(res, 0, path=sub2.path)

    ds.aggregate_metadata(recursive=True)
    # baseline, recursive aggregation gets us something for all three datasets
    res = ds.metadata(get_aggregates=True)
    assert_result_count(res, 3)
    # now let's do partial aggregation from just one subdataset
    # we should not loose information on the other datasets
    # as this would be a problem any time anything in a dataset
    # subtree is missing: not installed, too expensive to reaggregate, ...
    ds.aggregate_metadata(path='sub1', incremental=True)
    res = ds.metadata(get_aggregates=True)
    assert_result_count(res, 3)
    assert_result_count(res, 1, path=sub2.path)
    # from-scratch aggregation kills datasets that where not listed
    ds.aggregate_metadata(path='sub1', incremental=False)
    res = ds.metadata(get_aggregates=True)
    assert_result_count(res, 3)
    assert_result_count(res, 1, path=sub2.path)
    # now reaggregated in full
    ds.aggregate_metadata(recursive=True)
    # make change in sub1
    sub1.unlock('here')
    with open(opj(sub1.path, 'here'), 'w') as f:
        f.write('fresh')
    ds.save(recursive=True)
    ok_clean_git(path)
    # TODO for later
    # test --since with non-incremental
    #ds.aggregate_metadata(recursive=True, since='HEAD~1', incremental=False)
    #res = ds.metadata(get_aggregates=True)
    #assert_result_count(res, 3)
    #assert_result_count(res, 1, path=sub2.path)
