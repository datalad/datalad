# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling NIMH data archive"""


# Import necessary nodes
from ..nodes.misc import assign
from ..nodes.misc import switch
from ..nodes.misc import continue_if
from ..nodes.matches import a_href_match
from ..nodes.s3 import crawl_s3
from ..nodes.annex import Annexificator
from ...consts import DATALAD_SPECIAL_REMOTE

from datalad.support.nda_ import get_oracle_db
from datalad.support.nda_ import image03_fields, image03_file_fields
from datalad.support.nda_ import image03_Record
from datalad.utils import auto_repr, updated


# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.nda")

DEFAULT_BUCKET = 'NDAR_Central'


def collection_pipeline(bucket=DEFAULT_BUCKET, prefix=None):
    """Pipeline to crawl/annex an entire openfmri bucket"""

    lgr.info("Creating a pipeline for the openfmri bucket")
    annex = Annexificator(
        create=False,  # must be already initialized etc
    )
    sprefix = prefix + '/' if prefix else ''
    return [
        crawl_s3(bucket, prefix=prefix, recursive=False,
                 strategy='commit-versions', repo=annex.repo,
                 versioned=False),
        switch('datalad_action',
               {  # TODO: we should actually deal with subdirs primarily
                   'commit': annex.finalize(tag=True),
                   # should we bother removing anything? not sure
                   # 'remove': annex.remove,
                   'annex':  annex,
                   'directory': [
                       # for initiate_dataset we should replicate filename as handle_name, prefix
                       assign({
                           'prefix': sprefix + '%(filename)s/',
                           'bucket': bucket,
                           'handle_name': '%(filename)s'
                       }, interpolate=True),
                       annex.initiate_dataset(
                           template='nda',
                           data_fields=['bucket', 'prefix'],
                       )
                   ]
               },
               missing='skip',  # ok to not remove
        ),
    ]


def bucket_pipeline(bucket=DEFAULT_BUCKET, prefix=None):
    """Pipeline to crawl/annex NDA bucket"""

    lgr.info("Creating a pipeline for the NDA bucket")
    annex = Annexificator(
        create=False,  # must be already initialized etc
        special_remotes=[DATALAD_SPECIAL_REMOTE],
        backend='MD5E'
        # Primary purpose of this one is registration of all URLs with our
        # upcoming "ultimate DB" so we don't get to git anything
        # options=["-c", "annex.largefiles=exclude=CHANGES* and exclude=changelog.txt and exclude=dataset_description.json and exclude=README* and exclude=*.[mc]"]
    )

    return [
        crawl_s3(bucket,
                 prefix=prefix, strategy='commit-versions',
                 repo=annex.repo, versioned=False),
        switch('datalad_action',
               {
                   'commit': annex.finalize(tag=True),
                   'remove': annex.remove,
                   'annex':  annex,
                   'directory': None,
               })
    ]


@auto_repr
class crawl_mindar_images03(object):
    """Crawl miNDAR DB for a given collection

    TODO: generalize for other data structures other than image03, with their
    own sets of "File" fields

    Parameters
    ----------
    collection
    """
    def __init__(self, collection):
        self.collection = collection

    def __call__(self, data):

        db = get_oracle_db()

        query = "SELECT %s FROM IMAGE03 WHERE COLLECTION_ID=%s" \
                % (','.join(image03_fields), self.collection)
        c = db.cursor()
        c.execute(query)
        # query and wrap into named tuples to ease access
        #import ipdb; ipdb.set_trace()
        for rec in c.fetchall():  # TODO -- better access method?
            rec = image03_Record(*rec)
            for field in image03_file_fields:
                url = getattr(rec, field)
                if url:
                    # generate a new
                    yield updated(data, {
                        'url': url,
                    })
        c.close()


def pipeline(collection, archives=None):
    """Pipeline to crawl/annex NDA

    Parameters
    ----------
    archives:
      Idea is to be able to control how archives treated -- extracted within
      the same repository, or extracted into a submodule. TODO
    """

    assert archives is None, "nothing else is implemented"
    lgr.info("Creating a pipeline for the NDA bucket")

    annex = Annexificator(
        create=False,  # must be already initialized etc
        special_remotes=[DATALAD_SPECIAL_REMOTE],
        backend='MD5E',
        skip_problematic=True,  # TODO: make it cleaner for detection of s3 "directories"
        # Primary purpose of this one is registration of all URLs with our
        # upcoming "ultimate DB" so we don't get to git anything
        # options=["-c", "annex.largefiles=exclude=CHANGES* and exclude=changelog.txt and exclude=dataset_description.json and exclude=README* and exclude=*.[mc]"]
    )

    return [
        [
            assign(
                {'url': 'https://ndar.nih.gov/edit_collection.html?id=%s' % collection,
                 'filename': 'collection.html'}
            ),
            annex,
        ],
        [
            crawl_mindar_images03(collection),
            continue_if({'url': "s3://(?P<bucket>[^/]*)/submission_(?P<url_submission_id>[0-9]*)/(?P<filename>.*[^/])$"}, re=True),
            annex,
            # TODO: add annex tags may be for dataset_id, submission_id, 
        ],
    ]