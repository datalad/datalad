# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import join as opj

from ..nodes.crawl_url import crawl_url
from ..nodes.matches import *
from ..pipeline import run_pipeline, FinishPipeline

from ..nodes.misc import Sink, assign, range_node, interrupt_if
from ..nodes.annex import Annexificator, initiate_handle
from ..pipeline import load_pipeline_from_script

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


@skip_if_no_network
@use_cassette('fixtures/vcr_cassettes/openfmri.yaml')
def __test_basic_openfmri_top_pipeline():
    skip_if_no_module('scrapy')  # e.g. not present under Python3
    sink1 = Sink()
    sink2 = Sink()
    sink_licenses = Sink()
    pipeline = [
        crawl_url("https://openfmri.org/data-sets"),
        a_href_match(".*/dataset/(?P<dataset_dir>ds0*(?P<dataset>[1-9][0-9]*))$"),
        # if we wanted we could instruct to crawl inside
        [
            crawl_url(),
            [# and collect all URLs under "AWS Link"
                css_match('.field-name-field-aws-link a',
                           xpaths={'url': '@href',
                                   'url_text': 'text()'}),
                sink2
             ],
            [# and license information
                css_match('.field-name-field-license a',
                           xpaths={'url': '@href',
                                   'url_text': 'text()'}),
                sink_licenses
            ],
        ],
        sink1
    ]

    run_pipeline(pipeline)
    # we should have collected all the URLs to the datasets
    urls = [e['url'] for e in sink1.data]
    ok_(len(urls) > 20)  # there should be at least 20 listed there
    ok_(all([url.startswith('https://openfmri.org/dataset/ds00') for url in urls]))
    # got our dataset_dir entries as well
    ok_(all([e['dataset_dir'].startswith('ds0') for e in sink1.data]))

    # and sink2 should collect everything downloadable from under AWS Link section
    # test that we got all needed tags etc propagated properly!
    all_aws_entries = sink2.get_values('dataset', 'url_text', 'url')
    ok_(len(all_aws_entries) > len(urls))  # that we have at least as many ;-)
    #print('\n'.join(map(str, all_aws_entries)))
    all_licenses = sink_licenses.get_values('dataset', 'url_text', 'url')
    eq_(len(all_licenses), len(urls))
    #print('\n'.join(map(str, all_licenses)))


@skip_if_no_network
@use_cassette('fixtures/vcr_cassettes/openfmri-1.yaml')
@with_tempfile(mkdir=True)
def __test_basic_openfmri_dataset_pipeline_with_annex(path):
    skip_if_no_module('scrapy')  # e.g. not present under Python3
    dataset_index = 1
    dataset_name = 'ds%06d' % dataset_index
    dataset_url = 'https://openfmri.org/dataset/' + dataset_name
    # needs to be a non-existing directory
    handle_path = opj(path, dataset_name)
    # we need to pre-initiate handle
    list(initiate_handle('openfmri', dataset_index, path=handle_path)())

    annex = Annexificator(handle_path, create=False,  # must be already initialized etc
                          options=["-c", "annex.largefiles='exclude=*.txt'"])

    pipeline = [
        crawl_url(dataset_url),
        [  # and collect all URLs under "AWS Link"
            css_match('.field-name-field-aws-link a',
                      xpaths={'url': '@href',
                              'url_text': 'text()'}),
            # TODO:  here we need to provide means to rename some files
            # but first those names need to be extracted... pretty much
            # we need conditional sub-pipelines which do yield (or return?)
            # some result back to the main flow, e.g.
            # get_url_filename,
            # [ {'yield_result': True; },
            #   field_matches_re(filename='.*release_history.*'),
            #   assign({'filename': 'license:txt'}) ]
            annex,
        ],
        [  # and license information
            css_match('.field-name-field-license a',
                      xpaths={'url': '@href',
                              'url_text': 'text()'}),
            assign({'filename': 'license.txt'}),
            annex,
        ],
    ]

    run_pipeline(pipeline)


@with_tree(tree={
    'pipeline.py': 'pipeline = lambda: [1]',
    'pipeline2.py': 'pipeline = lambda x: [2*x]',
})
def test_load_pipeline_from_script(d):
    eq_(load_pipeline_from_script(opj(d, 'pipeline.py')), [1])
    eq_(load_pipeline_from_script(opj(d, 'pipeline2.py'), x=2), [4])
    assert_raises(RuntimeError, load_pipeline_from_script, opj(d, 'unlikelytobethere.py'))


def test_pipeline_linear_simple():
    sink = Sink()
    pipeline = [
        range_node(2, "out1"),
        range_node(3, "out2"),
        sink
    ]
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, [{}])  # by default 'input' is output and input is made empty dict if not provided
    eq_(sink.data, [{'out1': 0, 'out2': 0}, {'out1': 0, 'out2': 1}, {'out1': 0, 'out2': 2},
                    {'out1': 1, 'out2': 0}, {'out1': 1, 'out2': 1}, {'out1': 1, 'out2': 2}])

    # if we extend pipeline with matching interrupt_if, the entire pipeline should
    # stop at that matching point, but otherwise there should be no crash etc
    sink.clean()
    pipeline_output = run_pipeline(pipeline + [interrupt_if({'out1': 0, 'out2': 1})])
    eq_(pipeline_output, [{}])
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
    eq_(pipeline_output, [{}])
    eq_(sink.data, all_pairs)
    # and output is not seen outside of the nested pipeline
    eq_(sink2.data, [{'out1': 0}, {'out1': 1}])

    # Let's make nested pipeline yield all
    sink.clean()
    sink2.clean()
    pipeline[1].insert(0, {'output': 'outputs'})

    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, [{}])  # by default no output produced
    eq_(sink.data, all_pairs)
    # and output was passed outside from the nested pipeline
    eq_(sink2.data, all_pairs)

    # Let's make it yield the last-output one
    sink2.clean()
    pipeline[1][0] = {'output': 'last-output'}
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, [{}])  # by default no output produced
    # only the last output from the nested pipeline appeared outside
    eq_(sink2.data, [{'out1': 0, 'out2': 2}, {'out1': 1, 'out2': 2}])

    # Let's now add output to the top-most pipeline
    pipeline.insert(0, {'output': 'outputs'})
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, [{'out1': 0, 'out2': 2}, {'out1': 1, 'out2': 2}])

    # and if we ask only for the last one
    pipeline[0] = {'output': 'last-output'}
    pipeline_output = run_pipeline(pipeline)
    eq_(pipeline_output, [{'out1': 1, 'out2': 2}])

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
    eq_(pipeline_output, [{'x': 1}, {'x': 2}, {'x': 3}])


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
