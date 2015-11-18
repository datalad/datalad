# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from six import next
from ..misc import get_deposition_filename
from ..misc import range_node
from ..misc import interrupt_if
from ..misc import func_to_node
from ...pipeline import FinishPipeline

from datalad.tests.utils import skip_if_no_network
from datalad.tests.utils import use_cassette
from datalad.tests.utils import ok_generator
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_equal
from datalad.tests.utils import assert_false

from nose.tools import eq_, assert_raises
from nose import SkipTest

# TODO: redo on a local example
# TODO: seems vcr fetches entire response not just the header which makes this test url
#       in particular not appropriate
@skip_if_no_network
@use_cassette('fixtures/vcr_cassettes/brain-map.org-1.yaml')
def test_get_deposition_filename():
    input = {'url': 'http://human.brain-map.org/api/v2/well_known_file_download/157722290'}
    output = list(get_deposition_filename(input))
    eq_(len(output), 1)
    eq_(output[0]['filename'], 'T1.nii.gz')

def test_assign():
    raise SkipTest('TODO')
    raise SkipTest('TODO with interpolations')

def test_rename():
    raise SkipTest('TODO')

def test_range_node():
    eq_(list(range_node(1)()), [{'output': 0}])
    eq_(list(range_node(2)()), [{'output': 0}, {'output': 1}])

def test_interrupt_if():
    n = interrupt_if({'v1': 'done'})
    assert_raises(FinishPipeline, next, n(dict(v1='done')))
    assert_raises(FinishPipeline, next, n(dict(v1='done', someother=123)))
    tdict = dict(v1='not yet', someother=123)
    # and that we would interrupt while matching multiple values
    eq_(list(n(tdict)), [tdict])
    assert_raises(FinishPipeline, next, interrupt_if(tdict)(tdict))

def test_func_to_node():
    int_node = func_to_node(int)  # node which requires nothing and nothing of output is used
    assert(int_node.__doc__)
    in_dict = {'in': 1}
    ok_generator(int_node(in_dict))

    # xrange is not considered to be a generator
    def xrange_(n, offset=0):
        for x in range(offset, offset+n):
            yield x

    xrange_node = func_to_node(xrange_, data_args='in', outputs='out')
    assert_in('assigned to out', xrange_node.__doc__)
    assert_false('Additional keyword arguments' in xrange_node.__doc__)
    range_node_gen = xrange_node(in_dict)
    ok_generator(range_node_gen)
    assert_equal(list(range_node_gen), [{'in': 1, 'out': 0}])

    # with additional kwargs
    xrange_node = func_to_node(xrange_, data_args='in', outputs='out', kwargs={'offset': 10})
    assert_in('assigned to out', xrange_node.__doc__)
    assert_in('Additional keyword arguments', xrange_node.__doc__)
    range_node_gen = xrange_node(in_dict)
    ok_generator(range_node_gen)
    assert_equal(list(range_node_gen), [{'in': 1, 'out': 10}])