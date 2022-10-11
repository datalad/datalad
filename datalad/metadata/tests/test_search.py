# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Some additional tests for search command (some are within test_base)"""

import logging
import os
from os import makedirs
from os.path import dirname
from os.path import join as opj
from pathlib import Path
from shutil import copy
from uuid import UUID
from pkg_resources import EntryPoint

import pytest
from unittest.mock import (
    MagicMock,
    patch,
)

from datalad.api import (
    Dataset,
    search,
)
from datalad.support.exceptions import NoDatasetFound
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_in,
    assert_is_generator,
    assert_raises,
    assert_re_in,
    assert_repo_status,
    assert_result_count,
    eq_,
    known_failure_githubci_win,
    ok_file_under_git,
    patch_config,
    with_tempfile,
    with_testsui,
)
from datalad.utils import (
    chpwd,
    swallow_logs,
    swallow_outputs,
)

from ..indexers.base import MetadataIndexer
from ..metadata import (
    NoMetadataStoreFound,
    gen4_query_aggregated_metadata,
    query_aggregated_metadata,
)
from ..search import (
    _listdict2dictlist,
    _meta2autofield_dict,
)


@with_testsui(interactive=False)
@with_tempfile(mkdir=True)
def test_search_outside1_noninteractive_ui(tdir=None):
    # we should raise an informative exception
    with chpwd(tdir):
        with assert_raises(NoDatasetFound) as cme:
            list(search("irrelevant"))
        assert_in('run interactively', str(cme.value))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_search_outside1(tdir=None, newhome=None):
    with chpwd(tdir):
        # should fail since directory exists, but not a dataset
        # should not even waste our response ;)
        with patch_config({'datalad.locations.default-dataset': newhome}):
            gen = search("irrelevant", return_type='generator')
            assert_is_generator(gen)
            assert_raises(NoDatasetFound, next, gen)

        # and if we point to some non-existing dataset
        with assert_raises(ValueError):
            next(search("irrelevant", dataset=newhome))


@with_testsui(responses='yes')
@with_tempfile(mkdir=True)
@with_tempfile()
def test_search_outside1_install_default_ds(tdir=None, default_dspath=None):
    with chpwd(tdir):
        # let's mock out even actual install/search calls
        with \
            patch_config({'datalad.locations.default-dataset': default_dspath}), \
            patch('datalad.api.install',
                  return_value=Dataset(default_dspath)) as mock_install, \
            patch('datalad.distribution.dataset.Dataset.search',
                  new_callable=_mock_search):
            _check_mocked_install(default_dspath, mock_install)

            # now on subsequent run, we want to mock as if dataset already exists
            # at central location and then do search again
            from datalad.ui import ui
            ui.add_responses('yes')
            mock_install.reset_mock()
            with patch(
                    'datalad.distribution.dataset.Dataset.is_installed',
                    True):
                _check_mocked_install(default_dspath, mock_install)

            # and what if we say "no" to install?
            ui.add_responses('no')
            mock_install.reset_mock()
            with assert_raises(NoDatasetFound):
                list(search("."))

            # and if path exists and is a valid dataset and we say "no"
            Dataset(default_dspath).create()
            ui.add_responses('no')
            mock_install.reset_mock()
            with assert_raises(NoDatasetFound):
                list(search("."))


_mocked_search_results = [
    {
        'action': 'search',
        'status': 'ok',
        'path': 'ds1',  # this is wrong and must be an abspath
        'matched': {'f': 'v'},  # this has nothing to do with the actual output
    },
    {
        'action': 'search',
        'status': 'ok',
        'path': 'd2/ds2',  # this is wrong and must be an abspath
        'matched': {'f1': 'v1'}  # this has nothing to do with the actual output,
    },
]


class _mock_search(object):
    def __call__(*args, **kwargs):
        for report in _mocked_search_results:
            yield report


def _check_mocked_install(default_dspath, mock_install):
    gen = search(".", return_type='generator')
    assert_is_generator(gen)
    # we no longer do any custom path tune up from the one returned by search
    # so should match what search returns
    assert_equal(
        list(gen), [report
                    for report in _mocked_search_results])
    mock_install.assert_called_once_with(
        default_dspath,
        source='///',
        result_renderer='disabled')


@with_tempfile
def test_search_non_dataset(tdir=None):
    from datalad.support.gitrepo import GitRepo
    GitRepo(tdir, create=True)
    with assert_raises(NoDatasetFound) as cme:
        list(search('smth', dataset=tdir))
    # Should instruct user how that repo could become a datalad dataset
    assert_in("datalad create --force", str(cme.value))


@known_failure_githubci_win
@with_tempfile(mkdir=True)
def test_within_ds_file_search(path=None):
    try:
        import mutagen
    except ImportError:
        raise SkipTest
    ds = Dataset(path).create(force=True)
    # override default and search for datasets and files for this test
    for m in ('egrep', 'textblob', 'autofield'):
        ds.config.add(
            'datalad.search.index-{}-documenttype'.format(m), 'all',
            scope='branch')
    ds.config.add('datalad.metadata.nativetype', 'audio', scope='branch')
    makedirs(opj(path, 'stim'))
    for src, dst in (
            ('audio.mp3', opj('stim', 'stim1.mp3')),):
        copy(
            opj(dirname(dirname(__file__)), 'tests', 'data', src),
            opj(path, dst))
    ds.save()
    ok_file_under_git(path, opj('stim', 'stim1.mp3'), annexed=True)
    # If it is not under annex, below addition of metadata silently does
    # not do anything
    ds.repo.set_metadata(
        opj('stim', 'stim1.mp3'), init={'importance': 'very'})
    ds.aggregate_metadata()
    assert_repo_status(ds.path)
    # basic sanity check on the metadata structure of the dataset
    dsmeta = ds.metadata('.', reporton='datasets')[0]['metadata']
    for src in ('audio',):
        # something for each one
        assert_in(src, dsmeta)
        # each src declares its own context
        assert_in('@context', dsmeta[src])
        # we have a unique content metadata summary for each src
        assert_in(src, dsmeta['datalad_unique_content_properties'])

    # test default behavior
    with swallow_outputs() as cmo:
        ds.search(show_keys='name', mode='textblob')

        assert_in("""\
id
meta
parentds
path
type
""", cmo.out)

    target_out = """\
annex.importance
annex.key
audio.bitrate
audio.duration(s)
audio.format
audio.music-Genre
audio.music-album
audio.music-artist
audio.music-channels
audio.music-sample_rate
audio.name
audio.tracknumber
datalad_core.id
datalad_core.refcommit
id
parentds
path
type
"""

    # test default behavior while limiting set of keys reported
    with swallow_outputs() as cmo:
        ds.search([r'\.id', 'artist$'], show_keys='short')
        out_lines = [l for l in cmo.out.split(os.linesep) if l]
        # test that only the ones matching were returned
        assert_equal(
            [l for l in out_lines if not l.startswith(' ')],
            ['audio.music-artist', 'datalad_core.id']
        )
        # more specific test which would also test formatting
        assert_equal(
            out_lines,
            ['audio.music-artist',
             ' in  1 datasets', " has 1 unique values: 'dlartist'",
             'datalad_core.id',
             ' in  1 datasets',
             # we have them sorted
             " has 1 unique values: '%s'" % ds.id
             ]
        )

    with assert_raises(ValueError) as cme:
        ds.search('*wrong')
    assert_re_in(
        r"regular expression '\(\?i\)\*wrong' \(original: '\*wrong'\) is incorrect: ",
        str(cme.value))

    # check generated autofield index keys
    with swallow_outputs() as cmo:
        ds.search(mode='autofield', show_keys='name')
        # it is impossible to assess what is different from that dump
        assert_in(target_out, cmo.out)

    assert_result_count(ds.search('blablob#'), 0)
    # now check that we can discover things from the aggregated metadata
    for mode, query, hitpath, matched in (
        ('egrep',
         ':mp3',
         opj('stim', 'stim1.mp3'),
         {'audio.format': 'mp3'}),
        # same as above, leading : is stripped, in indicates "ALL FIELDS"
        ('egrep',
         'mp3',
         opj('stim', 'stim1.mp3'),
         {'audio.format': 'mp3'}),
        # same as above, but with AND condition
        # get both matches
        ('egrep',
         ['mp3', 'type:file'],
         opj('stim', 'stim1.mp3'),
         {'type': 'file', 'audio.format': 'mp3'}),
        # case insensitive search
        ('egrep',
         'mp3',
         opj('stim', 'stim1.mp3'),
         {'audio.format': 'mp3'}),
        # field selection by expression
        ('egrep',
         r'audio\.+:mp3',
         opj('stim', 'stim1.mp3'),
         {'audio.format': 'mp3'}),
        # random keyword query
        ('textblob',
         'mp3',
         opj('stim', 'stim1.mp3'),
         {'meta': 'mp3'}),
        # report which field matched with auto-field
        ('autofield',
         'mp3',
         opj('stim', 'stim1.mp3'),
         {'audio.format': 'mp3'}),
        # XXX next one is not supported by current text field analyser
        # decomposes the mime type in [mime, audio, mp3]
        # ('autofield',
        # "'mime:audio/mp3'",
        # opj('stim', 'stim1.mp3'),
        # 'audio.format', 'mime:audio/mp3'),
        # but this one works
        ('autofield',
         "'mime audio mp3'",
         opj('stim', 'stim1.mp3'),
         {'audio.format': 'mp3'}),
        # TODO extend with more complex queries to test whoosh
        # query language configuration
    ):
        res = ds.search(query, mode=mode, full_record=True)
        assert_result_count(
            res, 1, type='file', path=opj(ds.path, hitpath),
            # each file must report the ID of the dataset it is from, critical for
            # discovering related content
            dsid=ds.id)
        # in egrep we currently do not search unique values
        # and the queries above aim at files
        assert_result_count(res, 1 if mode == 'egrep' else 2)
        if mode != 'egrep':
            assert_result_count(
                res, 1, type='dataset', path=ds.path, dsid=ds.id)
        # test the key and specific value of the match
        for matched_key, matched_val in matched.items():
            assert_in(matched_key, res[-1]['query_matched'])
            assert_equal(res[-1]['query_matched'][matched_key], matched_val)

    # test a suggestion msg being logged if no hits and key is a bit off
    with swallow_logs(new_level=logging.INFO) as cml:
        res = ds.search('audio.formats:mp3 audio.bitsrate:1', mode='egrep')
        assert not res
        assert_in('Did you mean any of', cml.out)
        assert_in('audio.format', cml.out)
        assert_in('audio.bitrate', cml.out)


def test_listdict2dictlist():
    f = _listdict2dictlist
    l1 = [1, 3, [1, 'a']]
    assert f(l1) is l1, "we return it as is if no emb dict"
    eq_(f([{1: 2}]), {1: 2})  # inside out no need for a list
    # inside out, join into the list, skip entry with a list, or space
    eq_(f([{1: [2, 3], 'a': 1}, {'a': 2, 'c': ''}]), {'a': [1, 2]})


def test_meta2autofield_dict():
    # Just a test that we would obtain the value stored for that extractor
    # instead of what unique values it already had (whatever that means)
    eq_(
        _meta2autofield_dict({
            'datalad_unique_content_properties':
                {'extr1': {"prop1": "v1"}},
            'extr1': {'prop1': 'value'}}),
        {'extr1.prop1': 'value'}
    )


def test_external_indexer():
    """ check that external indexer are called """
    class MockedIndexer(MetadataIndexer):
        def __init__(self, metadata_format_name: str):
            super().__init__(metadata_format_name)

        def create_index(self, metadata):
            yield from {
                "jubel": 1,
                "trubel": 2
            }.items()

    class MockedEntryPoint(EntryPoint):
        def __init__(self):
            pass

        def load(self, *args):
            return MockedIndexer

    def _mocked_iter_entry_points(group, metadata):
        yield MockedEntryPoint()

    with patch('pkg_resources.iter_entry_points',
               MagicMock(side_effect=_mocked_iter_entry_points)):
        index = _meta2autofield_dict({
            'datalad_unique_content_properties': {
                'extr1': {
                    "prop1": "v1"
                }
            },
            'extr1': {
                'prop1': 'value'
            }
        })

    eq_(
        index,
        {
            'extr1.jubel': '1',
            'extr1.trubel': '2'
        }
    )


def test_faulty_external_indexer():
    """ check that generic indexer is called on external indexer faults """
    class MockedEntryPoint(EntryPoint):
        def __init__(self):
            self.name = 'MockedEntryPoint'
            self.dist = 'Mock Distribution 1.1'

        def load(self, *args):
            raise Exception('Mocked indexer error')

    def _mocked_iter_entry_points(group, metadata):
        yield MockedEntryPoint()

    with patch('pkg_resources.iter_entry_points',
               MagicMock(side_effect=_mocked_iter_entry_points)):

        index = _meta2autofield_dict({
            'datalad_unique_content_properties': {
                'extr1': {
                    "prop1": "v1"
                }
            },
            'extr1': {
                'prop1': 'value'
            }
        })

    eq_(
        index,
        {
            'extr1.prop1': 'value'
        }
    )


def test_multiple_entry_points():
    """ check that generic indexer is called if multiple indexers exist for the same name """
    class MockedEntryPoint(EntryPoint):
        def __init__(self):
            self.name = 'MockedEntryPoint'
            self.dist = 'Mock Distribution 1.1'

        def load(self, *args):
            return 'Loaded MockedEntryPoint'

    def _mocked_iter_entry_points(group, metadata):
        yield MockedEntryPoint()
        yield MockedEntryPoint()

    with patch('pkg_resources.iter_entry_points',
               MagicMock(side_effect=_mocked_iter_entry_points)):

        index = _meta2autofield_dict({
            'datalad_unique_content_properties': {
                'extr1': {
                    "prop1": "v1"
                }
            },
            'extr1': {
                'prop1': 'value'
            }
        })

    eq_(
        index,
        {
            'extr1.prop1': 'value'
        }
    )


def test_gen4_query_aggregated_metadata():
    class DatasetMock:
        def __init__(self, path: str):
            self.path = path
            self.pathobj = Path(path)

    extractor_name = 'mocked_extractor'
    extracted_metadata = {'info': 'this is mocked metadata'}

    def mocked_dump(**kwargs):
        yield from [
            {
                'action': 'dump',
                'status': 'ok',
                'path': '/ds1',
                'metadata': {
                    'type': 'file',
                    'dataset_id': str(UUID(int=1234)),
                    'dataset_version': '0000001111111',
                    'extractor_name': extractor_name,
                    'path': kwargs['path'],
                    'extracted_metadata': extracted_metadata
                }
            },
            {
                'action': 'dump',
                'status': 'error',
                'path': '/ds1',
                'metadata': {
                    'type': 'file',
                    'dataset_id': str(UUID(int=12345)),
                    'dataset_version': '0000002222222',
                    'extractor_name': extractor_name,
                    'path': kwargs['path'],
                    'extracted_metadata': extracted_metadata
                }
            },
            {
                'action': 'dump',
                'status': 'ok',
                'path': '/ds1',
                'metadata': {
                    'type': 'something',
                    'dataset_id': str(UUID(int=123456)),
                    'dataset_version': '0000003333333',
                    'extractor_name': extractor_name,
                    'path': kwargs['path'],
                    'extracted_metadata': extracted_metadata
                }
            }
        ]

    def mocked_no_metadata(**kwargs):
        raise NoMetadataStoreFound()

    mocked_annotated_paths = [
        {
            'path': 'ds/p1',
            'types': ['file', 'dataset']
        }
    ]

    with patch("datalad.metadata.metadata.Dump") as dump_mock:
        dump_mock.return_value = mocked_dump

        result = tuple(
            gen4_query_aggregated_metadata(
                reporton='all',
                ds=DatasetMock('ds'),
                aps=mocked_annotated_paths
            )
        )
        assert_equal(len(result), 1)
        assert_equal(
            result[0]['metadata'],
            {extractor_name: extracted_metadata}
        )

        # ensure gen4 code path selection
        import datalad.metadata.metadata
        datalad.metadata.metadata.next_generation_metadata_available = True

        result = [
            metadata_result
            for metadata_result in query_aggregated_metadata(
                reporton='all',
                ds=DatasetMock('ds'),
                metadata_source='gen4',
                aps=mocked_annotated_paths,
            )
            if metadata_result['status'] == 'ok'
        ]
        assert_equal(len(result), 1)
        assert_equal(
            result[0]['metadata'],
            {extractor_name: extracted_metadata}
        )

        # check no metadata found-handling
        dump_mock.reset_mock()
        dump_mock.return_value = mocked_no_metadata

        result = [
            metadata_result
            for metadata_result in query_aggregated_metadata(
                reporton='all',
                ds=DatasetMock('ds'),
                metadata_source='all',
                aps=mocked_annotated_paths,
            )
            if metadata_result['status'] == 'impossible'
        ]
        assert_equal(len(result), 2)


@with_tempfile(mkdir=True)
def test_metadata_source_handling(temp_dir=None):
    import datalad.metadata.metadata as metadata_module

    temp_ds = Dataset(temp_dir).create()

    gen4_result, legacy_result = (
        {
            "status": "ok",
            "path": "/ds",
            "action": "search",
            "matches": {("x", "x"): True},
            "metadata": {"k1": "v1", "k2": "v2"},
            "metadata_source": source
        }
        for source in ("gen4", "legacy")
    )

    def reset_mock(mock, result):
        mock.reset_mock()
        mock.return_value = [result]

    metadata_module.next_generation_metadata_available = True
    with patch("datalad.metadata.metadata.gen4_query_aggregated_metadata") as gen4_mock, \
         patch("datalad.metadata.metadata.legacy_query_aggregated_metadata") as legacy_mock:

        reset_mock(gen4_mock, gen4_result)
        reset_mock(legacy_mock, legacy_result)
        r = tuple(
            result["metadata_source"]
            for result in search(dataset=temp_ds, query="v1", metadata_source='all')
        )
        assert_equal(r, ("legacy", "gen4"))

        reset_mock(gen4_mock, gen4_result)
        reset_mock(legacy_mock, legacy_result)
        r = tuple(
            result["metadata_source"]
            for result in search(dataset=temp_ds, query="v1", metadata_source="gen4")
        )
        assert_equal(r, ("gen4",))

        reset_mock(gen4_mock, gen4_result)
        reset_mock(legacy_mock, legacy_result)
        r = tuple(
            result["metadata_source"]
            for result in search(dataset=temp_ds, query="v1", metadata_source="legacy")
        )
        assert_equal(r, ("legacy",))
