# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import vcr
from ..misc import get_deposition_filename

from nose.tools import eq_
from nose import SkipTest

# TODO: redo on a local example
# TODO: seems vcr fetches entire response not just the header which makes this test url
#       in particular not appropriate
@vcr.use_cassette('fixtures/vcr_cassettes/brain-map.org-1.yaml')
def test_get_deposition_filename():
    input = {'url': 'http://human.brain-map.org/api/v2/well_known_file_download/157722290'}
    output = list(get_deposition_filename(**input))
    assert(len(output), 1)
    eq_(output[0]['filename'], 'T1.nii.gz')

def test_assign():
    raise SkipTest('TODO')
    raise SkipTest('TODO with interpolations')

def test_rename():
    raise SkipTest('TODO')
