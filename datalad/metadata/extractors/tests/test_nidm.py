# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test NIDM extractor"""

from shutil import copy
from os.path import dirname
from os.path import join as opj
from datalad.api import Dataset
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_greater
from datalad.tests.utils import assert_result_count
from .test_bids import bids_template

try:
    from nidm.experiment.tools.BIDSMRI2NIDM import bidsmri2project
except ImportError:
    SkipTest


@with_tree(tree=bids_template)
def test_nidm(path):
    ds = Dataset(path).create(force=True)
    ds.config.add('datalad.metadata.nativetype', 'nidm', where='dataset')
    # imagine filling the dataset up with something that NIDM info could be
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'nifti1.nii.gz'),
        opj(path, 'sub-01', 'func', 'sub-01_task-some_bold.nii.gz'))
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'nifti1.nii.gz'),
        opj(path, 'sub-03', 'func', 'sub-03_task-other_bold.nii.gz'))
    # extracted from
    ds.add('.')
    # all nice and tidy, nothing untracked
    ok_clean_git(ds.path)
    # engage the extractor(s)
    res = ds.aggregate_metadata()
    # aggregation done without whining
    assert_status('ok', res)
    res = ds.metadata(reporton='datasets')
    # ATM we do not forsee file-based metadata to come back from NIDM
    assert_result_count(res, 1)
    # make basic content check, but otherwise we have no idea what we would
    # get from nidm, but it should be a bunch
    stuff = res[0]['metadata']['nidm']
    for key in ('@context', '@graph'):
        assert_in(key, stuff)
        assert_greater(len(stuff[key]), 10)
