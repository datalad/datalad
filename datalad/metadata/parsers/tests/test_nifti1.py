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
from datalad.tests.utils import eq_
from datalad.tests.utils import assert_in


target = {
    "description": "FSL5.0",
    "spatial_resolution(mm)": [2.0, 2.0, 2.0],
    "temporal_spacing(s)": 6.0,
    "nifti1:datatype": "int16",
    "nifti1:dim": [4, 91, 109, 91, 2, 1, 1, 1],
    "nifti1:pixdim": [-1.0, 2.0, 2.0, 2.0, 6.0, 1.0, 1.0, 1.0],
    "nifti1:xyz_unit": "millimiter (uo:0000016)",
    "nifti1:t_unit": "second (uo:0000010)",
    "nifti1:cal_min": 3000.0,
    "nifti1:cal_max": 8000.0,
    "nifti1:toffset": 0.0,
    "nifti1:vox_offset": 0.0,
    "nifti1:intent": "none",
    "nifti1:sizeof_hdr": 348,
    "nifti1:magic": "n+1",
    "nifti1:sform_code": "mni",
    "nifti1:qform_code": "mni",
    "nifti1:freq_axis": None,
    "nifti1:phase_axis": None,
    "nifti1:slice_axis": None,
    "nifti1:slice_start": 0,
    "nifti1:slice_duration": 0.0,
    "nifti1:slice_order": "unknown",
    "nifti1:slice_end": 0,
}


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

    # from this parser
    meta = res[0]['metadata']['nifti1']
    for k, v in target.items():
        eq_(meta[k], v)

    assert_in('@context', meta)
