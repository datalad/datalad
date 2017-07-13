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
from os.path import lexists, join as opj

# Import necessary nodes
from ..nodes.misc import switch, assign, sub
from ..nodes.s3 import crawl_s3
from ..nodes.annex import Annexificator
from ...consts import DATALAD_SPECIAL_REMOTE
from ...support.strings import get_replacement_dict

from .simple_with_archives import pipeline as swa_pipeline
from datalad.utils import assure_bool

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
        'url': {'^s3://([^/]*)/': r'http://\1.s3.amazonaws.com/'}
    },
    ok_missing=True
)


# TODO: make a unittest for all of this on a simple bucket
# TODO:   branch option
def pipeline(bucket,
             prefix=None,
             no_annex=False,
             tag=True, skip_problematic=False, to_http=False,
             rename=None,
             directory=None,
             archives=False,
             allow_dirty=False,
             backend='MD5E',
             drop=False,
             drop_force=False,
             strategy='commit-versions',
             exclude=None,
             **kwargs):
    """Pipeline to crawl/annex an arbitrary bucket

    Parameters
    ----------
    bucket : str
    prefix : str, optional
      prefix within the bucket
    tag : bool, optional
      tag "versions"
    skip_problematic : bool, optional
      pass to Annexificator
    to_http : bool, optional
      Convert s3:// urls to corresponding generic http:// . So to be used for resources
      which are publicly available via http
    directory : {subdataset}, optional
      What to do when encountering a directory.  'subdataset' would initiate a new sub-dataset
      at that directory
    strategy : {'commit-versions', 'naive'}, optional
      What strategy to use whenever processing "delete" event, See `crawl_s3` node for more information.
    drop : bool, optional
      Drop all the files whenever done crawling
    exclude : str, optional
      Regular expression to be passed to s3_crawl to exclude some files
    **kwargs:
      passed into simple_with_archives.pipeline
    """

    lgr.info("Creating a pipeline for the %s bucket", bucket)

    # TODO: see if we could make it more generic!!!
    # drop = assure_bool(drop)
    # drop_force = assure_bool(drop_force)

    annex_kw = {}

    to_http = assure_bool(to_http)
    tag = assure_bool(tag)
    archives = assure_bool(archives)
    no_annex = assure_bool(no_annex)
    allow_dirty = assure_bool(allow_dirty)
    drop = assure_bool(drop)
    drop_force = assure_bool(drop_force)

    if not to_http:
        annex_kw['special_remotes'] = [DATALAD_SPECIAL_REMOTE]

    annex = Annexificator(
        create=False,  # must be already initialized etc
        backend=backend,
        no_annex=no_annex,
        skip_problematic=skip_problematic,
        allow_dirty=allow_dirty,
        # Primary purpose of this one is registration of all URLs with our
        # upcoming "ultimate DB" so we don't get to git anything
        # options=["-c", "annex.largefiles=exclude=CHANGES* and exclude=changelog.txt and exclude=dataset_description.json and exclude=README* and exclude=*.[mc]"]
        **annex_kw
    )

    s3_actions = {
        'commit': annex.finalize(tag=tag),
        'annex': annex
    }
    s3_switch_kw = {}
    recursive = True
    if directory:
        if directory == 'subdataset':
            new_prefix = '%(filename)s/'
            if prefix:
                new_prefix = opj(prefix, new_prefix)
            s3_actions['directory'] = [
                # for initiate_dataset we should replicate filename as handle_name, prefix
                assign({'prefix': new_prefix, 'dataset_name': '%(filename)s'}, interpolate=True),
                annex.initiate_dataset(
                    template='simple_s3',
                    data_fields=['prefix'],
                    add_fields={
                        'bucket': bucket,
                        'to_http': to_http,
                        'skip_problematic': skip_problematic,
                    }
                )
            ]
            s3_switch_kw['missing'] = 'skip'  # ok to not remove
            recursive = False
        else:
            raise ValueError("Do not know how to treat %s" % directory)
    else:
        s3_actions['remove'] = annex.remove

    incoming_pipeline = [
        crawl_s3(bucket, prefix=prefix, strategy=strategy, repo=annex.repo, recursive=recursive,
                 exclude=exclude),
    ]

    from ..nodes.misc import debug
    if to_http:
        incoming_pipeline.append(sub_s3_to_http)

    if rename:
        incoming_pipeline += [sub({'filename': get_replacement_dict(rename)},
                                  ok_missing=True)]

    incoming_pipeline.append(switch('datalad_action', s3_actions, **s3_switch_kw))

    if archives:
        pipeline = swa_pipeline(incoming_pipeline=incoming_pipeline, annex=annex,
                                **kwargs)
    else:
        pipeline = incoming_pipeline

    if drop:
        pipeline.append(annex.drop(all=True, force=drop_force))

    return pipeline
