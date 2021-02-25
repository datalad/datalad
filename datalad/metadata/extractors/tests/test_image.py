# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test image extractor"""

from datalad.tests.utils import (
    assert_in,
    assert_repo_status,
    assert_result_count,
    assert_status,
    eq_,
    SkipTest,
    with_tempfile,
)
try:
    from PIL import Image
except ImportError as exc:
    from datalad.dochelpers import exc_str
    raise SkipTest(
       "No PIL module available or it cannot be imported: %s" % exc_str(exc))

from shutil import copy
from os.path import (
    dirname,
    join as opj,
)
from datalad.api import Dataset


target = {
    "dcterms:SizeOrDuration": [4, 3],
    "color_mode": "3x8-bit pixels, true color",
    "type": "dctype:Image",
    "spatial_resolution(dpi)": [72, 72],
    "format": "JPEG (ISO 10918)"
}


@with_tempfile(mkdir=True)
def test_image(path):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'image', where='dataset')
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'exif.jpg'),
        path)
    ds.save()
    assert_repo_status(ds.path)
    res = ds.aggregate_metadata()
    assert_status('ok', res)
    res = ds.metadata('exif.jpg')
    assert_result_count(res, 1)

    # from this extractor
    meta = res[0]['metadata']['image']
    for k, v in target.items():
        eq_(meta[k], v)

    assert_in('@context', meta)
