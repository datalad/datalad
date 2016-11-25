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
lgr = getLogger("datalad.crawler.pipelines.kaggle")

#
# def superdataset_pipeline():
#     lgr.info("Creating a CRCNS collection pipeline")
#     # Should return a list representing a pipeline
#     annex = Annexificator(no_annex=True)
#     return [
#         crawl_url("http://crcns.org/data-sets",
#             matchers=[a_href_match('.*/data-sets/[^#/]+$')]),
# #                      a_href_match('.*/data-sets/[\S+/\S+'),]),
#         # TODO:  such matchers don't have state so if they get to the same url from multiple
#         # pages they pass that content twice.  Implement state to remember yielded results +
#         # .reset() for nodes with state so we could first get through the pipe elements and reset
#         # them all
#         a_href_match("(?P<url>.*/data-sets/(?P<dataset_category>[^/#]+)/(?P<dataset>[^_/#]+))$"),
#         # http://crcns.org/data-sets/vc/pvc-1
#         assign({'dataset_name': '%(dataset)s'}, interpolate=True),
#         annex.initiate_dataset(
#             template="crcns",
#             data_fields=['dataset_category', 'dataset'],
#             # branch='incoming',  # there will be archives etc
#             existing='skip',
#             # further any additional options
#         )
#     ]
#
#
# def extract_readme(data):
#     # TODO - extract data from the page/response  but not into README I guess since majority of datasets
#     # already provide README
#     if os.path.exists("README.txt"):
#         os.unlink("README.txt")
#     with open("README.txt", "w") as f:
#         f.write("CRCNS dataset from %(url)s" % data)
#     lgr.info("Generated README.txt")
#     yield {'filename': "README.txt"}
#

def pipeline(url=None,
             a_href_match_='.*/download/.*\.(tgz|tar.*|zip)',
             tarballs=True,
             datalad_downloader=False,
             use_current_dir=False,
             leading_dirs_depth=1,
             rename=None,
             backend='MD5E',
             add_archive_leading_dir=False,
             annex=None,
             incoming_pipeline=None):
    """Pipeline to crawl/annex an crcns dataset"""

    if not isinstance(leading_dirs_depth, int):
        leading_dirs_depth = int(leading_dirs_depth)

    if not tarballs:
        raise NotImplementedError("yet to simplify for no tarballs case")

    lgr.info("Creating a pipeline to crawl data files from %s", url)
    if annex is None:
        # if no annex to use was provided -- let's just make one
        special_remotes = []
        if tarballs:
            special_remotes.append(ARCHIVES_SPECIAL_REMOTE)
        if datalad_downloader:
            special_remotes.append(DATALAD_SPECIAL_REMOTE)
        annex = Annexificator(
            create=False,  # must be already initialized etc
            backend=backend,
            statusdb='json',
            special_remotes=special_remotes,
            options=["-c", "annex.largefiles=exclude=README* and exclude=LICENSE*"]
        )

    if url:
        assert not incoming_pipeline
        crawler = crawl_url(url)
        incoming_pipeline = [ # Download all the archives found on the project page
            crawler,
            a_href_match(a_href_match_, min_count=1),
        ]
        if rename:
            incoming_pipeline += [sub({'filename': get_replacement_dict(rename)})]
        incoming_pipeline += [annex]
    else:
        # no URL -- nothing to crawl -- but then should have been provided
        assert incoming_pipeline


    # TODO: we could just extract archives processing setup into a separate pipeline template
    return [
        annex.switch_branch('incoming', parent='master'),
        [
            incoming_pipeline,
        ],
        annex.switch_branch('incoming-processed'),
        [   # nested pipeline so we could skip it entirely if nothing new to be merged
            annex.merge_branch('incoming', strategy='theirs', commit=False),  #, skip_no_changes=False),
            [   # Pipeline to augment content of the incoming and commit it to master
                find_files("\.(zip|tgz|tar(\..+)?)$", fail_if_none=tarballs),  # So we fail if none found -- there must be some! ;)),
                annex.add_archive_content(
                    existing='archive-suffix',
                    # Since inconsistent and seems in many cases no leading dirs to strip, keep them as provided
                    strip_leading_dirs=bool(leading_dirs_depth),
                    delete=True,
                    leading_dirs_depth=leading_dirs_depth,
                    use_current_dir=use_current_dir,
                    rename=rename,
                    exclude='.*__MACOSX.*',  # some junk penetrates
                    add_archive_leading_dir=add_archive_leading_dir
                ),
            ],
        ],
        annex.switch_branch('master'),
        annex.merge_branch('incoming-processed', allow_unrelated=True),
        annex.finalize(cleanup=True),
    ]
