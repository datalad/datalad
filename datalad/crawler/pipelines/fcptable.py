"""A pipeline for crawling FCP Classic Data Table"""

import os
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import xpath_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import sub
from ..nodes.misc import func_to_node
from ..nodes.misc import find_files
from ..nodes.annex import Annexificator
from ...support.s3 import get_versioned_url
from ...consts import ARCHIVES_SPECIAL_REMOTE

from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.fcptable")

TOPURL = "http://fcon_1000.projects.nitrc.org/fcpClassic/FcpTable.html"


def superdataset_pipeline(url=TOPURL):
    annex = Annexificator()
    lgr.info("Creating a FCP collection pipeline")
    return [
        crawl_url(url),
        #a_href_match("http://www.nitrc.org/frs/downloadlink.php/.*"),
        xpath_match('//*[@class="tableHdr"]/td/strong/text()', output='dataset'),
        # TODO: replace spaces
        assign({'dataset_name': '%(dataset)s'}, interpolate=True),
        annex.initiate_dataset(
            template="fcptable",
            data_fields=['dataset'],
            existing='skip'
        )
    ]


class find_dataset(object):

    def __init__(self, dataset):
    """Pipeline to crawl/annex an openfmri dataset

       Parameters
       ----------
       dataset: str
         Id of the FCP Table dataset (e.g. Baltimore)
       response: html web page
         Given by the top URL
       """

    def __call__(self, data):

        # might want tableCox row as well for pre-processed data
        for titles, tars in zip(response.xpath('//*/tr [@class="tableHdr"]'),
                                response.xpath('//*/tr [@class="tableDownload"]')):
            for title, tar in zip(titles.xpath('td'), tars.xpath('td')):
                if dataset == title.xpath('strong/text()').extract():
                    data['pi'] = title.xpath...
                    data['#subj'] = title.xpath...
                    data['response'] = tar
                    yield data
                    return
                    #return tar.xpath('a').extract()

def pipeline(dataset):
    [
        crawl_url(TOPURL),
        find_dataset(dataset),
        [
            extract_README,    #annexed
            annex
        ],
        a_href_match('.*'),
    ]

    #get disposition filename