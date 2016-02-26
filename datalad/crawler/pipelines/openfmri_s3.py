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
from ..nodes.misc import switch
from ..nodes.s3 import crawl_s3
from ..nodes.annex import Annexificator
from ...consts import DATALAD_SPECIAL_REMOTE

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri")

def pipeline(prefix=None):
    """Pipeline to crawl/annex an entire openfmri bucket"""

    lgr.info("Creating a pipeline for the openfmri bucket")
    annex = Annexificator(
        create=False,  # must be already initialized etc
        special_remotes=[DATALAD_SPECIAL_REMOTE],
        backend='MD5E'
        # Primary purpose of this one is registration of all URLs with our
        # upcoming "ultimate DB" so we don't get to git anything
        # options=["-c", "annex.largefiles=exclude=CHANGES* and exclude=changelog.txt and exclude=dataset_description.json and exclude=README* and exclude=*.[mc]"]
    )

    return [
        crawl_s3('openfmri', prefix=prefix, strategy='commit-versions', repo=annex.repo),
        switch('datalad_action',
               {
                   'commit': annex.finalize(tag=True),
                   'remove': annex.remove,
                   'annex':  annex,
               })
    ]
