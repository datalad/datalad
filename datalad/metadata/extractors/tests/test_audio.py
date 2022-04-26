# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test audio extractor"""

from datalad.tests.utils_pytest import (
    SkipTest,
    assert_in,
    assert_not_in,
    assert_repo_status,
    assert_result_count,
    assert_status,
    eq_,
    with_tempfile,
)

try:
    import mutagen
except ImportError:
    raise SkipTest

from os.path import dirname
from os.path import join as opj
from shutil import copy

from datalad.api import Dataset

target = {
    "format": "mime:audio/mp3",
    "duration(s)": 1.0,
    "name": "dltracktitle",
    "music:album": "dlalbumtitle",
    "music:artist": "dlartist",
    "music:channels": 1,
    "music:sample_rate": 44100,
    "music:Genre": "dlgenre",
    "date": "",
    "tracknumber": "dltracknumber",
}


@with_tempfile(mkdir=True)
def test_audio(path=None):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'audio', scope='branch')
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'audio.mp3'),
        path)
    ds.save()
    assert_repo_status(ds.path)
    res = ds.aggregate_metadata()
    assert_status('ok', res)
    res = ds.metadata('audio.mp3')
    assert_result_count(res, 1)

    # from this extractor
    meta = res[0]['metadata']['audio']
    for k, v in target.items():
        eq_(meta[k], v)

    assert_in('@context', meta)

    uniques = ds.metadata(
        reporton='datasets', return_type='item-or-list')['metadata']['datalad_unique_content_properties']
    # test file has it, but uniques have it blanked out, because the extractor considers it worthless
    # for discovering whole datasets
    assert_in('bitrate', meta)
    eq_(uniques['audio']['bitrate'], None)

    # 'date' field carries not value, hence gets exclude from the unique report
    assert_in('date', meta)
    assert(not meta['date'])
    assert_not_in('date', uniques['audio'])
