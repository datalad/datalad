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


from os.path import join as opj

from datalad.api import metadata
from datalad.distribution.dataset import Dataset


from datalad.tests.utils import with_tree
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_equal
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import skip_direct_mode
from ..parsers.tests.test_bids import bids_template


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
@skip_direct_mode  #FIXME
def test_basic_aggregate(path):
    # TODO give datasets some more metadata to actually aggregate stuff
    base = Dataset(opj(path, 'origin')).create(force=True)
    sub = base.create('sub', force=True)
    #base.metadata(sub.path, init=dict(homepage='this'), apply2global=True)
    subsub = base.create(opj('sub', 'subsub'), force=True)
    base.add('.', recursive=True)
    ok_clean_git(base.path)
    base.aggregate_metadata(recursive=True)
    ok_clean_git(base.path)
    direct_meta = base.metadata(recursive=True, return_type='list')
    # loose the deepest dataset
    sub.uninstall('subsub', check=False)
    # no we should eb able to reaggregate metadata, and loose nothing
    # because we can aggregate aggregated metadata of subsub from sub
    base.aggregate_metadata(recursive=True)
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
    res = ds.metadata(reporton='datasets')
    assert_result_count(res, 1)
    _assert_metadata_empty(res[0]['metadata'])
    # but we can now ask for metadata of stuff that is unknown on disk
    res = ds.metadata(opj('sub', 'deep', 'some'), reporton='datasets')
    assert_result_count(res, 1)
    eq_({'homepage': 'http://top.example.com'}, res[0]['metadata'])
    # and the command will report the aggregated metadata as it is recorded
    # in the dataset that is the closest parent on disk
    ds.create('sub', force=True)
    # same call as above, different result!
    res = ds.metadata(opj('sub', 'deep', 'some'), reporton='datasets')
    assert_result_count(res, 1)
    eq_({'homepage': 'http://sub.example.com'}, res[0]['metadata'])


@with_tree(tree=bids_template)
def test_nested_metadata(path):
    ds = Dataset(path).create(force=True)
    ds.add('.')
    ds.aggregate_metadata()
    # BIDS returns participant info as a nested dict for each file in the
    # content metadata. On the dataset-level this should automatically
    # yield a sequence of participant info dicts, without any further action
    # or BIDS-specific configuration
    meta = ds.metadata('.', reporton='datasets', return_type='item-or-list')['metadata']
    assert_equal(
        meta['datalad_unique_content_properties']['bids']['participant'],
        [
            {
                "age(years)": "20-25",
                "participant_id": "03",
                "gender": "female",
                "handedness": "r",
                "hearing_problems_current": "n"
            },
            {
                "age(years)": "30-35",
                "participant_id": "01",
                "gender": "male",
                "handedness": "r",
                "hearing_problems_current": "n"
            },
        ])
