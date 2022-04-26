# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test EXIF extractor"""

from datalad.tests.utils_pytest import (
    SkipTest,
    assert_in,
    assert_repo_status,
    assert_result_count,
    assert_status,
    eq_,
    with_tempfile,
)

try:
    import exifread
except ImportError:
    raise SkipTest

from os.path import dirname
from os.path import join as opj
from shutil import copy

from datalad.api import Dataset

target = {
    "InteroperabilityVersion": "[48, 49, 48, 48]",
    "ExifVersion": 221.0,
    "FocalLengthIn35mmFilm": 38.0,
    "CompressedBitsPerPixel": 5.0,
    "GainControl": "None",
    "Compression": "JPEG (old-style)",
    "PrintIM": "[80, 114, 105, 110, 116, 73, 77, 0, 48, 51, 48, 48, 0, 0, 0, 5, 0, 1, 0, 22, 0, 22, 0, 2, 1, 0, 0, 0, 1, 0, 5, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 16, 131, 0, 0, 0]",
    "Make": "CASIO COMPUTER CO.,LTD.",
    "Sharpness": "Normal",
    "Contrast": "Normal",
    "ColorSpace": "sRGB",
    "ExposureMode": "Auto Exposure",
    "ExposureBiasValue": 0.0,
    "ExifImageWidth": 4.0,
    "ComponentsConfiguration": "YCbCr",
    "DateTimeOriginal": "2011:03:13 16:36:02",
    "MaxApertureValue": "14/5",
    "DateTime": "2017:10:08 10:21:03",
    "InteroperabilityOffset": 30412.0,
    "InteroperabilityIndex": "R98",
    "FileSource": "Digital Camera",
    "ResolutionUnit": "Pixels/Inch",
    "FNumber": "27/10",
    "ExposureProgram": "Program Normal",
    "DigitalZoomRatio": "0/0",
    "LightSource": "Unknown",
    "ExifImageLength": 3.0,
    "FlashPixVersion": 100.0,
    "CustomRendered": "Normal",
    "Flash": "Flash fired, auto mode",
    "WhiteBalance": "Auto",
    "Orientation": "Horizontal (normal)",
    "ExposureTime": "1/60",
    "Software": "GIMP 2.8.20",
    "Model": "EX-S600",
    "FocalLength": "31/5",
    "SceneCaptureType": "Standard",
    "ExifOffset": 272.0,
    "Saturation": "Normal",
    "YCbCrPositioning": "Centered",
    "DateTimeDigitized": "2011:03:13 16:36:02",
    "XResolution": 72.0,
    "YResolution": 72.0,
    "MeteringMode": "Pattern",
}


@with_tempfile(mkdir=True)
def test_exif(path=None):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'exif', scope='branch')
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
    meta = res[0]['metadata']['exif']
    for k, v in target.items():
        eq_(meta[k], v)

    assert_in('@context', meta)
