"""A pipeline for crawling FCP Classic Data Table"""

import os, re
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import xpath_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import sub
from ..nodes.misc import func_to_node
from ..nodes.misc import find_files
from ..nodes.annex import Annexificator
from ...consts import ARCHIVES_SPECIAL_REMOTE

from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.fcptable")

TOPURL = "http://fcon_1000.projects.nitrc.org/fcpClassic/FcpTable.html"


def superdataset_pipeline(url=TOPURL):
    annex = Annexificator(allow_dirty=True)
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

    for title, detail in zip(xpath_match('//*/tr [@class="tableHdr"]/td/strong/text()')(data),
                             xpath_match('//*[@class="tableHdr"]/td|strong/text()')(data)):
        if title['match'] == data['title']:
            print detail['match']
            pi = (re.search(('<br>.*<br>'), detail['match'])).group()
            cleaner = re.compile('<.*?>')
            data['PI'] = re.sub(cleaner, '', pi)
            data['details'] = (re.search(('n =.*[0-9]'), detail['match'])).group()

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

        for title, tar in zip(xpath_match('//*/tr [@class="tableHdr"]/td/strong/text()')(data),
                              xpath_match('//*/tr [@class="tableDownload"]/td/a/text()')(data)):

            if title['match'] == self.dataset:
                data['title'] = title['match']
                data['tar'] = tar['match']
                yield data


def pipeline(dataset):
    lgr.info("Creating a pipeline for the FCP Table dataset %s" % dataset)
    annex = Annexificator(create=False, statusdb='json', allow_dirty=True, special_remotes=[ARCHIVES_SPECIAL_REMOTE],
                          options=["-c",
                                   "annex.largefiles="
                                   "exclude=Makefile and exclude=LICENSE* and exclude=ISSUES*"
                                   " and exclude=CHANGES* and exclude=README*"
                                   " and exclude=*.[mc] and exclude=dataset*.json"
                                   " and (exclude=*.txt or include=*/*.txt)"
                                   " and (exclude=*.json or include=*/*.json)"
                                   " and (exclude=*.tsv or include=*/*.tsv)"
                                   ])

    return [
        crawl_url(TOPURL),
        assign({'dataset': dataset}),
        sub({'response': {'<div class="tableParam">([^<]*)</div>': r'\1'}}),
        find_dataset(dataset),
        [
            extract_readme,
            annex,
        ]
    ]


