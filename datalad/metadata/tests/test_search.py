# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Some additional tests for search command (some are within test_base)"""

import logging
from shutil import copy
from unittest.mock import patch
import os
from os import makedirs
from os.path import (
    dirname,
    join as opj,
)
from datalad.api import Dataset
from datalad.utils import (
    chpwd,
    swallow_logs,
    swallow_outputs,
)
from datalad.tests.utils import (
    assert_equal,
    assert_in,
    assert_re_in,
    assert_is_generator,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    eq_,
    known_failure_githubci_win,
    ok_file_under_git,
    patch_config,
    SkipTest,
    with_tempfile,
    with_testsui,
)
from datalad.support.exceptions import NoDatasetFound

from datalad.api import search

from ..search import (
    _AutofieldSearch,
    _BlobSearch,
    _EGrepCSSearch,
    _EGrepSearch,
    _listdict2dictlist,
    _meta2autofield_dict,
)


@with_testsui(interactive=False)
@with_tempfile(mkdir=True)
def test_search_outside1_noninteractive_ui(tdir):
    # we should raise an informative exception
    with chpwd(tdir):
        with assert_raises(NoDatasetFound) as cme:
            list(search("bu"))
        assert_in('run interactively', str(cme.exception))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_search_outside1(tdir, newhome):
    with chpwd(tdir):
        # should fail since directory exists, but not a dataset
        # should not even waste our response ;)
        with patch_config({'datalad.locations.default-dataset': newhome}):
            gen = search("bu", return_type='generator')
            assert_is_generator(gen)
            assert_raises(NoDatasetFound, next, gen)

        # and if we point to some non-existing dataset
        with assert_raises(ValueError):
            next(search("bu", dataset=newhome))


@with_testsui(responses='yes')
@with_tempfile(mkdir=True)
@with_tempfile()
def test_search_outside1_install_default_ds(tdir, default_dspath):
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
    mock_install.assert_called_once_with(default_dspath, source='///')


@with_tempfile
def test_search_non_dataset(tdir):
    from datalad.support.gitrepo import GitRepo
    GitRepo(tdir, create=True)
    with assert_raises(NoDatasetFound) as cme:
        list(search('smth', dataset=tdir))
    # Should instruct user how that repo could become a datalad dataset
    assert_in("datalad create --force", str(cme.exception))


@known_failure_githubci_win
@with_tempfile(mkdir=True)
def test_within_ds_file_search(path):
    try:
        import mutagen
    except ImportError:
        raise SkipTest
    ds = Dataset(path).create(force=True)
    # override default and search for datasets and files for this test
    for m in ('egrep', 'textblob', 'autofield'):
        ds.config.add(
            'datalad.search.index-{}-documenttype'.format(m), 'all',
            where='dataset')
    ds.config.add('datalad.metadata.nativetype', 'audio', where='dataset')
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
        ds.search(['\.id', 'artist$'], show_keys='short')
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
        str(cme.exception))

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
         'audio\.+:mp3',
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


def test_meta2autofield_jsonld_graph():
    """ check proper handling of JSON-LD @graph nodes """
    # Just a test that we would obtain the value stored for that extractor
    # instead of what unique values it already had (whatever that means)
    eq_(
        _meta2autofield_dict({"r": {"@graph": ["a", "b", "c"]}}),
        {'r.graph[0]': 'a', 'r.graph[1]': 'b', 'r.graph[2]': 'c'}
    )


def test_meta2autofield_jsonld_list():
    """ check proper handling of JSON-LD @list nodes """
    # Just a test that we would obtain the value stored for that extractor
    # instead of what unique values it already had (whatever that means)
    eq_(
        _meta2autofield_dict({"r": {"@list": ["a", "b", "c"]}}),
        {'r.list[0]': 'a', 'r.list[1]': 'b', 'r.list[2]': 'c'}
    )


_mocked_studyminimeta_jsonld = {
    "@context": {
        "@vocab": "http://schema.org/"
    },
    "@graph": [
        {
            "@id": "#study",
            "@type": "CreativeWork",
            "name": "A small study",
            "abstract": "a short description of the study",
            "accountablePerson": "a@example.com",
            "keywords": [
                "k1",
                "k2"
            ],
            "dateCreated": "01.01.2020",
            "description": "end_date: 02.02.2020",
            "contributor": [
                {
                    "@id": "https://schema.datalad.org/person#a@example.com"
                },
                {
                    "@id": "https://schema.datalad.org/person#b@example.com"
                }
            ],
            "funder": [
                {
                    "@id": "https://schema.datalad.org/organization#DFG",
                    "@type": "Organization",
                    "name": "DFG"
                },
                {
                    "@id": "https://schema.datalad.org/organization#NHO",
                    "@type": "Organization",
                    "name": "NHO"
                }
            ]
        },
        {
            "@id": "https://schema.datalad.org/datalad_dataset#id-0000--0000",
            "@type": "Dataset",
            "version": "a02312398324778972389472834",
            "name": "Datenddaslk",
            "url": "http://dlksdfs.comom.com",
            "description": "Some data I collected once upon a time, spending hours and hours in dark places.",
            "keywords": [
                "d_k1",
                "d_k2",
                "d_k3"
            ],
            "author": [
                {
                    "@id": "https://schema.datalad.org/person#a@example.com"
                },
                {
                    "@id": "https://schema.datalad.org/person#b@example.com"
                }
            ],
            "hasPart": {
                "@id": "#standards",
                "@type": "DefinedTermSet",
                "hasDefinedTerm": [
                    {
                        "@id": "https://schema.datalad.org/standard#dicom",
                        "@type": "DefinedTerm",
                        "termCode": "dicom"
                    },
                    {
                        "@id": "https://schema.datalad.org/standard#ebdsi",
                        "@type": "DefinedTerm",
                        "termCode": "ebdsi"
                    }
                ]
            }
        },
        {
            "@id": "#personList",
            "@list": [
                {
                    "@id": "https://schema.datalad.org/person#a@example.com",
                    "@type": "Person",
                    "email": "a@example.com",
                    "name": "Prof. Dr.  Alex Meyer",
                    "givenName": "Alex",
                    "familyName": "Meyer",
                    "sameAs": "0000-0001-0002-0033",
                    "honorificSuffix": "Prof. Dr.",
                    "affiliation": "Big Old University",
                    "contactPoint": {
                        "@id": "#contactPoint(a@example.com)",
                        "@type": "ContactPoint",
                        "description": "Corner broadway and main"
                    }
                },
                {
                    "@id": "https://schema.datalad.org/person#b@example.com",
                    "@type": "Person",
                    "email": "b@example.com",
                    "name": "MD  Bernd Muller",
                    "givenName": "Bernd",
                    "familyName": "Muller",
                    "sameAs": "0000-0001-0002-0034",
                    "honorificSuffix": "MD",
                    "affiliation": "RRU-SSLT",
                    "contactPoint": {
                        "@id": "#contactPoint(b@example.com)",
                        "@type": "ContactPoint",
                        "description": "central plaza"
                    }
                }
            ]
        },
        {
            "@id": "#publicationList",
            "@list": [
                {
                    "@id": "#publication[0]",
                    "@type": "ScholarlyArticle",
                    "headline": "Publication Numero Unos",
                    "datePublished": 2001,
                    "author": [
                        {
                            "@id": "https://schema.datalad.org/person#a@example.com"
                        },
                        {
                            "@id": "https://schema.datalad.org/person#b@example.com"
                        }
                    ],
                    "publisher": {
                        "@id": "https://schema.datalad.org/publisher#Renato",
                        "@type": "Organization",
                        "name": "Renato"
                    },
                    "isPartOf": {
                        "@id": "#issue(4)",
                        "@type": "PublicationIssue",
                        "issueNumber": 4,
                        "isPartOf": {
                            "@id": "#volume(30)",
                            "@type": "PublicationVolume",
                            "volumeNumber": 30
                        }
                    }
                },
                {
                    "@id": "#publication[1]",
                    "@type": "ScholarlyArticle",
                    "headline": "Publication Numero Dos",
                    "datePublished": 2002,
                    "author": [
                        {
                            "@id": "https://schema.datalad.org/person#a@example.com"
                        },
                        {
                            "@id": "https://schema.datalad.org/person#b@example.com"
                        }
                    ],
                    "publisher": {
                        "@id": "https://schema.datalad.org/publisher#Vorndran",
                        "@type": "Organization",
                        "name": "Vorndran"
                    },
                    "isPartOf": {
                        "@id": "#volume(400)",
                        "@type": "PublicationVolume",
                        "volumeNumber": 400
                    }
                },
                {
                    "@id": "#publication[2]",
                    "@type": "ScholarlyArticle",
                    "headline": "Publication Numero Tres",
                    "datePublished": 2003,
                    "author": [
                        {
                            "@id": "https://schema.datalad.org/person#a@example.com"
                        },
                        {
                            "@id": "https://schema.datalad.org/person#b@example.com"
                        }
                    ],
                    "publisher": {
                        "@id": "https://schema.datalad.org/publisher#Eisenberg",
                        "@type": "Organization",
                        "name": "Eisenberg"
                    },
                    "isPartOf": {
                        "@id": "#issue(500)",
                        "@type": "PublicationIssue",
                        "issueNumber": 500
                    }
                },
                {
                    "@id": "#publication[3]",
                    "@type": "ScholarlyArticle",
                    "headline": "Publication Numero Quatro",
                    "datePublished": 2004,
                    "author": [
                        {
                            "@id": "https://schema.datalad.org/person#a@example.com"
                        },
                        {
                            "@id": "https://schema.datalad.org/person#b@example.com"
                        }
                    ],
                    "publisher": {
                        "@id": "https://schema.datalad.org/publisher#Killian-Tumler",
                        "@type": "Organization",
                        "name": "Killian-Tumler"
                    }
                }
            ]
        }
    ]
}


def test_meta2autofield_studyminimeta():
    """ check proper handling of JSON-LD @list nodes """
    # Just a test that we would obtain the value stored for that extractor
    # instead of what unique values it already had (whatever that means)
    generated_dict = _meta2autofield_dict({"metalad_studyminimeta": _mocked_studyminimeta_jsonld})
    template_dict = {
        'metalad_studyminimeta.dataset.author': 'Prof. Dr.  Alex Meyer, MD  Bernd Muller',
        'metalad_studyminimeta.dataset.name': 'Datenddaslk',
        'metalad_studyminimeta.dataset.location': 'http://dlksdfs.comom.com',
        'metalad_studyminimeta.dataset.description': 'Some data I collected once upon a time, '
                                                     'spending hours and hours in dark places.',
        'metalad_studyminimeta.dataset.keywords': 'd_k1, d_k2, d_k3',
        'metalad_studyminimeta.dataset.standards': 'dicom, ebdsi',
        'metalad_studyminimeta.person.email': 'a@example.com, b@example.com',
        'metalad_studyminimeta.person.name': 'Prof. Dr.  Alex Meyer, MD  Bernd Muller',
        'metalad_studyminimeta.name': 'A small study',
        'metalad_studyminimeta.accountable_person': 'Prof. Dr.  Alex Meyer',
        'metalad_studyminimeta.contributor': 'Prof. Dr.  Alex Meyer, MD  Bernd Muller',
        'metalad_studyminimeta.publication.author': 'Prof. Dr.  Alex Meyer, MD  Bernd Muller',
        'metalad_studyminimeta.publication.title': 'Publication Numero Quatro',
        'metalad_studyminimeta.publication.year': '2004', 'metalad_studyminimeta.keywords': 'k1, k2'
    }
    eq_(generated_dict, template_dict)


def _test_ds_studyminimeta_show_keys_full_with_searcher(ds, search_class, mode):
    from unittest.mock import patch, MagicMock

    # Mock the aggregation of studyminimeta-metadata since the extractor
    # is not necessarily installed
    def _mock_query_aggregated_metadata(**kwargs):
        yield {
            'path': "/mocked/static/path",
            'status': 'ok',
            'type': 'dataset',
            'metadata': {
                'metalad_studyminimeta': _mocked_studyminimeta_jsonld
            }
        }

    # When the studyminimeta-indexer is moved into datalad-metalad, these tests will
    # move there too. Until then, we might not have the studyminimeta-plugins available,
    # therefore we have to mock out datalad.metadata.metadata.load_ds_aggregate_db.
    # (Issue #4944 <https://github.com/datalad/datalad/issues/4944>)
    def _mock_load_ds_aggregate_db(*args, **kwargs):
        return {
            '.': {
                'path': '/mocked/ds/path',
            }
        }

    with \
            patch('datalad.metadata.search.query_aggregated_metadata',
                  MagicMock(side_effect=_mock_query_aggregated_metadata)),\
            patch('datalad.metadata.metadata.load_ds_aggregate_db',
                  MagicMock(side_effect=_mock_load_ds_aggregate_db)), \
            swallow_outputs() as cmo:

        searcher = search_class(ds)
        searcher.show_keys(mode=mode)
        out_lines = [line for line in cmo.out.split(os.linesep) if line]

    key_lines = [key_line for key_line in out_lines if not key_line.startswith(' ')]
    if issubclass(search_class, _BlobSearch):
        # On blobsearch, check for the existence of the meta-blob
        assert_equal(
            key_lines,
            [
                'id',
                'meta',
                'parentds',
                'path',
                'type'
            ]
        )
    else:
        # Test that the studyminimeta-indexer is called and working
        assert_equal(
            key_lines,
            (['id'] if issubclass(search_class, _AutofieldSearch) else [])
            + [
                'metalad_studyminimeta.accountable_person',
                'metalad_studyminimeta.contributor',
                'metalad_studyminimeta.dataset.author',
                'metalad_studyminimeta.dataset.description',
                'metalad_studyminimeta.dataset.keywords',
                'metalad_studyminimeta.dataset.location',
                'metalad_studyminimeta.dataset.name',
                'metalad_studyminimeta.dataset.standards',
                'metalad_studyminimeta.keywords',
                'metalad_studyminimeta.name',
                'metalad_studyminimeta.person.email',
                'metalad_studyminimeta.person.name',
                'metalad_studyminimeta.publication.author',
                'metalad_studyminimeta.publication.title',
                'metalad_studyminimeta.publication.year',
                'parentds',
                'path',
                'type'
            ]
        )

    if mode == 'full':
        # Test correct value composition
        assert_equal(
            out_lines,
            [
                "metalad_studyminimeta.accountable_person",
                " in  1 datasets",
                " has 1 unique values: 'Prof. Dr.  Alex Meyer'",
                "metalad_studyminimeta.contributor",
                " in  1 datasets",
                " has 1 unique values: 'Prof. Dr.  Alex Meyer, MD  Bernd Muller'",
                "metalad_studyminimeta.dataset.author",
                " in  1 datasets",
                " has 1 unique values: 'Prof. Dr.  Alex Meyer, MD  Bernd Muller'",
                "metalad_studyminimeta.dataset.description",
                " in  1 datasets",
                " has 1 unique values: <<'Some data I collected once upon a++44 chars++es.'>>",
                "metalad_studyminimeta.dataset.keywords",
                " in  1 datasets",
                " has 1 unique values: 'd_k1, d_k2, d_k3'",
                "metalad_studyminimeta.dataset.location",
                " in  1 datasets",
                " has 1 unique values: 'http://dlksdfs.comom.com'",
                "metalad_studyminimeta.dataset.name",
                " in  1 datasets",
                " has 1 unique values: 'Datenddaslk'",
                "metalad_studyminimeta.dataset.standards",
                " in  1 datasets",
                " has 1 unique values: 'dicom, ebdsi'",
                "metalad_studyminimeta.keywords",
                " in  1 datasets",
                " has 1 unique values: 'k1, k2'",
                "metalad_studyminimeta.name",
                " in  1 datasets",
                " has 1 unique values: 'A small study'",
                "metalad_studyminimeta.person.email",
                " in  1 datasets",
                " has 1 unique values: 'a@example.com, b@example.com'",
                "metalad_studyminimeta.person.name",
                " in  1 datasets",
                " has 1 unique values: 'Prof. Dr.  Alex Meyer, MD  Bernd Muller'",
                "metalad_studyminimeta.publication.author",
                " in  1 datasets",
                " has 1 unique values: 'Prof. Dr.  Alex Meyer, MD  Bernd Muller'",
                "metalad_studyminimeta.publication.title",
                " in  1 datasets",
                " has 1 unique values: 'Publication Numero Quatro'",
                "metalad_studyminimeta.publication.year",
                " in  1 datasets",
                " has 1 unique values: 2004",
                "parentds",
                " in  1 datasets",
                " has 0 unique values: ",
                "path",
                " in  1 datasets",
                " has 1 unique values: '/mocked/static/path'",
                "type",
                " in  1 datasets",
                " has 1 unique values: 'dataset'"
            ]
        )
    return


@with_tempfile(mkdir=True)
def test_ds_studyminimeta_show_keys(path):
    ds = Dataset(path).create(force=True)

    metadata_dir = opj(ds.path, '.datalad', 'metadata')
    aggregate_json_file_name = opj(metadata_dir, 'aggregate_v1.json')
    makedirs(metadata_dir)
    with open(aggregate_json_file_name, 'tw+') as f:
        f.write('{"info": "this is a dummy json object, used for testing"}')
    ds.save()

    for search_class, mode in ((_BlobSearch, 'name'), (_AutofieldSearch, 'name'), (_EGrepSearch, 'full'), (_EGrepCSSearch, 'full'),):
        _test_ds_studyminimeta_show_keys_full_with_searcher(ds, search_class, mode)
    return


