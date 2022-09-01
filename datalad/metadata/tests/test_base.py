# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test metadata """

import logging
import os.path as op
from os.path import join as opj
from os.path import relpath

from datalad.api import (
    Dataset,
    aggregate_metadata,
    install,
    metadata,
)
from datalad.metadata.metadata import (
    _get_containingds_from_agginfo,
    get_metadata_type,
    legacy_query_aggregated_metadata,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    InsufficientArgumentsError,
    NoDatasetFound,
)
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    assert_dict_equal,
    assert_equal,
    assert_in,
    assert_in_results,
    assert_raises,
    assert_re_in,
    assert_repo_status,
    assert_result_count,
    assert_status,
    assert_true,
    eq_,
    known_failure_githubci_win,
    slow,
    swallow_logs,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    chpwd,
    ensure_unicode,
)

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
def test_get_metadata_type(path=None):
    ds = Dataset(path).create()
    # nothing set, nothing found
    assert_equal(get_metadata_type(ds), [])
    # got section, but no setting
    open(opj(path, '.datalad', 'config'), 'w').write('[datalad "metadata"]\n')
    # not relying on automagical pick up of changes done
    # by external powers to the config
    # see https://github.com/datalad/datalad/issues/4363 for more info
    ds.config.reload()
    assert_equal(get_metadata_type(ds), [])
    # minimal setting
    open(opj(path, '.datalad', 'config'), 'w+').write('[datalad "metadata"]\nnativetype = mamboschwambo\n')
    ds.config.reload()
    assert_equal(get_metadata_type(ds), 'mamboschwambo')


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


@known_failure_githubci_win
@slow  # ~16s
@with_tree(tree=_dataset_hierarchy_template)
def test_aggregation(path=None):
    with chpwd(path):
        assert_raises(InsufficientArgumentsError, aggregate_metadata, None)
    # a hierarchy of three (super/sub)datasets, each with some native metadata
    ds = Dataset(opj(path, 'origin')).create(force=True)
    # before anything aggregated we would get nothing and only a log warning
    with swallow_logs(new_level=logging.WARNING) as cml:
        assert_equal(list(legacy_query_aggregated_metadata('all', ds, [])), [])
    assert_re_in('.*Found no aggregated metadata.*update', cml.out)
    ds.config.add('datalad.metadata.nativetype', 'frictionless_datapackage',
                  scope='branch')
    subds = ds.create('sub', force=True)
    subds.config.add('datalad.metadata.nativetype', 'frictionless_datapackage',
                     scope='branch')
    subsubds = subds.create('subsub', force=True)
    subsubds.config.add('datalad.metadata.nativetype', 'frictionless_datapackage',
                        scope='branch')
    ds.save(recursive=True)
    assert_repo_status(ds.path)
    # aggregate metadata from all subdatasets into any superdataset, including
    # intermediate ones
    res = ds.aggregate_metadata(recursive=True, update_mode='all')
    # we get success report for both subdatasets and the superdataset,
    # and they get saved
    assert_result_count(res, 3, status='ok', action='aggregate_metadata')
    assert_in_results(res, action='save', status="ok")
    # nice and tidy
    assert_repo_status(ds.path)

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
                    == ensure_unicode(name) for s in origres
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
    # origin and make sure we get the extract same stuff from the clone
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
def test_ignore_nondatasets(path=None):
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
        ds.save(subpath)
        assert_equal(len(ds.subdatasets()), n_subm + 1)
        assert_equal(meta, _kill_time(ds.metadata(reporton='datasets', on_failure='ignore')))
        n_subm += 1


@with_tempfile(mkdir=True)
def test_get_aggregates_fails(path=None):
    with chpwd(path), assert_raises(NoDatasetFound):
        metadata(get_aggregates=True)
    ds = Dataset(path).create()
    res = ds.metadata(get_aggregates=True, on_failure='ignore')
    assert_result_count(res, 1, path=ds.path, status='impossible')


@with_tree({'dummy': 'content'})
@with_tempfile(mkdir=True)
def test_bf2458(src=None, dst=None):
    ds = Dataset(src).create(force=True)
    ds.save(to_git=False)

    # no clone (empty) into new dst
    clone = install(source=ds.path, path=dst)
    # content is not here
    eq_(clone.repo.whereis('dummy'), [ds.config.get('annex.uuid')])
    # check that plain metadata access does not `get` stuff
    clone.metadata('.', on_failure='ignore')
    eq_(clone.repo.whereis('dummy'), [ds.config.get('annex.uuid')])


@known_failure_githubci_win
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
