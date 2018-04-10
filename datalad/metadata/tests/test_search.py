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

from shutil import copy
from mock import patch
from os import makedirs
from os.path import join as opj
from os.path import dirname
from datalad.api import Dataset, install
from nose.tools import assert_equal, assert_raises
from datalad.utils import chpwd
from datalad.utils import swallow_outputs
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_is_generator
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_testsui
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import SkipTest
from datalad.tests.utils import eq_
from datalad.support.exceptions import NoDatasetArgumentFound

from datalad.api import search
from datalad.metadata import search as search_mod

from ..search import _listdict2dictlist
from ..search import _meta2autofield_dict


@with_testsui(interactive=False)
@with_tempfile(mkdir=True)
def test_search_outside1_noninteractive_ui(tdir):
    # we should raise an informative exception
    with chpwd(tdir):
        with assert_raises(NoDatasetArgumentFound) as cme:
            list(search("bu"))
        assert_in('run interactively', str(cme.exception))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_search_outside1(tdir, newhome):
    with chpwd(tdir):
        # should fail since directory exists, but not a dataset
        # should not even waste our response ;)
        with patch.object(search_mod, 'LOCAL_CENTRAL_PATH', newhome):
            gen = search("bu", return_type='generator')
            assert_is_generator(gen)
            assert_raises(NoDatasetArgumentFound, next, gen)

        # and if we point to some non-existing dataset
        with assert_raises(ValueError):
            next(search("bu", dataset=newhome))


@with_testsui(responses='yes')
@with_tempfile(mkdir=True)
@with_tempfile()
def test_search_outside1_install_central_ds(tdir, central_dspath):
    with chpwd(tdir):
        # let's mock out even actual install/search calls
        with \
            patch.object(search_mod, 'LOCAL_CENTRAL_PATH', central_dspath), \
            patch('datalad.api.install',
                  return_value=Dataset(central_dspath)) as mock_install, \
            patch('datalad.distribution.dataset.Dataset.search',
                  new_callable=_mock_search):
            _check_mocked_install(central_dspath, mock_install)

            # now on subsequent run, we want to mock as if dataset already exists
            # at central location and then do search again
            from datalad.ui import ui
            ui.add_responses('yes')
            mock_install.reset_mock()
            with patch(
                    'datalad.distribution.dataset.Dataset.is_installed',
                    True):
                _check_mocked_install(central_dspath, mock_install)

            # and what if we say "no" to install?
            ui.add_responses('no')
            mock_install.reset_mock()
            with assert_raises(NoDatasetArgumentFound):
                list(search("."))

            # and if path exists and is a valid dataset and we say "no"
            Dataset(central_dspath).create()
            ui.add_responses('no')
            mock_install.reset_mock()
            with assert_raises(NoDatasetArgumentFound):
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


def _check_mocked_install(central_dspath, mock_install):
    gen = search(".", return_type='generator')
    assert_is_generator(gen)
    # we no longer do any custom path tune up from the one returned by search
    # so should match what search returns
    assert_equal(
        list(gen), [report
                    for report in _mocked_search_results])
    mock_install.assert_called_once_with(central_dspath, source='///')


@with_tempfile
def test_our_metadataset_search(tdir):
    # TODO renable when a dataset with new aggregated metadata is
    # available at some public location
    raise SkipTest
    # smoke test for basic search operations on our super-megadataset
    # expensive operation but ok
    #ds = install(
    #    path=tdir,
    #    # TODO renable test when /// metadata actually conforms to the new metadata
    #    #source="///",
    #    source="smaug:/mnt/btrfs/datasets-meta6-4/datalad/crawl",
    #    result_xfm='datasets', return_type='item-or-list')
    assert list(ds.search('haxby'))
    assert_result_count(
        ds.search('id:873a6eae-7ae6-11e6-a6c8-002590f97d84', mode='textblob'),
        1,
        type='dataset',
        path=opj(ds.path, 'crcns', 'pfc-2'))

    # there is a problem with argparse not decoding into utf8 in PY2
    from datalad.cmdline.tests.test_main import run_main
    # TODO: make it into an independent lean test
    from datalad.cmd import Runner
    out, err = Runner(cwd=ds.path)('datalad search Buzsáki')
    assert_in('crcns/pfc-2 ', out)  # has it in description
    # and then another aspect: this entry it among multiple authors, need to
    # check if aggregating them into a searchable entity was done correctly
    assert_in('crcns/hc-1 ', out)


@with_tempfile
def test_search_non_dataset(tdir):
    from datalad.support.gitrepo import GitRepo
    GitRepo(tdir, create=True)
    with assert_raises(NoDatasetArgumentFound) as cme:
        list(search('smth', dataset=tdir))
    # Should instruct user how that repo could become a datalad dataset
    assert_in("datalad create --force", str(cme.exception))


@with_tempfile(mkdir=True)
def test_within_ds_file_search(path):
    try:
        import mutagen
    except ImportError:
        raise SkipTest
    ds = Dataset(path).create(force=True)
    ds.config.add('datalad.metadata.nativetype', 'audio', where='dataset')
    makedirs(opj(path, 'stim'))
    for src, dst in (
            ('audio.mp3', opj('stim', 'stim1.mp3')),):
        copy(
            opj(dirname(dirname(__file__)), 'tests', 'data', src),
            opj(path, dst))
    ds.add('.')
    ds.aggregate_metadata()
    ok_clean_git(ds.path)
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

    # check generated autofield index keys
    with swallow_outputs() as cmo:
        ds.search(mode='autofield', show_keys='name')
        # it is impossible to assess what is different from that dump
        assert_in(target_out, cmo.out)

    assert_result_count(ds.search('blablob#'), 0)
    # now check that we can discover things from the aggregated metadata
    for mode, query, hitpath, matched_key, matched_val in (
            # random keyword query
            ('textblob',
             'mp3',
             opj('stim', 'stim1.mp3'),
             'meta', 'mp3'),
            # report which field matched with auto-field
            ('autofield',
             'mp3',
             opj('stim', 'stim1.mp3'),
             'audio.format', 'mp3'),
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
             'audio.format', 'mp3'),
            # TODO extend with more complex queries to test whoosh
            # query language configuration
    ):
        res = ds.search(query, mode=mode, full_record=True)
        if mode == 'textblob':
            # 'textblob' does datasets by default only (be could be configured otherwise
            assert_result_count(res, 1)
        else:
            # the rest has always a file and the dataset, because they carry metadata in
            # the same structure
            assert_result_count(res, 2)
            assert_result_count(
                res, 1, type='file', path=opj(ds.path, hitpath),
                # each file must report the ID of the dataset it is from, critical for
                # discovering related content
                dsid=ds.id)
        assert_result_count(
            res, 1, type='dataset', path=ds.path, dsid=ds.id)
        # test the key and specific value of the match
        assert_in(matched_key, res[-1]['query_matched'])
        assert_equal(res[-1]['query_matched'][matched_key], matched_val)


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
