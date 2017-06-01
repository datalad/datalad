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
from ..nodes.misc import switch, assign, sub
from ..nodes.s3 import crawl_s3
from ..nodes.annex import Annexificator
from ...consts import DATALAD_SPECIAL_REMOTE

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri")


# Since all content of openfmri is anyways available openly, no need atm
# to use https which complicates proxying etc. Thus provide a node which
# would replace s3:// urls with regular http
# TODO:  we might want to make it an option for crawl_s3 to yield http urls
# so then we could just generalize this whole shebang into a single helper
# for crawling any S3 bucket.
# Right away think about having an 'incoming' branch and handling of versioned files
sub_s3_to_http = sub({
        'url': {'^s3://openfmri/': 'http://openfmri.s3.amazonaws.com/',
                '^s3://openneuro/': 'http://openneuro.s3.amazonaws.com/',
                }
    },
    ok_missing=True
)


def collection_pipeline(prefix=None):
    """Pipeline to crawl/annex an entire openfmri bucket"""

    lgr.info("Creating a pipeline for the openfmri bucket")
    annex = Annexificator(
        create=False,  # must be already initialized etc
        # Primary purpose of this one is registration of all URLs with our
        # upcoming "ultimate DB" so we don't get to git anything
        # options=["-c", "annex.largefiles=exclude=CHANGES* and exclude=changelog.txt and exclude=dataset_description.json and exclude=README* and exclude=*.[mc]"]
    )

    return [
        crawl_s3('openfmri', prefix=prefix, recursive=False, strategy='commit-versions', repo=annex.repo),
        sub_s3_to_http,
        switch('datalad_action',
               {  # TODO: we should actually deal with subdirs primarily
                   'commit': annex.finalize(tag=True),
                   # should we bother removing anything? not sure
                   # 'remove': annex.remove,
                   'annex':  annex,
                   'directory': [
                       # for initiate_dataset we should replicate filename as handle_name, prefix
                       assign({'prefix': '%(filename)s/', 'handle_name': '%(filename)s'}, interpolate=True),
                       annex.initiate_dataset(
                           template='openfmri_s3',
                           data_fields=['prefix'],
                       )
                   ]
               },
               missing='skip', # ok to not remove
              )
    ]


# TODO: make a unittest for all of this on a simple bucket

def pipeline(prefix=None, bucket='openfmri', tag=True, skip_problematic=False):
    """Pipeline to crawl/annex an entire openfmri bucket"""

    lgr.info("Creating a pipeline for the openfmri bucket")
    annex = Annexificator(
        create=False,  # must be already initialized etc
        #special_remotes=[DATALAD_SPECIAL_REMOTE],
        backend='MD5E',
        skip_problematic=skip_problematic,
        # Primary purpose of this one is registration of all URLs with our
        # upcoming "ultimate DB" so we don't get to git anything
        # options=["-c", "annex.largefiles=exclude=CHANGES* and exclude=changelog.txt and exclude=dataset_description.json and exclude=README* and exclude=*.[mc]"]
    )

    return [
        crawl_s3(bucket=bucket, prefix=prefix, strategy='commit-versions',
                 repo=annex.repo, recursive=True, exclude='\.git/'),
        sub_s3_to_http,
        switch('datalad_action',
               {
                   'commit': annex.finalize(tag=tag),
                   'remove': annex.remove,
                   'annex':  annex,
               })
    ]
