# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test meta data """

import logging
import pickle
import os

from mock import patch
from operator import itemgetter
from os.path import join as opj, exists

from datalad.api import Dataset, aggregate_metadata, install
from datalad.metadata import get_metadata_type, get_metadata
from datalad.metadata import _cached_load_document
from datalad.metadata import _sanitize_annex_description
from datalad.utils import swallow_logs
from datalad.utils import chpwd
from datalad.utils import assure_unicode
from datalad.utils import assure_list
from datalad.dochelpers import exc_str
from datalad.tests.utils import with_tree, with_tempfile
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_in
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import skip_if_no_network
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose import SkipTest
from nose.tools import assert_true, assert_equal, assert_raises, assert_false

try:
    import pyld
    # do here to prevent pyld from being needed
except ImportError as exc:
    raise SkipTest(exc_str(exc))

from datalad.api import search

_dataset_hierarchy_template = {
    'origin': {
        'dataset_description.json': """
{
    "Name": "mother_äöü東"
}""",
        'datapackage.json': """
{
    "name": "MOTHER_äöü東",
    "keywords": ["example", "multitype metadata"]
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


@with_tempfile(mkdir=True)
def test_get_metadata_type(path):
    # nothing set, nothing found
    assert_equal(get_metadata_type(Dataset(path)), [])
    os.makedirs(opj(path, '.datalad'))
    # got section, but no setting
    open(opj(path, '.datalad', 'config'), 'w').write('[metadata]\n')
    assert_equal(get_metadata_type(Dataset(path)), [])
    # minimal setting
    open(opj(path, '.datalad', 'config'), 'w+').write('[metadata]\nnativetype = mamboschwambo\n')
    assert_equal(get_metadata_type(Dataset(path)), ['mamboschwambo'])


@with_tree(tree={
    'dataset_description.json': "{}",
    'datapackage.json': '{"name": "some"}'
})
def test_get_multiple_metadata_types(path):
    assert_equal(
        sorted(get_metadata_type(Dataset(path), guess=True)),
        ['bids', 'frictionless_datapackage'])


@with_tree(tree={
    'origin': {
        'dataset_description.json': """
{
    "Name": "the mother"
}""",
    'sub': {
        'dataset_description.json': """
{
    "Name": "child"
}"""}}})
def test_basic_metadata(path):
    ds = Dataset(opj(path, 'origin'))
    meta = get_metadata(ds)
    assert_equal(sorted(meta[0].keys()),
                 ['@context', 'dcterms:conformsTo'])
    ds.create(force=True, save=False)
    # with subdataset
    sub = ds.create('sub', force=True)
    ds.save()
    meta = get_metadata(ds)
    assert_equal(
        sorted(meta[0].keys()),
        ['@context', '@id', 'availableFrom', 'dcterms:conformsTo',
         'dcterms:modified', 'type', 'version'])
    assert_equal(meta[0]['type'], 'Dataset')
    # clone and get relationship info in metadata
    sibling = install(
        opj(path, 'sibling'), source=opj(path, 'origin'),
        result_xfm='datasets', return_type='item-or-list')
    sibling_meta = get_metadata(sibling)
    assert_equal(sibling_meta[0]['@id'], ds.id)
    # origin should learn about the clone
    sibling.repo.push(remote='origin', refspec='git-annex')
    meta = get_metadata(ds)
    assert_equal([m['@id'] for m in meta[0]['availableFrom']],
                 [m['@id'] for m in sibling_meta[0]['availableFrom']])
    meta = get_metadata(ds, guess_type=True)
    # without aggregation there is not trace of subdatasets in the metadata
    assert_not_in('dcterms:hasPart', meta[0])


@skip_if_no_network
@with_tree(tree=_dataset_hierarchy_template)
def test_aggregation(path):
    with chpwd(path):
        assert_raises(InsufficientArgumentsError, aggregate_metadata, None)
    # a hierarchy of three (super/sub)datasets, each with some native metadata
    ds = Dataset(opj(path, 'origin')).create(force=True)
    subds = ds.create('sub', force=True)
    subsubds = subds.create('subsub', force=True)
    # aggregate from bottom to top, guess native data, no compacting of graph
    # should yield 6 meta data sets, one implicit, and one native per dataset
    # and a second natiev set for the topmost dataset
    aggregate_metadata(ds, guess_native_type=True, recursive=True)
    # no only ask the top superdataset, no recursion, just reading from the cache
    meta = get_metadata(
        ds, guess_type=False, ignore_subdatasets=False, ignore_cache=False)
    assert_equal(len(meta), 10)
    # same schema
    assert_equal(
        10,
        sum([s.get('@context', {'@vocab': None})['@vocab'] == 'http://schema.org/'
             for s in meta]))
    # three different IDs
    assert_equal(3, len(set([s.get('@id') for s in meta])))
    # and we know about all three datasets
    for name in ('mother_äöü東', 'child_äöü東', 'grandchild_äöü東'):
        assert_true(sum([s.get('name', None) == assure_unicode(name) for s in meta]))
    #print(meta)
    assert_equal(
        # first implicit, then two natives, then aggregate
        meta[3]['dcterms:hasPart']['@id'],
        subds.id)
    success = False
    for m in meta:
        p = m.get('dcterms:hasPart', {})
        if p.get('@id', None) == subsubds.id:
            assert_equal(opj('sub', 'subsub'), p.get('location', None))
            success = True
    assert_true(success)

    # save the toplevel dataset only (see below)
    ds.save('with aggregated meta data')

    # now clone the beast to simulate a new user installing an empty dataset
    clone = install(
        opj(path, 'clone'), source=ds.path,
        result_xfm='datasets', return_type='item-or-list')
    # ID mechanism works
    assert_equal(ds.id, clone.id)

    # get fresh meta data, the implicit one for the top-most datasets should
    # differ, but the rest not
    clonemeta = get_metadata(
        clone, guess_type=False, ignore_subdatasets=False, ignore_cache=False)

    for m in clonemeta:
        # could be a list or a single entry
        for r in assure_list(m.get('availableFrom', []), iterate=False):
            # if there is a description, it shouldn't have any [ in it
            # (enabled state should have been pruned, local remote name pruned)
            assert_not_in('[', r.get('description', ''))

    # make sure the implicit md for the topmost come first
    assert_equal(clonemeta[0]['@id'], clone.id)
    assert_equal(clonemeta[0]['@id'], ds.id)
    assert_equal(clone.repo.get_hexsha(), ds.repo.get_hexsha())
    assert_equal(clonemeta[0]['version'], ds.repo.get_hexsha())
    # all but the implicit is identical
    assert_equal(clonemeta[1:], meta[1:])
    # the implicit md of the clone should list a dataset ID for its subds,
    # although it has not been obtained!
    assert_equal(
        clonemeta[3]['dcterms:hasPart']['@id'],
        subds.id)

    # now obtain a subdataset in the clone and the IDs should be updated
    clone.install('sub')
    partial = get_metadata(clone, guess_type=False, ignore_cache=True)
    # ids don't change
    assert_equal(partial[0]['@id'], clonemeta[0]['@id'])
    # datasets are properly connected
    assert_equal(partial[1]['dcterms:hasPart']['@id'],
                 partial[2]['@id'])

    # query smoke test
    if os.environ.get('DATALAD_TESTS_NONETWORK'):
        raise SkipTest

    assert_equal(len(list(clone.search('mother'))), 1)
    assert_equal(len(list(clone.search('MoTHER'))), 1)  # case insensitive

    child_res = list(clone.search('child'))
    assert_equal(len(child_res), 2)

    # little helper to match names
    def assert_names(res, names, path=clone.path):
        assert_equal(list(map(itemgetter(0), res)),
                     [opj(path, n) for n in names])
    # should yield (location, report) tuples
    assert_names(child_res, ['sub', 'sub/subsub'])

    # test searching among specified properties only
    assert_names(clone.search('i', search='name'), ['sub', 'sub/subsub'])
    assert_names(clone.search('i', search='keywords'), ['.'])
    # case shouldn't matter
    assert_names(clone.search('i', search='Keywords'), ['.'])
    assert_names(clone.search('i', search=['name', 'keywords']),
                 ['.', 'sub', 'sub/subsub'])

    # without report_matched, we are getting none of the fields
    assert(all([not x for x in map(itemgetter(1), child_res)]))
    # but we would get all if asking for '*'
    assert(all([len(x) >= 9
                for x in map(itemgetter(1),
                             list(clone.search('child', report='*')))]))
    # but we would get only the matching name if we ask for report_matched
    assert_equal(
        set(map(lambda x: tuple(x[1].keys()),
                clone.search('child', report_matched=True))),
        set([('name',)])
    )
    # and the additional field we might have asked with report
    assert_equal(
        set(map(lambda x: tuple(sorted(x[1].keys())),
                clone.search('child', report_matched=True,
                             report=['schema:type']))),
        set([('name', 'schema:type')])
    )
    # and if we ask report to be 'empty', we should get no fields
    child_res_empty = list(clone.search('child', report=''))
    assert_equal(len(child_res_empty), 2)
    assert_equal(
        set(map(lambda x: tuple(x[1].keys()), child_res_empty)),
        set([tuple()])
    )

    # more tests on returned paths:
    assert_names(clone.search('datalad'), ['.', 'sub', 'sub/subsub'])
    # if we clone subdataset and query for value present in it and its kid
    clone_sub = clone.install(
        'sub',
        result_xfm='datasets', return_type='item-or-list')
    assert_names(clone_sub.search('datalad'), ['.', 'subsub'], clone_sub.path)

    # Test 'and' for multiple search entries
    assert_equal(len(list(clone.search(['child', 'bids']))), 2)
    assert_equal(len(list(clone.search(['child', 'subsub']))), 1)
    assert_equal(len(list(clone.search(['bids', 'sub']))), 2)

    res = list(clone.search('.*', regex=True))  # with regex
    assert_equal(len(res), 3)  # one per dataset

    # we do search, not match
    assert_equal(len(list(clone.search('randchild', regex=True))), 1)
    assert_equal(len(list(clone.search(['gr.nd', 'ch.ld'], regex=True))), 1)
    assert_equal(len(list(clone.search('randchil.', regex=True))), 1)
    assert_equal(len(list(clone.search('^randchild.*', regex=True))), 0)
    assert_equal(len(list(clone.search('^grandchild.*', regex=True))), 1)
    assert_equal(len(list(clone.search('grandchild'))), 1)


    #TODO update the clone or reclone to check whether saved meta data comes down the pipe


@skip_if_no_network
@with_tree(tree=_dataset_hierarchy_template)
def test_aggregate_with_missing_or_duplicate_id(path):
    # a hierarchy of three (super/sub)datasets, each with some native metadata
    ds = Dataset(opj(path, 'origin')).create(force=True)
    subds = ds.create('sub', force=True)
    subds.create('subsub', force=True)
    # aggregate from bottom to top, guess native data, no compacting of graph
    # should yield 6 meta data sets, one implicit, and one native per dataset
    # and a second native set for the topmost dataset
    aggregate_metadata(ds, guess_native_type=True, recursive=True)
    # no only ask the top superdataset, no recursion, just reading from the cache
    meta = get_metadata(
        ds, guess_type=False, ignore_subdatasets=False, ignore_cache=False)
    # and we know nothing subsub
    for name in ('grandchild_äöü東',):
        assert_true(sum([s.get('name', '') == assure_unicode(name) for s in meta]))

    # but search should not fail
    with swallow_outputs():
        res1 = list(search('.', regex=True, dataset=ds))
    assert res1

    # and let's see now if we wouldn't fail if dataset is duplicate if we
    # install the same dataset twice
    subds_clone = ds.install(
        source=subds.path, path="subds2",
        result_xfm='datasets', return_type='item-or-list')
    with swallow_outputs():
        res2 = list(search('.', regex=True, dataset=ds))
    # TODO: bring back when meta data RF is complete with aggregate
    #assert_equal(len(res1) + 1, len(res2))
    #assert_equal(
    #    set(map(itemgetter(0), res1)).union({subds_clone.path}),
    #    set(map(itemgetter(0), res2)))


@with_tempfile(mkdir=True)
def test_cached_load_document(tdir):

    target_schema = {'buga': 'duga'}
    cache_filename = opj(tdir, "crap")

    with open(cache_filename, 'wb') as f:
        f.write("CRAPNOTPICKLED".encode())

    with patch('datalad.support.network.get_url_cache_filename',
               return_value=cache_filename):
        with patch('pyld.jsonld.load_document', return_value=target_schema), \
            swallow_logs(new_level=logging.WARNING) as cml:
            schema = _cached_load_document("http://schema.org/")
            assert_equal(schema, target_schema)
            cml.assert_logged("cannot load cache from", level="WARNING")

        # but now pickled one should have been saved
        assert_equal(pickle.load(open(cache_filename, 'rb')), target_schema)

        # and if we reload it -- it should be all fine without warnings
        # should come from cache so no need to overload load_document
        with swallow_logs(new_level=logging.WARNING) as cml:
            schema = _cached_load_document("http://schema.org/")
            assert_equal(schema, target_schema)
            assert_not_in("cannot load cache from", cml.out)


@with_tempfile(mkdir=True)
def test_ignore_nondatasets(path):
    # we want to ignore the version/commits for this test
    def _kill_time(meta):
        for m in meta:
            for k in ('version', 'dcterms:modified'):
                if k in m:
                    del m[k]
        return meta

    ds = Dataset(path).create()
    meta = _kill_time(get_metadata(ds))
    n_subm = 0
    # placing another repo in the dataset has no effect on metadata
    for cls, subpath in ((GitRepo, 'subm'), (AnnexRepo, 'annex_subm')):
        subm_path = opj(ds.path, subpath)
        r = cls(subm_path, create=True)
        with open(opj(subm_path, 'test'), 'w') as f:
            f.write('test')
        r.add('test')
        r.commit('some')
        assert_true(Dataset(subm_path).is_installed())
        assert_equal(meta, _kill_time(get_metadata(ds)))
        # making it a submodule has no effect either
        ds.add(subpath)
        assert_equal(len(ds.subdatasets()), n_subm + 1)
        assert_equal(meta, _kill_time(get_metadata(ds)))
        n_subm += 1


def test_sanitize_annex_description():
    assert_equal(_sanitize_annex_description("[d-a]"), "d-a")
    assert_equal(_sanitize_annex_description("d-a"), "d-a")
    assert_equal(_sanitize_annex_description("lo c [d-a]"), "lo c")
    assert_equal(_sanitize_annex_description("lo c"), "lo c")
