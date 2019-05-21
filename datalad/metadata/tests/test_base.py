# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test metadata """

import logging

from os.path import join as opj
from os.path import relpath
import os.path as op

from datalad.api import Dataset
from datalad.api import aggregate_metadata
from datalad.api import install
from datalad.api import metadata
from datalad.metadata.metadata import (
    get_metadata_type,
    query_aggregated_metadata,
    _get_containingds_from_agginfo,
)
from datalad.utils import chpwd
from datalad.utils import assure_unicode
from datalad.tests.utils import with_tree, with_tempfile
from datalad.tests.utils import slow
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import assert_in
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import skip_direct_mode
from datalad.tests.utils import known_failure_direct_mode
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import ok_
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import assert_re_in
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import assert_true, assert_equal, assert_raises


_dataset_hierarchy_template = {
    'origin': {
        'datapackage.json': """
{
    "name": "MOTHER_äöü東",
    "keywords": ["example", "multitype metadata"]
}""",
    'sub': {
        'datapackage.json': """
{
    "name": "child_äöü東"
}""",
    'subsub': {
        'datapackage.json': """
{
    "name": "grandchild_äöü東"
}"""}}}}


@with_tempfile(mkdir=True)
def test_get_metadata_type(path):
    Dataset(path).create()
    # nothing set, nothing found
    assert_equal(get_metadata_type(Dataset(path)), [])
    # got section, but no setting
    open(opj(path, '.datalad', 'config'), 'w').write('[datalad "metadata"]\n')
    assert_equal(get_metadata_type(Dataset(path)), [])
    # minimal setting
    open(opj(path, '.datalad', 'config'), 'w+').write('[datalad "metadata"]\nnativetype = mamboschwambo\n')
    assert_equal(get_metadata_type(Dataset(path)), 'mamboschwambo')


def _compare_metadata_helper(origres, compds):
    for ores in origres:
        rpath = relpath(ores['path'], ores['refds'])
        cres = compds.metadata(
            rpath,
            reporton='{}s'.format(ores['type']))
        if ores['type'] == 'file':
            # TODO implement file based lookup
            continue
        assert_result_count(cres, 1)
        cres = cres[0]
        assert_dict_equal(ores['metadata'], cres['metadata'])
        if ores['type'] == 'dataset':
            for i in ('dsid', ):
                eq_(ores[i], cres[i])


@known_failure_direct_mode  #FIXME
@slow  # ~16s
@with_tree(tree=_dataset_hierarchy_template)
def test_aggregation(path):
    with chpwd(path):
        assert_raises(InsufficientArgumentsError, aggregate_metadata, None)
    # a hierarchy of three (super/sub)datasets, each with some native metadata
    ds = Dataset(opj(path, 'origin')).create(force=True)
    # before anything aggregated we would get nothing and only a log warning
    with swallow_logs(new_level=logging.WARNING) as cml:
        assert_equal(list(query_aggregated_metadata('all', ds, [])), [])
    assert_re_in('.*Found no aggregated metadata.*update', cml.out)
    ds.config.add('datalad.metadata.nativetype', 'frictionless_datapackage',
                  where='dataset')
    subds = ds.create('sub', force=True)
    subds.config.add('datalad.metadata.nativetype', 'frictionless_datapackage',
                     where='dataset')
    subsubds = subds.create('subsub', force=True)
    subsubds.config.add('datalad.metadata.nativetype', 'frictionless_datapackage',
                        where='dataset')
    ds.add('.', recursive=True)
    ok_clean_git(ds.path)
    # aggregate metadata from all subdatasets into any superdataset, including
    # intermediate ones
    res = ds.aggregate_metadata(recursive=True, update_mode='all')
    # we get success report for both subdatasets and the superdataset,
    # and they get saved
    assert_result_count(res, 6)
    assert_result_count(res, 3, status='ok', action='aggregate_metadata')
    assert_result_count(res, 3, status='ok', action='save')
    # nice and tidy
    ok_clean_git(ds.path)

    # quick test of aggregate report
    aggs = ds.metadata(get_aggregates=True)
    # one for each dataset
    assert_result_count(aggs, 3)
    # mother also report layout version
    assert_result_count(aggs, 1, path=ds.path, layout_version=1)

    # store clean direct result
    origres = ds.metadata(recursive=True)
    # basic sanity check
    assert_result_count(origres, 6)
    assert_result_count(origres, 3, type='dataset')
    assert_result_count(origres, 3, type='file')  # Now that we have annex.key
    # three different IDs
    assert_equal(3, len(set([s['dsid'] for s in origres if s['type'] == 'dataset'])))
    # and we know about all three datasets
    for name in ('MOTHER_äöü東', 'child_äöü東', 'grandchild_äöü東'):
        assert_true(
            sum([s['metadata']['frictionless_datapackage']['name'] \
                    == assure_unicode(name) for s in origres
                 if s['type'] == 'dataset']))

    # now clone the beast to simulate a new user installing an empty dataset
    clone = install(
        opj(path, 'clone'), source=ds.path,
        result_xfm='datasets', return_type='item-or-list')
    # ID mechanism works
    assert_equal(ds.id, clone.id)

    # get fresh metadata
    cloneres = clone.metadata()
    # basic sanity check
    assert_result_count(cloneres, 2)
    assert_result_count(cloneres, 1, type='dataset')
    assert_result_count(cloneres, 1, type='file')

    # now loop over the previous results from the direct metadata query of
    # origin and make sure we get the extact same stuff from the clone
    _compare_metadata_helper(origres, clone)

    # now obtain a subdataset in the clone, should make no difference
    assert_status('ok', clone.install('sub', result_xfm=None, return_type='list'))
    _compare_metadata_helper(origres, clone)

    # test search in search tests, not all over the place
    ## query smoke test
    assert_result_count(clone.search('mother', mode='egrep'), 1)
    assert_result_count(clone.search('(?i)MoTHER', mode='egrep'), 1)

    child_res = clone.search('child', mode='egrep')
    assert_result_count(child_res, 2)
    for r in child_res:
        if r['type'] == 'dataset':
            assert_in(
                r['query_matched']['frictionless_datapackage.name'],
                r['metadata']['frictionless_datapackage']['name'])

    ## Test 'and' for multiple search entries
    #assert_result_count(clone.search(['*child*', '*bids*']), 2)
    #assert_result_count(clone.search(['*child*', '*subsub*']), 1)
    #assert_result_count(clone.search(['*bids*', '*sub*']), 2)

    #assert_result_count(clone.search(['*', 'type:dataset']), 3)

    ##TODO update the clone or reclone to check whether saved metadata comes down the pipe


@with_tempfile(mkdir=True)
def test_ignore_nondatasets(path):
    # we want to ignore the version/commits for this test
    def _kill_time(meta):
        for m in meta:
            for k in ('version', 'shasum'):
                if k in m:
                    del m[k]
        return meta

    ds = Dataset(path).create()
    meta = _kill_time(ds.metadata(reporton='datasets', on_failure='ignore'))
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
        assert_equal(meta, _kill_time(ds.metadata(reporton='datasets', on_failure='ignore')))
        # making it a submodule has no effect either
        ds.add(subpath)
        assert_equal(len(ds.subdatasets()), n_subm + 1)
        assert_equal(meta, _kill_time(ds.metadata(reporton='datasets', on_failure='ignore')))
        n_subm += 1


@with_tempfile(mkdir=True)
def test_get_aggregates_fails(path):
    with chpwd(path), assert_raises(NoDatasetArgumentFound):
        metadata(get_aggregates=True)
    ds = Dataset(path).create()
    res = ds.metadata(get_aggregates=True, on_failure='ignore')
    assert_result_count(res, 1, path=ds.path, status='impossible')


@with_tree({'dummy': 'content'})
@with_tempfile(mkdir=True)
def test_bf2458(src, dst):
    ds = Dataset(src).create(force=True)
    ds.add('.', to_git=False)

    # no clone (empty) into new dst
    clone = install(source=ds.path, path=dst)
    # XXX whereis says nothing in direct mode
    # content is not here
    eq_(clone.repo.whereis('dummy'), [ds.config.get('annex.uuid')])
    # check that plain metadata access does not `get` stuff
    clone.metadata('.', on_failure='ignore')
    # XXX whereis says nothing in direct mode
    eq_(clone.repo.whereis('dummy'), [ds.config.get('annex.uuid')])


def test_get_containingds_from_agginfo():
    eq_(None, _get_containingds_from_agginfo({}, 'any'))
    # direct hit returns itself
    eq_('match', _get_containingds_from_agginfo({'match': {}, 'other': {}}, 'match'))
    # matches
    down = op.join('match', 'down')
    eq_('match', _get_containingds_from_agginfo({'match': {}}, down))
    # closest match
    down_under = op.join(down, 'under')
    eq_(down, _get_containingds_from_agginfo({'match': {}, down: {}}, down_under))
    # absolute works too
    eq_(op.abspath(down),
        _get_containingds_from_agginfo(
            {op.abspath('match'): {}, op.abspath(down): {}}, op.abspath(down_under)))
    # will not tollerate mix'n'match
    assert_raises(ValueError, _get_containingds_from_agginfo, {'match': {}}, op.abspath(down))
    assert_raises(ValueError, _get_containingds_from_agginfo, {op.abspath('match'): {}}, down)
