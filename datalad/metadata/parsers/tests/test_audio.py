# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test audio parser"""


from shutil import copy
from os.path import dirname
from os.path import join as opj
from datalad.api import Dataset
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count


@with_tempfile(mkdir=True)
def test_audio(path):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'audio', where='dataset')
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'audio.mp3'),
        path)
    ds.add('.')
    ok_clean_git(ds.path)
    res = ds.aggregate_metadata()
    assert_status('ok', res)
    res = ds.metadata('audio.mp3')
    assert_result_count(res, 1)
    # compare full expected metadata set to catch any change of mind on the
    # side of the mutagen package
    assert_result_count(
        res, 1,
        metadata={
           "format": "mime:audio/mp3",
           "duration(s)": 1.0,
           "name": "dltracktitle",
           "music:album": "dlalbumtitle",
           "music:artist": "dlartist",
           "music:channels": 1,
           "music:sample_rate": 44100,
           "music:Genre": "dlgenre",
           "comment<bitrate>": 43928,
           "comment<date>": "",
           "comment<tracknumber>": "dltracknumber",
        })
