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
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import css_match, a_href_match
from ..nodes.matches import a_text_match
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
lgr = getLogger("datalad.crawler.pipelines.crcns")

def extract_readme(data):
    # TODO - extract data from the page/response
    import pdb; pdb.set_trace()
    with open("README.txt", "w") as f:
        f.write("CRCNS dataset from %(url)s" % data)
    lgr.info("Generated README.txt")
    yield {'filename': "README.txt"}

def pipeline(dataset, dataset_category, versioned_urls=False):
    """Pipeline to crawl/annex an crcns dataset"""

    dataset_url = 'http://crcns.org/data-sets/{dataset_category}/{dataset}'.format(**locals())
    lgr.info("Creating a pipeline for the crcns dataset %s" % dataset)
    annex = Annexificator(
        create=False,  # must be already initialized etc
        backend="MD5SUME",
        options=["-c", "annex.largefiles=exclude=*.txt and exclude=README"])

    crawler = crawl_url(dataset_url)
    return [
        annex.switch_branch('incoming'),
        [   # nested pipeline so we could quit it earlier happen we decided that nothing todo in it
            # but then we would still return to 'master' branch
            crawler,
            [   # README
                # Somewhat sucks here since 'url' from above would be passed all the way to annex
                # So such nodes as extract_readme should cleans the data so only relevant pieces are left
                a_href_match(".*/about.*"),
                crawler.recurse,
                extract_readme,
                annex,
            ],
            [   # Download from NERSC
                # don't even bother finding the link (some times only in about, some times also on the main page
                # just use https://portal.nersc.gov/project/crcns/download/<dataset_id>
                crawl_url("https://portal.nersc.gov/project/crcns/download/{dataset}".format(**locals())),
                # they all contain filelist and checksums.md5 which we can make use of without explicit crawling
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
                # Since all content of crcns is anyways available openly, no need atm
                # to use https which complicates proxying etc. Thus replace for AWS urls
                # to crcns S3 from https to http
                # TODO: might want to become an option for get_versioned_url? 
                sub({
                 'url': {
                   '(http)s?(://.*crcns\.s3\.amazonaws.com/|://s3\.amazonaws\.com/crcns/)': r'\1\2'
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
        ],
        annex.switch_branch('master'),
        [   # nested pipeline so we could skip it entirely if nothing new to be merged
            annex.merge_branch('incoming', strategy='theirs', commit=False),
            [   # Pipeline to augment content of the incoming and commit it to master
                find_files("\.(tgz|tar(\..+)?)$", fail_if_none=True),  # So we fail if none found -- there must be some! ;)),
                annex.add_archive_content(
                    #rename=[
                    #    r"|^[^/]*/(.*)|\1"  # e.g. to strip leading dir, or could prepend etc
                    #],
					existing='archive-suffix',
					strip_leading_dirs=True,
                    # overwrite=True,
                    # TODO: we might need a safeguard for cases if multiple subdirectories within a single tarball
                    #rename=
                ),
                # annex, # not needed since above add_archive_content adds to annex
            ],
        ],
        annex.finalize,
    ]
