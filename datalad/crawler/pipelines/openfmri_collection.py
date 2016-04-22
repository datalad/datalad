# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling openfmri collection of datasets"""

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import a_href_match
from ..nodes.annex import Annexificator
from ..nodes.misc import assign

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri_collection")


# define a pipeline factory function accepting necessary keyword arguments
# Should have no strictly positional arguments
def pipeline(url="https://openfmri.org/dataset/", **kwargs):
    annex = Annexificator()
    lgr.info("Creating a pipeline with kwargs %s" % str(kwargs))
    return [
        crawl_url(url),
        a_href_match("(?P<url>.*/dataset/(?P<dataset>ds0*(?P<dataset_index>[0-9a-z]*)))/*$"),
        # https://openfmri.org/dataset/ds000001/
        assign({'handle_name': '%(dataset)s'}, interpolate=True),
        annex.initiate_handle(
            template="openfmri",
            data_fields=['dataset'],
            # let's all specs and modifications reside in master
            # branch='incoming',  # there will be archives etc
            existing='skip'
            # further any additional options
        )
    ]
