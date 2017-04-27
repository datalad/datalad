# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Primarily a smoke test for ls

"""

__docformat__ = 'restructuredtext'

import logging

from os import makedirs
from os.path import join as opj
from ...api import clean
from ...consts import ARCHIVES_TEMP_DIR
from ...consts import ANNEX_TEMP_DIR
from ...distribution.dataset import Dataset
from ...support.annexrepo import AnnexRepo
from ...tests.utils import with_tempfile
from ...utils import swallow_outputs
from ...utils import chpwd
from ...tests.utils import assert_equal
from ...tests.utils import assert_status


@with_tempfile(mkdir=True)
def test_clean(d):
    AnnexRepo(d, create=True)
    ds = Dataset(d)
    assert_status('notneeded', clean(dataset=ds))

    # if we create some temp archives directory
    makedirs(opj(d, ARCHIVES_TEMP_DIR, 'somebogus'))
    res = clean(dataset=ds, return_type='item-or-list',
                result_filter=lambda x: x['status'] == 'ok')
    assert_equal(res['path'], opj(d, ARCHIVES_TEMP_DIR))
    assert_equal(res['message'][0] % tuple(res['message'][1:]),
                 "Removed 1 temporary archive directory: somebogus")

    # relative path
    makedirs(opj(d, ARCHIVES_TEMP_DIR, 'somebogus'))
    makedirs(opj(d, ARCHIVES_TEMP_DIR, 'somebogus2'))
    with chpwd(d), swallow_outputs() as cmo:
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed 2 temporary archive directories: somebogus, somebogus2")

    # and what about git annex temporary files?
    makedirs(opj(d, ANNEX_TEMP_DIR))
    open(opj(d, ANNEX_TEMP_DIR, "somebogus"), "w").write("load")

    with chpwd(d):
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['path'], opj(d, ANNEX_TEMP_DIR))
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed 1 temporary annex file: somebogus")
