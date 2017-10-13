# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling openfmri dataset"""

import os
import re
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import css_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import sub
from ..nodes.misc import switch
from ..nodes.misc import func_to_node
from ..nodes.misc import find_files
from ..nodes.misc import skip_if
from ..nodes.misc import debug
from ..nodes.misc import fix_permissions
from ..nodes.annex import Annexificator
from ...support.s3 import get_versioned_url
from ...utils import updated
from ...consts import ARCHIVES_SPECIAL_REMOTE, DATALAD_SPECIAL_REMOTE
from datalad.downloaders.providers import Providers

# For S3 crawling
from ..nodes.s3 import crawl_s3
from .openfmri_s3 import pipeline as s3_pipeline
from datalad.api import ls
from datalad.dochelpers import exc_str

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri")

TOPURL = "https://openfmri.org/dataset/"


# define a pipeline factory function accepting necessary keyword arguments
# Should have no strictly positional arguments
def superdataset_pipeline(url=TOPURL, **kwargs):
    annex = Annexificator(no_annex=True, allow_dirty=True)
    lgr.info("Creating a pipeline with kwargs %s" % str(kwargs))
    return [
        crawl_url(url),
        a_href_match("(?P<url>.*/dataset/(?P<dataset>ds0*(?P<dataset_index>[0-9a-z]*)))/*$"),
        # https://openfmri.org/dataset/ds000001/
        assign({'dataset_name': '%(dataset)s'}, interpolate=True),
        # skip_if({'dataset_name': 'ds000017'}), # was split into A/B
        # TODO:  crawl into the dataset url, and check if there is any tarball available
        # if not -- do not bother (e.g. ds000053)
        annex.initiate_dataset(
            template="openfmri",
            data_fields=['dataset'],
            # let's all specs and modifications reside in master
            # branch='incoming',  # there will be archives etc
            existing='skip'
            # further any additional options
        )
    ]


def extract_readme(data):
    # TODO - extract data from the page/response
    if lexists("README.txt"):
        os.unlink("README.txt")
    with open("README.txt", "w") as f:
        f.write("OpenfMRI dataset from %(url)s" % data)
    lgr.info("Generated README.txt")
    yield {'filename': "README.txt",
           # TODO: think how we should sweat about this one
           # 'datalad_stats': data['datalad_stats']
           }


def pipeline(dataset,
             versioned_urls=True, topurl=TOPURL,
             versions_overlay_level=2,
             leading_dirs_depth=1,
             prefix='',
             s3_prefix=None):
    """Pipeline to crawl/annex an openfmri dataset

    Parameters
    ----------
    dataset: str
      Id of the OpenfMRI dataset (e.g. ds000001)
    versioned_urls: bool, optional
      Request versioned URLs.  OpenfMRI bucket is versioned, but if
      original data resides elsewhere, set to False
    topurl: str, optional
      Top level URL to the datasets.
    prefix: str, optional
      Prefix regular expression in urls to identifying subgroup of data to be
      fetched in the dataset
      (e.g. in case of ds000017 there is A and B)
    s3_prefix: str or None, optional
      Either to crawl per-dataset subdirectory in the bucket into incoming-s3
      branch, to also annex also all the extracted files available from openfmri
      bucket.  If None -- we determine depending on availability of the
      sub-directory on S3 bucket
    """
    skip_no_changes = True    # to redo incoming-processed, would finish dirty in incoming-processed
                              # when commit would fail since nothing to commit
    leading_dirs_depth = int(leading_dirs_depth)
    versions_overlay_level = int(versions_overlay_level)
    dataset_url = '%s%s/' % (topurl, dataset)
    lgr.info("Creating a pipeline for the openfmri dataset %s" % dataset)

    special_remotes = [ARCHIVES_SPECIAL_REMOTE]

    if s3_prefix is None:
        # some datasets available (fresh enough or old) from S3, so let's sense if this one is
        # s3_prefix = re.sub('^ds0*([0-9]{3})/*', r'ds\1/', dataset)  # openfmri bucket
        s3_prefix = dataset
        # was relevant only for openfmri bucket. for openneuro -- it is all under the same
        # directory, separated deep inside between A and B, so we just crawl for both
        # if dataset == 'ds000017':
        #     # we had some custom prefixing going on
        #     assert(prefix)
        #     suf = prefix[-3]
        #     assert suf in 'AB'
        #     s3_prefix = 'ds017' + suf

        openfmri_s3_prefix = 's3://openneuro/'
        try:
            if not ls('%s%s' % (openfmri_s3_prefix, s3_prefix)):
                s3_prefix = None  # not there
        except Exception as exc:
            lgr.warning(
                "Failed to access %s, not attempting to crawl S3: %s",
                s3_prefix, exc_str(exc)
            )
            s3_prefix = None

    if s3_prefix:
        # actually not needed here since we are remapping them to public http
        #  urls
        # special_remotes += [DATALAD_SPECIAL_REMOTE]
        pass


    annex = Annexificator(
        create=False,  # must be already initialized etc
        # leave in Git only obvious descriptors and code snippets -- the rest goes to annex
        # so may be eventually we could take advantage of git tags for changing layout
        statusdb='json',
        special_remotes=special_remotes,
        # all .txt and .json in root directory (only) go into git!
        options=["-c",
                 "annex.largefiles="
                 # ISSUES LICENSE Makefile
                 "exclude=Makefile and exclude=LICENSE* and exclude=ISSUES*"
                 " and exclude=CHANGES* and exclude=README* and exclude=ReadMe.txt"
                 " and exclude=*.[mc] and exclude=dataset*.json and exclude=license.txt"
                 " and (exclude=*.txt or include=*/*.txt)"
                 " and (exclude=*.json or include=*/*.json)"
                 " and (exclude=*.tsv or include=*/*.tsv)"
                 ])

    if s3_prefix:
        # a sub-pipeline to crawl s3 bucket
        s3_pipeline_here = \
            [
                [
                    annex.switch_branch('incoming-s3-openneuro'),
                    s3_pipeline(s3_prefix, bucket='openneuro', tag=False), # for 31 ;) skip_problematic=True),
                    annex.switch_branch('master'),
                ]
            ]
    else:
        s3_pipeline_here = []

    # common kwargs which would later would be tuned up
    def add_archive_content(**kw):
        if 'leading_dirs_depth' not in kw:
            kw['leading_dirs_depth'] = leading_dirs_depth
        if 'strip_leading_dirs' not in kw:
            kw['strip_leading_dirs'] = bool(leading_dirs_depth)
        return annex.add_archive_content(
            existing='archive-suffix',
            delete=True,
            exclude=['(^|%s)\._' % os.path.sep],  # some files like '._whatever'
            **kw
        # overwrite=True,
        # TODO: we might need a safeguard for cases when multiple subdirectories within a single tarball
        )

    return s3_pipeline_here + [
        # optionally "log" to annex extracted content available on openfmri S3
        annex.switch_branch('incoming'),
        [   # nested pipeline so we could quit it earlier happen we decided that nothing todo in it
            # but then we would still return to 'master' branch
            crawl_url(dataset_url),
            [  # changelog XXX there might be multiple, e.g. in case of ds000017
               a_href_match(".*%srelease_history.txt" % prefix),  # , limit=1
               assign({'filename': 'changelog.txt'}),
               annex,
            ],
            # Moving to proper meta-data descriptors, so no need to generate and possibly conflict
            # with distributed one README
            # [  # README
            #    # Somewhat sucks here since 'url' from above would be passed all the way to annex
            #    # So such nodes as extract_readme should cleans the data so only relevant pieces are left
            #    extract_readme,
            #    annex,
            # ],
            [  # and collect all URLs pointing to tarballs
                a_href_match('.*/%s.*\.(tgz|tar.*|zip)' % prefix, min_count=1),
                # Since all content of openfmri is anyways available openly, no need atm
                # to use https which complicates proxying etc. Thus replace for AWS urls
                # to openfmri S3 from https to http
                # TODO: might want to become an option for get_versioned_url?
                sub({
                 'url': {
                   '(http)s?(://.*openfmri\.s3\.amazonaws.com/|://s3\.amazonaws\.com/openfmri/)': r'\1\2'}}),
                func_to_node(get_versioned_url,
                             data_args=['url'],
                             outputs=['url'],
                             kwargs={'guarantee_versioned': versioned_urls,
                                     'verify': True}),
                annex,
            ],
            # TODO: describe_dataset
            # Now some true magic -- possibly multiple commits, 1 per each detected **new** version!
            # this one doesn't go through all files, but only through the freshly staged!
            annex.commit_versions(
                '_R(?P<version>\d+[\.\d]*)(?=[\._])',
                always_versioned='ds\d\d+.*',
                unversioned='default',
                default='1.0.0'),
        ],
        annex.remove_obsolete(),  # should be called while still within incoming but only once
        # TODO: since it is a very common pattern -- consider absorbing into e.g. add_archive_content?
        [   # nested pipeline so we could skip it entirely if nothing new to be merged
            {'loop': not skip_no_changes},  # loop for multiple versions merges
            annex.switch_branch('incoming-processed'),
            annex.merge_branch('incoming',
                               one_commit_at_a_time=True, strategy='theirs', commit=False,
                               skip_no_changes=skip_no_changes
                               ),
            # still we would have all the versions present -- we need to restrict only to the current one!
            # TODO:  we often need ability to augment next node options by checks etc in the previous ones
            # e.g. ehere overlay option depending on which dataset/version being processed
            annex.remove_other_versions('incoming',
                                        remove_unversioned=True,
                                        # ds001.tar.gz  could then become ds0000001.zip
                                        fpath_subs=[
                                            # ad-hoc fixups for some datasets
                                            ('ds005\.tgz', 'ds005_raw.tgz'),
                                            # had it split into this one with derived data separately and then joined
                                            ('ds007_01-20\.tgz', 'ds007_raw.tgz'),
                                            ('ds000107_raw\.', 'ds000107.'),
                                            # generic
                                            ('^ds0*', '^ds'),
                                            ('\.(zip|tgz|tar\.gz)$', '.ext')
                                        ],
                                        # Had manually to do this for this one since there was a switch from
                                        # overlay layout to even bigger single one within a minor 2.0.1 "release"
                                        # 158 -- 1.0.1 changed layout completely so should not be overlayed ATM
                                        overlay=None
                                            if dataset in ('ds000007', 'ds000114', 'ds000119', 'ds000158')
                                            else versions_overlay_level,  # use major.minor to define overlays
                                        #overlay=None, # use major.minor to define overlays
                                        exclude='(README|changelog).*'),
            [   # Pipeline to augment content of the incoming and commit it to master
                # There might be archives within archives, so we need to loop
                {'loop': True},
                find_files("\.(zip|tgz|tar(\..+)?)$", fail_if_none=True),  #  we fail if none found -- there must be some! ;)),
                assign({'dataset_file': dataset + '///%(filename)s'}, interpolate=True),
                switch(
                    'dataset_file',
                    {
                        'ds0*158///aalmasks\.zip$': add_archive_content(add_archive_leading_dir=True),
                        '.*///ds000030_R1\.0\.1_metadata\.tgz': add_archive_content(leading_dirs_depth=4),
                    },
                    default=add_archive_content(),
                    re=True,
                ),
            ],
            [
                find_files("(\.(tsv|csv|txt|json|gz|bval|bvec|hdr|img|m|mat|pdf|png|zip|nii|jpg|fif|fig)|README|CHANGES)$"),
                fix_permissions(executable=False)
            ],
            annex.switch_branch('master'),
            annex.merge_branch('incoming-processed', commit=True, allow_unrelated=True),
            annex.finalize(tag=True, aggregate=True),
        ],
        annex.switch_branch('master'),
        annex.finalize(cleanup=True, aggregate=True),
        # TODO:  drop all files which aren't in master or incoming  since now many extracted arrive from s3
        #  - no need to keep all versions locally for all of them

    ]
