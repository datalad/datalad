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
from ..misc import xrange_node
from ..misc import interrupt_if
from ...pipeline import FinishPipeline

from nose.tools import eq_, assert_raises
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

def test_xrange_node():
    eq_(list(xrange_node(1)()), [{'output': 0}])
    eq_(list(xrange_node(2)()), [{'output': 0}, {'output': 1}])

def test_interrupt_if():
    n = interrupt_if({'v1': 'done'})
    assert_raises(FinishPipeline, n(v1='done').next)
    assert_raises(FinishPipeline, n(v1='done', someother=123).next)
    tdict = dict(v1='not yet', someother=123)
    # and that we would interrupt while matching multiple values
    eq_(list(n(**tdict)), [tdict])
    assert_raises(FinishPipeline, interrupt_if(tdict)(**tdict).next)