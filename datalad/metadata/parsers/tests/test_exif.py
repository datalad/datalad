# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test EXIF parser"""


from shutil import copy
from os.path import dirname
from os.path import join as opj
from datalad.api import Dataset
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count


@with_tempfile(mkdir=True)
def test_exif(path):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'exif', where='dataset')
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'exif.jpg'),
        path)
    ds.add('.')
    ok_clean_git(ds.path)
    res = ds.aggregate_metadata()
    assert_status('ok', res)
    res = ds.metadata('exif.jpg')
    assert_result_count(res, 1)
    # compare full expected metadata set to catch any change of mind on the
    # side of the EXIF library
    assert_result_count(
        res, 1,
        metadata={
           "exif:InteroperabilityVersion": "[48, 49, 48, 48]",
           "exif:ExifVersion": 221.0,
           "exif:FocalLengthIn35mmFilm": 38.0,
           "exif:CompressedBitsPerPixel": 5.0,
           "exif:GainControl": "None",
           "exif:Compression": "JPEG (old-style)",
           "exif:PrintIM": "[80, 114, 105, 110, 116, 73, 77, 0, 48, 51, 48, 48, 0, 0, 0, 5, 0, 1, 0, 22, 0, 22, 0, 2, 1, 0, 0, 0, 1, 0, 5, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 16, 131, 0, 0, 0]",
           "exif:Make": "CASIO COMPUTER CO.,LTD.",
           "exif:Sharpness": "Normal",
           "exif:Contrast": "Normal",
           "exif:ColorSpace": "sRGB",
           "exif:ExposureMode": "Auto Exposure",
           "exif:ExposureBiasValue": 0.0,
           "exif:ExifImageWidth": 4.0,
           "exif:ComponentsConfiguration": "YCbCr",
           "exif:DateTimeOriginal": "2011:03:13 16:36:02",
           "exif:MaxApertureValue": "14/5",
           "exif:DateTime": "2017:10:08 10:21:03",
           "exif:InteroperabilityOffset": 30412.0,
           "exif:InteroperabilityIndex": "R98",
           "exif:FileSource": "Digital Camera",
           "exif:ResolutionUnit": "Pixels/Inch",
           "exif:FNumber": "27/10",
           "exif:ExposureProgram": "Program Normal",
           "exif:DigitalZoomRatio": "0/0",
           "exif:LightSource": "Unknown",
           "exif:ExifImageLength": 3.0,
           "exif:FlashPixVersion": 100.0,
           "exif:CustomRendered": "Normal",
           "exif:Flash": "Flash fired, auto mode",
           "exif:WhiteBalance": "Auto",
           "exif:Orientation": "Horizontal (normal)",
           "exif:ExposureTime": "1/60",
           "exif:Software": "GIMP 2.8.20",
           "exif:Model": "EX-S600",
           "exif:FocalLength": "31/5",
           "exif:SceneCaptureType": "Standard",
           "exif:ExifOffset": 272.0,
           "exif:Saturation": "Normal",
           "exif:YCbCrPositioning": "Centered",
           "exif:DateTimeDigitized": "2011:03:13 16:36:02",
           "exif:XResolution": 72.0,
           "exif:YResolution": 72.0,
           "exif:MeteringMode": "Pattern",
        })
