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

from os import makedirs
from os.path import join as opj
from ...api import clean
from ...consts import ARCHIVES_TEMP_DIR
from ...support.annexrepo import AnnexRepo
from ...tests.utils import with_tempfile
from ...utils import swallow_outputs
from ...utils import chpwd
from ...tests.utils import assert_equal, assert_in
from ...tests.utils import use_cassette

@with_tempfile(mkdir=True)
def test_ls(d):
    repo = AnnexRepo(d, create=True)
    with swallow_outputs() as cmo:
        assert_equal(clean(annex=repo), None)  # no output ATM
        assert_equal(cmo.out, '')  # no output ATM

    # if we create some temp archives directory
    makedirs(opj(d, ARCHIVES_TEMP_DIR, 'somebogus'))
    with swallow_outputs() as cmo:
        assert_equal(clean(annex=repo), None)  # no output ATM
        assert_equal("Removing 1 temporary archive directory under %s: somebogus"
                  % opj(d, ARCHIVES_TEMP_DIR), cmo.out.rstrip())

    # relative path
    makedirs(opj(d, ARCHIVES_TEMP_DIR, 'somebogus'))
    makedirs(opj(d, ARCHIVES_TEMP_DIR, 'somebogus2'))
    with chpwd(d), \
         swallow_outputs() as cmo:
        assert_equal(clean(), None)  # no output ATM
        assert_equal("Removing 2 temporary archive directories under %s: somebogus, somebogus2"
                  % ARCHIVES_TEMP_DIR, cmo.out.rstrip())
