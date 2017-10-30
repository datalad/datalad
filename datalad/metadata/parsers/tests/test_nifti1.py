# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test NIfTI parser"""

from datalad.tests.utils import SkipTest
try:
    import nibabel
except ImportError:
    raise SkipTest

from shutil import copy
from os.path import dirname
from os.path import join as opj
from datalad.api import Dataset
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count


@with_tempfile(mkdir=True)
def test_nifti(path):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'nifti1', where='dataset')
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'nifti1.nii.gz'),
        path)
    ds.add('.')
    ok_clean_git(ds.path)
    res = ds.aggregate_metadata()
    assert_status('ok', res)
    res = ds.metadata('nifti1.nii.gz')
    assert_result_count(res, 1)
    assert_result_count(
        res, 1,
        metadata={
            "description": "FSL5.0",
            "3d_spatial_resolution(mm)": [2.0, 2.0, 2.0],
            "4d_spacing(s)": 6.0,
            "nifti1:dim": [4, 91, 109, 91, 2, 1, 1, 1],
            "nifti1:cal_min": 3000.0,
            "nifti1:regular": "r",
            "nifti1:cal_max": 8000.0,
            "nifti1:sform_code": 4,
            "nifti1:quatern_d": 0.0,
            "nifti1:quatern_b": 0.0,
            "nifti1:quatern_c": 1.0,
            "nifti1:toffset": 0.0,
            "nifti1:xyzt_units": 10,
            "nifti1:slice_start": 0,
            "nifti1:bitpix": 16,
            "nifti1:vox_offset": 0.0,
            "nifti1:glmax": 0,
            "nifti1:session_error": 0,
            "nifti1:intent_code": 0,
            "nifti1:glmin": 0,
            "nifti1:extents": 0,
            "nifti1:sizeof_hdr": 348,
            "nifti1:dim_info": 0,
            "nifti1:magic": "n+1",
            "nifti1:qform_code": 4,
            "nifti1:slice_duration": 0.0,
            "nifti1:slice_code": 0,
            "nifti1:datatype": 4,
            "nifti1:intent_p1": 0.0,
            "nifti1:intent_p2": 0.0,
            "nifti1:intent_p3": 0.0,
            "nifti1:slice_end": 0,
            "nifti1:qoffset_x": 90.0,
            "nifti1:qoffset_y": -126.0,
            "nifti1:qoffset_z": -72.0,
            "nifti1:srow_z": [0.0, 0.0, 2.0, -72.0],
            "nifti1:pixdim": [-1.0, 2.0, 2.0, 2.0, 6.0, 1.0, 1.0, 1.0],
            "nifti1:srow_x": [-2.0, 0.0, 0.0, 90.0],
            "nifti1:srow_y": [0.0, 2.0, 0.0, -126.0]
        })
