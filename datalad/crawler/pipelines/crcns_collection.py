# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling crcns collection of datasets"""

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import a_href_match
from ..nodes.annex import initiate_handle
from ..nodes.misc import assign

from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.crcns_collection")

def pipeline(**kwargs):

    lgr.info("Creating a pipeline with kwargs %s" % str(kwargs))
    # Should return a list representing a pipeline
    # TODO: get to 'incoming branch'
    return [
        crawl_url("http://crcns.org/data-sets",
            matchers=[a_href_match('.*/data-sets/[^#/]+$')]),
#                      a_href_match('.*/data-sets/[\S+/\S+'),]),
        # TODO:  such matchers don't have state so if they get to the same url from multiple
        # pages they pass that content twice.  Implement state to remember yielded results +
        # .reset() for nodes with state so we could first get through the pipe elements and reset
        # them all
        a_href_match("(?P<url>.*/data-sets/(?P<dataset_category>[^/#]+)/(?P<dataset>[^_/#]+))$"),
        # https://openfmri.org/dataset/ds000001/
        assign({'handle_name': '%(dataset)s'}, interpolate=True),
        initiate_handle(
            template="crcns",
            data_fields=['dataset_category', 'dataset'],
            branch='incoming',  # there will be archives etc
            existing='adjust',
            # further any additional options
        )
    ]
