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

from ...api import ls
from ...utils import swallow_outputs
from ...tests.utils import assert_equal, assert_in
from ...tests.utils import use_cassette

from datalad.downloaders.tests.utils import get_test_providers


@use_cassette('fixtures/vcr_cassettes/ls_s3.yaml')
def test_ls():
    url = 's3://datalad-test0-versioned/'
    with swallow_outputs():
        # just to skip if no credentials
        get_test_providers(url)

    with swallow_outputs() as cmo:
        assert_equal(ls(url), None) # not output ATM
        assert_in('Bucket info:', cmo.out)
test_ls.tags = ['network']
