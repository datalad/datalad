# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A template (non-functional) for crawler pipelines"""

# Import necessary nodes
from ..nodes.crawl_url import crawl_url

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.template")

# define a pipeline generator as a function accepting necessary keyword arguments
# Should have no strictly positional arguments
def pipeline(
        # e.g. could be listed as explicit keyword arguments
        #url="http://example.com", depth=2, ...
        **kwargs
    ):
    lgr.info("Creating a pipeline with kwargs %s" % str(kwargs))
    # Should return a list representing a pipeline
    return []