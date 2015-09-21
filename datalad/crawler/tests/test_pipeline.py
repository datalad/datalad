# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import vcr

from ..nodes.crawl_url import crawl_url
from ..nodes.matches import *
from ..pipeline import run_pipeline

from ..nodes.misc import Sink

from datalad.tests.utils import eq_, ok_
from datalad.tests.utils import serve_path_via_http, with_tree

@vcr.use_cassette('fixtures/vcr_cassettes/openfmri.yaml')
def test_basic_openfmri_top_pipeline():
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
    all_aws_entries = sink2.get_fields('dataset', 'url_text', 'url')
    ok_(len(all_aws_entries) > len(urls))  # that we have at least as many ;-)
    #print('\n'.join(map(str, all_aws_entries)))
    all_licenses = sink_licenses.get_fields('dataset', 'url_text', 'url')
    eq_(len(all_licenses), len(urls))
    #print('\n'.join(map(str, all_licenses)))


# now with some recursive structure of directories
pages_loop = dict(
    tree=(
        ('index.html', '<html><body><a href="page2.html">page2</a></body></html>'),
        ('page2.html', '<html><body><a href="/">root</a></body></html>')))

@with_tree(**pages_loop)
@serve_path_via_http()
def test_recurse_loop_http(path, url):
    crawler = crawl_url(url)
    visited = []
    def visiting(url, **data):
        visited.append(url)
        yield data

    run_pipeline([
        crawler,
        a_href_match('.*'),
        crawler.recurse,
        visiting
    ])
    print visited