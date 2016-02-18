# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling openfmri s3 bucket"""

import os
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import css_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import sub
from ..nodes.misc import func_to_node
from ..nodes.misc import find_files
from ..nodes.s3 import crawl_s3
from ..nodes.annex import Annexificator
from ...support.s3 import get_versioned_url
from ...utils import updated

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri")

def pipeline():
    """Pipeline to crawl/annex an entire openfmri bucket"""

    lgr.info("Creating a pipeline for the openfmri bucket")
    annex = Annexificator(
        create=False,  # must be already initialized etc
        # Primary purpose of this one is registration of all URLs with our
        # upcoming "ultimate DB" so we don't get to git anything
        # options=["-c", "annex.largefiles=exclude=CHANGES* and exclude=changelog.txt and exclude=dataset_description.json and exclude=README* and exclude=*.[mc]"]
    )

    return [
            crawl_s3('openfmri'),
            #crawl_s3('openfmri'),
            [  # if url present -- should be annexed
                annex,
            ],
            [  # if
                annex.finalize(tag=True),
            ]
           ]
