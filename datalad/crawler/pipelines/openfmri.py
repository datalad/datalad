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
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import css_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import sub
from ..nodes.misc import switch
from ..nodes.misc import func_to_node
from ..nodes.misc import find_files
from ..nodes.annex import Annexificator
from ...support.s3 import get_versioned_url
from ...utils import updated
from ...consts import ARCHIVES_SPECIAL_REMOTE

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri")

TOPURL = "https://openfmri.org/dataset/"


# define a pipeline factory function accepting necessary keyword arguments
# Should have no strictly positional arguments
def superdataset_pipeline(url=TOPURL, **kwargs):
    annex = Annexificator(no_annex=True)
    lgr.info("Creating a pipeline with kwargs %s" % str(kwargs))
    return [
        crawl_url(url),
        a_href_match("(?P<url>.*/dataset/(?P<dataset>ds0*(?P<dataset_index>[0-9a-z]*)))/*$"),
        # https://openfmri.org/dataset/ds000001/
        assign({'dataset_name': '%(dataset)s'}, interpolate=True),
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


def pipeline(dataset, versioned_urls=True, topurl=TOPURL, leading_dirs_depth=1):
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
    """
    skip_no_changes = True    # to redo incoming-processed, would finish dirty in incoming-processed
                              # when commit would fail since nothing to commit
    leading_dirs_depth = int(leading_dirs_depth)
    dataset_url = '%s%s/' % (topurl, dataset)
    lgr.info("Creating a pipeline for the openfmri dataset %s" % dataset)
    annex = Annexificator(
        create=False,  # must be already initialized etc
        # leave in Git only obvious descriptors and code snippets -- the rest goes to annex
        # so may be eventually we could take advantage of git tags for changing layout
        statusdb='json',
        special_remotes=[ARCHIVES_SPECIAL_REMOTE],
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

    # common kwargs which would later would be tuned up
    def add_archive_content(**kw):
        return annex.add_archive_content(
            existing = 'archive-suffix',
            strip_leading_dirs = bool(leading_dirs_depth),
            leading_dirs_depth = leading_dirs_depth,
            delete = True,
            exclude = ['(^|%s)\._' % os.path.sep],  # some files like '._whatever'
            **kw
        # overwrite=True,
        # TODO: we might need a safeguard for cases when multiple subdirectories within a single tarball
        )

    return [
        annex.switch_branch('incoming'),
        [   # nested pipeline so we could quit it earlier happen we decided that nothing todo in it
            # but then we would still return to 'master' branch
            crawl_url(dataset_url),
            [  # changelog
               a_href_match(".*release_history.txt"),  # , limit=1
               assign({'filename': 'changelog.txt'}),
               annex,
            ],
            [  # README
               # Somewhat sucks here since 'url' from above would be passed all the way to annex
               # So such nodes as extract_readme should cleans the data so only relevant pieces are left
               extract_readme,
               annex,
            ],
            [  # and collect all URLs pointing to tarballs
                a_href_match('.*/.*\.(tgz|tar.*|zip)', min_count=1),
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
            # Now some true magic -- possibly multiple commits, 1 per each detected new version!
            annex.commit_versions('_R(?P<version>\d+[\.\d]*)(?=[\._])', unversioned='default', default='1.0.0'),
        ],
        annex.remove_obsolete(),  # should be called while still within incoming but only once
        # TODO: since it is a very common pattern -- consider absorbing into e.g. add_archive_content?
        [   # nested pipeline so we could skip it entirely if nothing new to be merged
            {'loop': not skip_no_changes},  # loop for multiple versions merges
            annex.switch_branch('incoming-processed'),
            annex.merge_branch('incoming', one_commit_at_a_time=True, strategy='theirs', commit=False,
                               skip_no_changes=skip_no_changes
                               ),
            # still we would have all the versions present -- we need to restrict only to the current one!
            annex.remove_other_versions('incoming', remove_unversioned=True, exclude='(README|changelog).*'),
            [   # Pipeline to augment content of the incoming and commit it to master
                # There might be archives within archives, so we need to loop
                {'loop': True},
                find_files("\.(zip|tgz|tar(\..+)?)$", fail_if_none=True),  #  we fail if none found -- there must be some! ;)),
                assign({'dataset_file': dataset + '///%(filename)s'}, interpolate=True),
                switch(
                    'dataset_file',
                    {'ds0*158///aalmasks\.zip$': add_archive_content(add_archive_leading_dir=True)},
                    default=add_archive_content(),
                    re=True,
                ),
            ],
            annex.switch_branch('master'),
            annex.merge_branch('incoming-processed', commit=True),
            annex.finalize(tag=True),
        ],
        annex.switch_branch('master'),
        annex.finalize(cleanup=True),
    ]
