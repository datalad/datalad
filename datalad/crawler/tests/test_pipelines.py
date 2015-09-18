# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import vcr

from ..newmain import crawl_url
from ..matches import *
from ..pipeline import run_pipeline

class DataSink(object):
    def __init__(self):
        self.data = []
    def __call__(self, **data):
        # ??? for some reason didn't work when I made entire thing a list
        self.data.append(data)
        yield data

@vcr.use_cassette('fixtures/vcr_cassettes/openfmri.yaml')
def test_basic_openfmri_top_pipeline():
    sink1 = DataSink()
    sink2 = DataSink()
    pipeline = [
        crawl_url("https://openfmri.org/data-sets"),
        a_href_match(".*/dataset/(?P<dataset_dir>ds0*(?P<dataset>[1-9][0-9]*))$"),
        # if we wanted we could instruct to crawl inside
        [crawl_url(),
         # and collect all URLs under "AWS Link"
         css_match('.field-name-field-aws-link a',
                   xpaths={'url': '@href',
                           'url_text': 'text()'}),
         sink2],
        sink1
    ]

    run_pipeline(pipeline)
    # we should have collected all the URLs to the datasets
    urls = [e['url'] for e in sink1.data]
    assert(len(urls) > 20)  # there should be at least 20 listed there
    assert(all([url.startswith('https://openfmri.org/dataset/ds00') for url in urls]))
    # got our dataset_dir entries as well
    assert(all([e['dataset_dir'].startswith('ds0') for e in sink1.data]))

    # and sink2 should collect everything downloadable from under AWS Link section
    # test that we got all needed tags etc propagated properly!
    all_aws_entries = [(d['dataset'], d['url_text'], d['url']) for d in sink2.data]
    assert(len(all_aws_entries) > len(urls)) # that we have at least as many ;-)
    #print('\n'.join(map(str, all_aws_entries)))

