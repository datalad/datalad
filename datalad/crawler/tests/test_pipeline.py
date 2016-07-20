# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import join as opj

from datalad.tests.utils import skip_if_scrapy_without_selector
skip_if_scrapy_without_selector()

from ..nodes.crawl_url import crawl_url
from ..nodes.matches import *
from ..pipeline import run_pipeline, FinishPipeline

from ..nodes.misc import Sink, assign, range_node, interrupt_if
from ..nodes.annex import Annexificator
from ..pipeline import load_pipeline_from_module

from ...support.stats import ActivityStats

from ...tests.utils import with_tree
from ...tests.utils import eq_, ok_, assert_raises
from ...tests.utils import assert_in
from ...tests.utils import skip_if_no_module
from ...tests.utils import with_tempfile
from ...tests.utils import skip_if_no_network
from ...tests.utils import use_cassette

from logging import getLogger
lgr = getLogger('datalad.crawl.tests')


class AssertOrder(object):
    """Helper to verify that nodes executed in correct order

    Counter _call gets incremented with each invocation of the _call
    """
    def __init__(self):
        self._call = 0

    def __call__(self, numbers):
        if isinstance(numbers, int):
            numbers = {numbers}

        def _assert_order(data):
            self._call += 1
            lgr.debug("#%d invocation of %s " % (self._call, self))
            assert_in(self._call, numbers)
            yield data
        return _assert_order


@with_tree(tree={
    'pipeline.py': 'pipeline = lambda: [1]',
    'pipeline2.py': 'pipeline = lambda x: [2*x]',
})
def test_load_pipeline_from_script(d):
    eq_(load_pipeline_from_module(opj(d, 'pipeline.py')), [1])
    eq_(load_pipeline_from_module(opj(d, 'pipeline2.py'), kwargs=dict(x=2)), [4])
    assert_raises(RuntimeError, load_pipeline_from_module, opj(d, 'unlikelytobethere.py'))


DEFAULT_OUTPUT = [{'datalad_stats': ActivityStats()}]


def _out(ld):
    """Adjust output entry to include default outputs as well
    """
    outl = []
    for d in ld:
        out = d.copy()
        outl.append(out)
        for k, v in DEFAULT_OUTPUT[0].items():
            if k not in out:
                out[k] = v
    return outl


def test_pipeline_linear_simple():
    sink = Sink()
    pipeline = [
        range_node(2, "out1"),
        range_node(3, "out2"),
        sink
    ]
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, DEFAULT_OUTPUT)  # by default 'input' is output and input is made empty dict if not provided
    eq_(sink.data, [{'out1': 0, 'out2': 0}, {'out1': 0, 'out2': 1}, {'out1': 0, 'out2': 2},
                    {'out1': 1, 'out2': 0}, {'out1': 1, 'out2': 1}, {'out1': 1, 'out2': 2}])

    # if we extend pipeline with matching interrupt_if, the entire pipeline should
    # stop at that matching point, but otherwise there should be no crash etc
    sink.clean()
    pipeline_output = run_pipeline(pipeline + [interrupt_if({'out1': 0, 'out2': 1})])
    eq_(pipeline_output, DEFAULT_OUTPUT)
    eq_(sink.data, [{'out1': 0, 'out2': 0}, {'out1': 0, 'out2': 1}])


def test_pipeline_unknown_opts():
    assert_raises(ValueError, run_pipeline, [{'xxx': 1}])


def test_pipeline_linear_nested_order():
    sink = Sink()
    sink2 = Sink()
    assert_order = AssertOrder()

    pipeline = [
        assert_order(1),
        range_node(2, "out1"),
        assert_order({2, 5}),
        [
            assert_order({3, 6}),
            range_node(3, "out2"),
            sink,
        ],
        assert_order({4, 7}),
        sink2
    ]
    pipeline_output = run_pipeline(pipeline)


def test_pipeline_linear_nested():
    sink = Sink()
    sink2 = Sink()
    assert_order = AssertOrder()

    pipeline = [
        range_node(2, "out1"),
        [
            range_node(3, "out2"),
            sink,
        ],
        sink2
    ]
    all_pairs = [{'out1': 0, 'out2': 0}, {'out1': 0, 'out2': 1}, {'out1': 0, 'out2': 2},
                 {'out1': 1, 'out2': 0}, {'out1': 1, 'out2': 1}, {'out1': 1, 'out2': 2}]
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, DEFAULT_OUTPUT)
    eq_(sink.data, all_pairs)
    # and output is not seen outside of the nested pipeline
    eq_(sink2.data, [{'out1': 0}, {'out1': 1}])

    # Let's make nested pipeline yield all
    sink.clean()
    sink2.clean()
    pipeline[1].insert(0, {'output': 'outputs'})

    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, DEFAULT_OUTPUT)  # by default no output produced
    eq_(sink.data, all_pairs)
    # and output was passed outside from the nested pipeline
    eq_(sink2.data, all_pairs)

    # Let's make it yield the last-output one
    sink2.clean()
    pipeline[1][0] = {'output': 'last-output'}
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, DEFAULT_OUTPUT)  # by default no output produced
    # only the last output from the nested pipeline appeared outside
    eq_(sink2.data, [{'out1': 0, 'out2': 2}, {'out1': 1, 'out2': 2}])

    # Let's now add output to the top-most pipeline
    pipeline.insert(0, {'output': 'outputs'})
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, _out([{'out1': 0, 'out2': 2},
                               {'out1': 1, 'out2': 2}]))

    # and if we ask only for the last one
    pipeline[0] = {'output': 'last-output'}
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, _out([{'out1': 1, 'out2': 2}]))


def test_pipeline_recursive():
    def less3(data):
        """a little helper which would not yield whenever input x>3"""
        if data['x'] < 3:
            yield updated(data, dict(x=data['x']+1))

    pipeline = [
        {'loop': True, 'output': 'outputs'},
        less3,
    ]
    pipeline_output = run_pipeline(pipeline, dict(x=0))
    eq_(pipeline_output, _out([{'x': 1}, {'x': 2}, {'x': 3}]))


def test_pipeline_looping():
    count = [0, 0]

    def count_threetimes(data):
        """helper to not yield anything if done it 3 times by now"""
        if count[0] >= 3:
            return
        count[0] += 1
        for i in range(count[0]):
            yield updated(data, dict(somevar=(i, count[0])))

    def add_count(data):
        count[1] += 1
        yield updated(data, {'count': count[0]})

    def passthrough(data):
        yield data

    pipeline_output = run_pipeline([{'loop': True}, count_threetimes], dict(x=0))
    eq_(pipeline_output, _out([{'x': 0}]))
    eq_(count, [3, 0])

    # and even if the node not yielding is note the first node
    pipeline_output = run_pipeline([{'loop': True}, passthrough, count_threetimes], dict(x=0))
    eq_(pipeline_output, _out([{'x': 0}]))
    eq_(count, [3, 0])

    count[0] = 0
    # Let's rerun with explicit last-output, which would also affect output of this pipeline
    pipeline_output = run_pipeline([{'loop': True, 'output': 'last-output'}, count_threetimes], dict(x=0))
    eq_(pipeline_output, _out([{'x': 0, 'somevar': (2, 3)}]))
    eq_(count, [3, 0])

    # and if pipeline is composite, i.e. more than a single step, so we could make sure everything is called
    count[0] = 0
    pipeline_output = run_pipeline([{'loop': True}, count_threetimes, add_count], dict(x=0))
    eq_(pipeline_output, _out([{'x': 0}]))
    eq_(count, [3, 6])

    count[0] = count[1] = 0
    # Let's rerun with explicit last-output, which would also affect output of this pipeline
    pipeline_output = run_pipeline([{'loop': True, 'output': 'last-output'}, count_threetimes, add_count], dict(x=0))
    eq_(pipeline_output, _out([{'x': 0, 'somevar': (2, 3), 'count': 3}]))
    eq_(count, [3, 6])


def test_pipeline_linear_top_isnested_pipeline():
    # check if no generated data to reach the end node, it still gets executed
    was_called = []
    pipeline = [
        # range_node(1),
        [
            range_node(1, "out2"),
        ],
        lambda d: was_called.append('yes')
    ]
    pipeline_output = run_pipeline(pipeline)
    eq_(was_called, ['yes'])


def test_pipeline_updated_stats():
    def n1(data):
        data['datalad_stats'].increment('add_git')
        yield data

    def n2(data):  # doesn't care to maintain previous stats
        data = data.copy()
        data['datalad_stats'] = ActivityStats(files=2)
        data['out'] = 1
        yield data
    pipeline_output = run_pipeline([{'output': 'outputs'}, n1, n2])
    eq_(pipeline_output, [{'datalad_stats': ActivityStats(files=2, add_git=1), 'out': 1}])


def test_pipeline_dropped_stats():
    def n1(data):
        data['datalad_stats'].increment('add_git')
        yield data

    def n2(data):  # doesn't care to maintain previous stats
        yield {'out': 1}
    pipeline_output = run_pipeline([{'output': 'outputs'}, n1, n2])
    eq_(pipeline_output, [{'datalad_stats': ActivityStats(add_git=1), 'out': 1}])


def test_pipeline_stats_persist():
    # to test that we would get proper stats returned in various pipeline layouts
    def n1(data):
        data['datalad_stats'].increment('add_git')
        yield data

    def p(data):
        yield data

    def n2(data):  # doesn't care to maintain previous stats
        data['datalad_stats'].increment('add_annex')
        yield data

    target_stats = ActivityStats(add_git=1, add_annex=1)

    def assert_pipeline(pipeline):
        eq_(run_pipeline(pipeline), [{'datalad_stats': target_stats}])

    assert_pipeline([n1, n2])
    assert_pipeline([n1, [n2]])
    assert_pipeline([[n1], [n2]])
    assert_pipeline([n1, [n2, p]])
    assert_pipeline([[n1], n2])
    assert_pipeline([[n1, p], n2])
