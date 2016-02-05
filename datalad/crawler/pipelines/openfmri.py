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
from ..nodes.crawl_url import __prune_to_the_next_version
from ..nodes.matches import css_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import sub
from ..nodes.misc import func_to_node
from ..nodes.misc import find_files
from ..nodes.annex import Annexificator
from ...support.s3 import get_versioned_url
from ...utils import updated

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri")

def extract_readme(data):
    # TODO - extract data from the page/response
    if lexists("README.txt"):
        os.unlink("README.txt")
    with open("README.txt", "w") as f:
        f.write("OpenfMRI dataset from %(url)s" % data)
    lgr.info("Generated README.txt")
    yield {'filename': "README.txt"}

def pipeline(dataset, versioned_urls=True, topurl="https://openfmri.org/dataset/"):
    """Pipeline to crawl/annex an openfmri dataset"""

    dataset_url = '%s%s' % (topurl, dataset)
    lgr.info("Creating a pipeline for the openfmri dataset %s" % dataset)
    annex = Annexificator(
        create=False,  # must be already initialized etc
        options=["-c", "annex.largefiles=exclude=*.txt and exclude=*.json and exclude=README* and exclude=*.[mc]"])

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
            [  # and collect all URLs under "AWS Link"
                # no longer valid
                #css_match('.field-name-field-aws-link a',
                #          xpaths={'url': '@href',
                #                  'url_text': 'text()'},
                #          min_count=1),
                # and don't know how to select all the a after h4
                # xpath('//h4[contains(text(), "Data:")]')
                # so let's just select all the ones going to /tarballs/
                # some are not on S3 yet, so no /tarballs/ prefix e.g. ds 158
                #a_href_match('.*/tarballs/.*\.(tgz|tar.*|zip)', min_count=1),
                a_href_match('.*/.*\.(tgz|tar.*|zip)', min_count=1),
                # Since all content of openfmri is anyways available openly, no need atm
                # to use https which complicates proxying etc. Thus replace for AWS urls
                # to openfmri S3 from https to http
                # TODO: might want to become an option for get_versioned_url? 
                sub({
                 'url': {
                   '(http)s?(://.*openfmri\.s3\.amazonaws.com/|://s3\.amazonaws\.com/openfmri/)': r'\1\2'
                }}),
                func_to_node(get_versioned_url,
                             data_args=['url'],
                             outputs=['url'],
                             kwargs={'guarantee_versioned': versioned_urls,
                                     'verify': True}),

                # TODO: we need to "version" those urls which we can version, e.g.,
                # if coming from versioned S3 buckets
                # version_url,
                # TODO TEMP -- too heavy, use some bogie for now
                #assign({'url': 'http://www.onerussian.com/tmp/ds005_raw_boogie.tgz'}),
                #assign({'url': 'http://www.onerussian.com/tmp/ds005_raw_boogie_2.tgz'}),
                #assign({'url': 'http://www.onerussian.com/tmp/ds005_raw_boogie_4.tgz'}),
                #assign({'filename': 'ds005_raw_boogie.tgz'}),

                annex,
            ],
            # Some of them ship their own license.txt, so let's just use that one
            # TODO: add a check and only if not present -- populate
            # [  # and license information
            #    css_match('.field-name-field-license a',
            #              xpaths={'url': '@href',
            #                      'url_text': 'text()'}),
            #    # TODO: HTML dump of that page for the license wouldn't be as useful I guess,
            #    # so let's provide our collection of most common referenced artifacts
            #    # in few formats
            #    assign({'filename': 'license.txt'}),
            #    annex,
            # ],
            # TODO: describe_handle
            # Now some true magic -- possibly multiple commits, 1 per each detected version!
            # Do not rename to stay consistent with single version commits... and stuff can change
            # for the same version I am afraid...
            annex.commit_versions('_R(?P<version>\d+[\.\d]*)(?=[\._])', rename=True),
            # D'oh -- but without rename, whenever we merge we end up with multiple per each version!
            # so we would then need to strip them again while in incoming, while needing to pass in
            # version to make it all robust etc... bleh
            # Alternative is to remove previous versions upon commit here BUT it would complicate crawling...
            # unless we finally introduce that DB with mtimes etc but allow it to list files which we remove
            # from within incoming
            # So -- either rename or remove!  Renaming would complicate when non-versioned also would be present
            # but is pretty much implemented already ATM, so let's proceed with rename!  When non-versioned would
            # appear we would treat it as prev version
        ],
        # TODO: since it is a very common pattern -- consider absorbing into e.g. add_archive_content?
        # [ {'loop': 'datalad_stats.flags.loop_versions',  # to loop while there is a flag in stats to process all the versions
        annex.switch_branch('incoming-processed'),
        [   # nested pipeline so we could skip it entirely if nothing new to be merged
            {'loop': True},  # loop for multiple versions merges
            annex.merge_branch('incoming', one_commit_at_a_time=True, strategy='theirs', commit=False),
            [   # Pipeline to augment content of the incoming and commit it to master
                # There might be archives within archives, so we need to loop
                {'loop': True},
                find_files("\.(zip|tgz|tar(\..+)?)$", fail_if_none=True),  #  we fail if none found -- there must be some! ;)),
                annex.add_archive_content(
                    existing='archive-suffix',
                    strip_leading_dirs=True,
                    leading_dirs_depth=1,
                    exclude=['(^|%s)\._' % os.path.sep],  # some files like '._whatever'
                    # overwrite=True,
                    # TODO: we might need a safeguard for cases if multiple subdirectories within a single tarball
                    #rename=
                ),
                # annex, # not needed since above add_archive_content adds to annex
            ],
            annex.switch_branch('master'),
            annex.merge_branch('incoming-processed', commit=True),
            annex.switch_branch('incoming-processed'),  # so we could possibly merge more
        ],
        annex.switch_branch('master'),
        # ] # finish the loop for versioned ones
        annex.finalize,
    ]
