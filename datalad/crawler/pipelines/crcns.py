# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling a crcns dataset"""

# Import necessary nodes
import os
from ..nodes.crawl_url import crawl_url
from ..nodes.crawl_url import parse_checksums
from ..nodes.matches import css_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import find_files
from ..nodes.misc import sub
from ..nodes.misc import skip_if
from ..nodes.annex import Annexificator
from ...consts import DATALAD_SPECIAL_REMOTE, ARCHIVES_SPECIAL_REMOTE
from ...support.strings import get_replacement_dict

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.crcns")


def superdataset_pipeline():
    lgr.info("Creating a CRCNS collection pipeline")
    # Should return a list representing a pipeline
    annex = Annexificator(no_annex=True)
    return [
        crawl_url("http://crcns.org/data-sets",
            matchers=[a_href_match('.*/data-sets/[^#/]+$')]),
#                      a_href_match('.*/data-sets/[\S+/\S+'),]),
        # TODO:  such matchers don't have state so if they get to the same url from multiple
        # pages they pass that content twice.  Implement state to remember yielded results +
        # .reset() for nodes with state so we could first get through the pipe elements and reset
        # them all
        a_href_match("(?P<url>.*/data-sets/(?P<dataset_category>[^/#]+)/(?P<dataset>[^_/#]+))$"),
        # http://crcns.org/data-sets/vc/pvc-1
        assign({'dataset_name': '%(dataset)s'}, interpolate=True),
        annex.initiate_dataset(
            template="crcns",
            data_fields=['dataset_category', 'dataset'],
            # branch='incoming',  # there will be archives etc
            existing='skip',
            # further any additional options
        )
    ]


def extract_readme(data):
    # TODO - extract data from the page/response  but not into README I guess since majority of datasets
    # already provide README
    if os.path.exists("README.txt"):
        os.unlink("README.txt")
    with open("README.txt", "w") as f:
        f.write("CRCNS dataset from %(url)s" % data)
    lgr.info("Generated README.txt")
    yield {'filename': "README.txt"}


# we might need to explicitly specify for some datasets to use_current_dir since
# archives are already carrying the leading directory anyways...
# actually probably wouldn't scale since within the same dataset we might need
# some tarballs extracted one way, some other... so we might better rely on
# stripping dirs in general BUT need to provide some sophistication, e.g. strip
# iff directory matches archive name (without archive suffix)
# hc-3 dataset is a good example of a mix etc... or may be just a parameter for
# how many to strip (currently 2), but then we need to take care bout converting
# if provided as a str from config
def pipeline(dataset, dataset_category, versioned_urls=False, tarballs=True,
             data_origin='checksums', use_current_dir=False,
             leading_dirs_depth=2, rename=None):
    """Pipeline to crawl/annex an crcns dataset"""

    if not isinstance(leading_dirs_depth, int):
        leading_dirs_depth = int(leading_dirs_depth)

    dataset_url = 'http://crcns.org/data-sets/{dataset_category}/{dataset}'.format(**locals())
    lgr.info("Creating a pipeline for the crcns dataset %s" % dataset)
    annex = Annexificator(
        create=False,  # must be already initialized etc
        backend="MD5E",
        statusdb='json',
        special_remotes=[DATALAD_SPECIAL_REMOTE, ARCHIVES_SPECIAL_REMOTE],
        # many datasets are actually quite small, so we can simply git them up
        # below one didn't work out as it should have -- caused major headache either due to bug here or in annex
        # and comitting to git large .mat and .h5 files
        # options=["-c", "annex.largefiles=exclude=*.txt and exclude=README and (largerthan=100kb or include=*.gz or include=*.zip)"]
        #
        # CRCNS requires authorization, so only README* should go straight under git
        options=["-c", "annex.largefiles=exclude=README*"]
    )

    crawler = crawl_url(dataset_url)
    if data_origin == 'checksums':
        urls_pipe = [   # Download from NERSC
            # don't even bother finding the link (some times only in about, some times also on the main page
            # just use https://portal.nersc.gov/project/crcns/download/<dataset_id>
            # actually to not mess with crawling a custom index let's just go by checksums.md5
            crawl_url("https://portal.nersc.gov/project/crcns/download/{dataset}/checksums.md5".format(**locals())),
            parse_checksums(digest='md5'),
            # they all contain filelist and checksums.md5 which we can make use of without explicit crawling
            # no longer valid
            # TODO:  do not download checksums.md (annex would do it) and filelist.txt (includes download
            #   instructions which might confuse, not help)
            skip_if({'url': '(checksums.md5|filelist.txt)$'}, re=True),
        ]
    elif data_origin == 'urls':
        urls_pipe = [ # Download all the archives found on the project page
            crawler,
            a_href_match('.*/.*\.(tgz|tar.*|zip)', min_count=1),
        ]
    else:
        raise ValueError(data_origin)

    if rename:
        urls_pipe += [sub({'filename': get_replacement_dict(rename)})]

    return [
        annex.switch_branch('incoming'),
        [   # nested pipeline so we could quit it earlier happen we decided that nothing todo in it
            # but then we would still return to 'master' branch
            # [   # README
            #     crawler,
            #     # Somewhat sucks here since 'url' from above would be passed all the way to annex
            #     # So such nodes as extract_readme should cleans the data so only relevant pieces are left
            #     a_href_match(".*/data.*sets/.*about.*"),
            #     crawler.recurse,
            #     extract_readme,
            #     annex,
            # ],
            urls_pipe + [
                annex,
            ],
        ],
        annex.switch_branch('incoming-processed'),
        [   # nested pipeline so we could skip it entirely if nothing new to be merged
            annex.merge_branch('incoming', strategy='theirs', commit=False),  #, skip_no_changes=False),
            [   # Pipeline to augment content of the incoming and commit it to master
                find_files("\.(zip|tgz|tar(\..+)?)$", fail_if_none=tarballs),  # So we fail if none found -- there must be some! ;)),
                annex.add_archive_content(
                    existing='archive-suffix',
                    # Since inconsistent and seems in many cases no leading dirs to strip, keep them as provided
                    strip_leading_dirs=True,
                    delete=True,
                    leading_dirs_consider=['crcns.*', dataset],
                    leading_dirs_depth=leading_dirs_depth,
                    use_current_dir=use_current_dir,
                    rename=rename,
                    exclude='.*__MACOSX.*',  # some junk penetrates
                ),
            ],
        ],
        annex.switch_branch('master'),
        annex.merge_branch('incoming-processed', allow_unrelated=True),
        annex.finalize(cleanup=True),
    ]
