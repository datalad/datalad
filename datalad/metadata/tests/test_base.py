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

from operator import itemgetter
from six import PY2
from datalad.api import Dataset, aggregate_metadata, install
from datalad.metadata import get_metadata_type, get_metadata
from nose.tools import assert_true, assert_equal, assert_raises
from datalad.tests.utils import with_tree, with_tempfile
from datalad.utils import chpwd
from datalad.dochelpers import exc_str
import os
from os.path import join as opj
from datalad.support.exceptions import InsufficientArgumentsError
from nose import SkipTest


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
    assert_equal(get_metadata_type(Dataset(path)), None)
    os.makedirs(opj(path, '.datalad'))
    # got section, but no setting
    open(opj(path, '.datalad', 'config'), 'w').write('[metadata]\n')
    assert_equal(get_metadata_type(Dataset(path)), None)
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
                 ['@context', '@id', 'dcterms:conformsTo', 'type'])
    ds.create(force=True, save=False)
    # with subdataset
    sub = ds.create('sub', force=True, if_dirty='ignore')
    ds.save()
    meta = get_metadata(ds)
    assert_equal(
        sorted(meta[0].keys()),
        ['@context', '@id', 'availableFrom', 'dcterms:conformsTo',
         'dcterms:hasPart', 'dcterms:modified', 'type', 'version'])
    assert_equal(meta[0]['type'], 'Dataset')
    # clone and get relationship info in metadata
    sibling = install(opj(path, 'sibling'), source=opj(path, 'origin'))
    sibling_meta = get_metadata(sibling)
    assert_equal(sibling_meta[0]['@id'], ds.id)
    # origin should learn about the clone
    sibling.repo.push(remote='origin', refspec='git-annex')
    meta = get_metadata(ds)
    assert_equal([m['@id'] for m in meta[0]['availableFrom']],
                 [m['@id'] for m in sibling_meta[0]['availableFrom']])
    meta = get_metadata(ds, guess_type=True)
    assert_equal(meta[0]['dcterms:hasPart'],
                 {'@id': sub.id,
                  'type': 'Dataset',
                  'location': 'sub'})


@with_tree(tree=_dataset_hierarchy_template)
def test_aggregation(path):
    with chpwd(path):
        assert_raises(InsufficientArgumentsError, aggregate_metadata, None)
    # a hierarchy of three (super/sub)datasets, each with some native metadata
    ds = Dataset(opj(path, 'origin')).create(force=True)
    subds = ds.create('sub', force=True, if_dirty='ignore')
    subsubds = subds.create('subsub', force=True, if_dirty='ignore')
    # aggregate from bottom to top, guess native data, no compacting of graph
    # should yield 6 meta data sets, one implicit, and one native per dataset
    # and a second natiev set for the topmost dataset
    aggregate_metadata(ds, guess_native_type=True, recursive=True)
    # no only ask the top superdataset, no recursion, just reading from the cache
    meta = get_metadata(
        ds, guess_type=False, ignore_subdatasets=False, ignore_cache=False)
    assert_equal(len(meta), 7)
    # same schema
    assert_equal(
        7, sum([s.get('@context', None) == 'http://schema.org/' for s in meta]))
    # three different IDs
    assert_equal(3, len(set([s.get('@id') for s in meta])))
    # and we know about all three datasets
    for name in ('mother_äöü東', 'child_äöü東', 'grandchild_äöü東'):
        if PY2:
            assert_true(sum([s.get('name', None) == name.decode('utf-8') for s in meta]))
        else:
            assert_true(sum([s.get('name', None) == name for s in meta]))
    assert_equal(
        meta[0]['dcterms:hasPart']['@id'],
        subds.id)
    success = False
    for m in meta:
        p = m.get('dcterms:hasPart', {})
        if p.get('@id', None) == subsubds.id:
            assert_equal(opj('sub', 'subsub'), p.get('location', None))
            success = True
    assert_true(success)

    # save the toplevel dataset only (see below)
    ds.save('with aggregated meta data', auto_add_changes=True)

    # now clone the beast to simulate a new user installing an empty dataset
    clone = install(opj(path, 'clone'), source=ds.path)
    # ID mechanism works
    assert_equal(ds.id, clone.id)

    # get fresh meta data, the implicit one for the top-most datasets should
    # differ, but the rest not
    clonemeta = get_metadata(
        clone, guess_type=False, ignore_subdatasets=False, ignore_cache=False)

    # make sure the implicit md for the topmost come first
    assert_equal(clonemeta[0]['@id'], clone.id)
    assert_equal(clonemeta[0]['@id'], ds.id)
    assert_equal(clonemeta[0]['version'], ds.repo.get_hexsha())
    # all but the implicit is identical
    assert_equal(clonemeta[1:], meta[1:])
    # the implicit md of the clone should list a dataset ID for its subds,
    # although it has not been obtained!
    assert_equal(
        clonemeta[0]['dcterms:hasPart']['@id'],
        subds.id)

    # now obtain a subdataset in the clone and the IDs should be updated
    clone.install('sub')
    partial = get_metadata(clone, guess_type=False, ignore_cache=True)
    # ids don't change
    assert_equal(partial[0]['@id'], clonemeta[0]['@id'])
    # datasets are properly connected
    assert_equal(partial[0]['dcterms:hasPart']['@id'],
                 partial[1]['@id'])

    # query smoke test
    try:
        if os.environ.get('DATALAD_TESTS_NONETWORK'):
            raise SkipTest

        import pyld
        from datalad.api import search

        assert_equal(len(list(clone.search('mother'))), 1)
        assert_equal(len(list(clone.search('MoTHER'))), 1)  # case insensitive

        child_res = list(clone.search('child'))
        assert_equal(len(child_res), 2)
        # should yield (location, report) tuples
        assert_equal(list(map(itemgetter(0), child_res)), ['sub', 'sub/subsub'])

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
                                 report=['type']))),
            set([('name', 'type')])
        )
        # and if we ask report to be 'empty', we should get no fields
        child_res_empty = list(clone.search('child', report=''))
        assert_equal(len(child_res_empty), 2)
        assert_equal(
            set(map(lambda x: tuple(x[1].keys()), child_res_empty)),
            set([tuple()])
        )

        # more tests on returned paths:
        assert_equal(list(map(itemgetter(0),
                              clone.search('datalad'))),
                     ['.', 'sub', 'sub/subsub'])
        # if we clone subdataset and query for value present in it and its kid
        assert_equal(list(map(itemgetter(0),
                              clone.install('sub').search('datalad'))),
                     ['.', 'subsub'])

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

    # do here to prevent pyld from being needed
    except SkipTest:
        raise SkipTest
    except ImportError as exc:
        raise SkipTest(exc_str(exc))
    except pyld.jsonld.JsonLdError as exc:
        if PY2:
            raise
        #
        raise SkipTest(
            "pyld code is not ready for Python 3.5 it seems (see: #756): %s"
            % exc_str(exc)
        )
        pass

    #TODO update the clone or reclone to check whether saved meta data comes down the pipe
