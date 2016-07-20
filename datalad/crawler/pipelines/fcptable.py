"""A pipeline for crawling FCP Classic Data Table"""

import os, re
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import xpath_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import sub
from ..nodes.misc import get_disposition_filename
from ..nodes.misc import find_files
from ..nodes.annex import Annexificator
from ...consts import ARCHIVES_SPECIAL_REMOTE

from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.fcptable")

TOPURL = "http://fcon_1000.projects.nitrc.org/fcpClassic/FcpTable.html"


def superdataset_pipeline(url=TOPURL):
    annex = Annexificator()
    lgr.info("Creating a FCP collection pipeline")
    return [
        crawl_url(url),
        xpath_match('//*[@class="tableHdr"]/td/strong/text()', output='dataset'),
        # TODO: replace spaces
        assign({'dataset_name': '%(dataset)s'}, interpolate=True),
        annex.initiate_dataset(
            template="fcptable",
            data_fields=['dataset'],
            existing='skip'
        )
    ]


def extract_readme(data):

    if lexists("README.txt"):
        os.unlink("README.txt")

    with open("README.txt", "w") as fi:
        fi.write("""\
FCP1000 sub-dataset %(dataset)s
------------------------

Author(s): %(PI)s
Details: %(details)s
        """ % data)

        lgr.info("Generated README.txt")
        yield {'filename': "README.txt"}


class find_dataset(object):

    def __init__(self, dataset):
        """
        Pipeline to crawl/annex a FCP Table dataset

        Parameters
        ----------
        dataset: str
            Id of the FCP Table dataset (e.g. Baltimore)
        """
        self.dataset = dataset

    def __call__(self, data):

        titles = [x['match'] for x in xpath_match('//*/tr [@class="tableHdr"]/td/strong/text()')(data)]
        tar_tds = [x['match'] for x in xpath_match('//*/tr [@class="tableDownload"]/td')(data)]
        details = [x['match'] for x in xpath_match('//*[@class="tableHdr"]/td|strong/text()')(data)]

        if len(titles) != len(tar_tds):
            assert tar_tds[-1] == '<td></td>'
            assert len(tar_tds) == len(titles) + 1

        for title, tar, detail in zip(titles, tar_tds, details):
            if title == self.dataset:
                data['title'] = title
                data['response'] = tar
                pi = (re.search(('<br>.*<br>'), detail)).group()
                cleaner = re.compile('<.*?>')
                data['PI'] = re.sub(cleaner, '', pi)
                data['details'] = (re.search(('n =.*[0-9]'), detail)).group()
                yield data
                return
        raise RuntimeError("Failed to find a cell for the dataset %s" % self.dataset)


def pipeline(dataset):
    lgr.info("Creating a pipeline for the FCP Table dataset %s" % dataset)
    annex = Annexificator(create=False, statusdb='json', special_remotes=[ARCHIVES_SPECIAL_REMOTE],
                          options=["-c",
                                   "annex.largefiles="
                                   "exclude=Makefile and exclude=LICENSE* and exclude=ISSUES*"
                                   " and exclude=CHANGES* and exclude=README*"
                                   " and exclude=*.[mc] and exclude=dataset*.json"
                                   " and exclude=*.txt"
                                   " and exclude=*.json"
                                   " and exclude=*.tsv"
                                   ])
    # FCP Table has no versioning, so no changelog either
    return [
        annex.switch_branch('incoming'),
        [
            crawl_url(TOPURL),
            [
                assign({'dataset': dataset}),
                # first row was formatted differently so we need to condition it a bit
                sub({'response': {'<div class="tableParam">([^<]*)</div>': r'\1'}}),
                find_dataset(dataset),
                [  # README
                    extract_readme,
                    annex,
                ],

                # and collect all URLs pointing to tarballs
                a_href_match('http://www.nitrc.org/frs/downloadlink.php/[0-9999]', min_count=1),
                #  get_disposition_filename,
                annex,
            ],
        ],
        annex.remove_obsolete(),
        [
            annex.switch_branch('incoming-processed'),
            annex.merge_branch('incoming', one_commit_at_a_time=True, strategy='theirs', commit=False),
            [
               {'loop': True},
               find_files("\.(zip|tgz|tar(\..+)?)$", fail_if_none=True),
               annex.add_archive_content(
                   existing='archive-suffix',
                   strip_leading_dirs=True,
                   leading_dirs_depth=1,
                   delete=True,
                   exclude=['(^|%s)\._' % os.path.sep],
               ),
            ],
            annex.switch_branch('master'),
            annex.merge_branch('incoming-processed', commit=True),
            annex.finalize(tag=True),
        ],
        annex.switch_branch('master'),
        annex.finalize(cleanup=True),
    ]
