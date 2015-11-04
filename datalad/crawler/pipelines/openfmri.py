# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling openfmri dataset"""

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import css_match, a_href_match
from ..nodes.misc import assign
from ..nodes.annex import Annexificator
from ...utils import updated

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri")

def extract_readme(data):
    # TODO - extract data from the page/response
    with open("README.txt", "w") as f:
        f.write("OpenfMRI dataset from %(url)s" % data)
    lgr.info("Generated README.txt")
    yield {'filename': "README.txt"}

def pipeline(dataset):
    """Pipeline to crawl/annex an openfmri dataset"""

    dataset_url = 'https://openfmri.org/dataset/%s' % dataset
    lgr.info("Creating a pipeline for the openfmri dataset %s" % dataset)
    annex = Annexificator(create=False,  # must be already initialized etc
                          options=["-c", "annex.largefiles=exclude=*.txt"])

    return [
        annex.switch_branch('incoming'),
        crawl_url(dataset_url),
        [  # changelog
           a_href_match(".*release_history.txt"), # , limit=1
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
            css_match('.field-name-field-aws-link a',
                      xpaths={'url': '@href',
                              'url_text': 'text()'}),

            # TODO: we need to "version" those urls which we can version, e.g.,
            # if coming from versioned S3 buckets
            # version_url,
            # TODO TEMP -- too heavy, use some bogie for now
            assign({'url': 'http://www.onerussian.com/tmp/ds005_raw_boogie.tgz'}),

            annex,
        ],
        [  # and license information
           css_match('.field-name-field-license a',
                     xpaths={'url': '@href',
                             'url_text': 'text()'}),
           # TODO: HTML dump of that page for the license wouldn't be as useful I guess,
           # so let's provide our collection of most common referenced artifacts
           # in few formats
           assign({'filename': 'license.txt'}),
           annex,
        ],
        # TODO: describe_handle
        annex.switch_branch('master'),
        annex.merge_branch('incoming', strategy='theirs', commit=False),
        # [ # Pipeline to augment content of the incoming TODO
        #     ExtractArchives(
        #         # will do the merge of 'replace' strategy
        #         source_branch="incoming",
        #         regex="\.(tgz|tar\..*)$",
        #         renames=[
        #             ("^[^/]*/(.*)", "\1") # e.g. to strip leading dir, or could prepend etc
        #         ],
        #         #exclude="license.*",  # regexp
        #     ),
        #     annex,
        # ],
        annex.finalize,
    ]
