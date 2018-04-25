"""A pipeline for Stanford Repository's xml datasets"""

from ..nodes.matches import xpath_match
from ..nodes.crawl_url import crawl_url
try:
    from scrapy.http import Response
    from scrapy.http import XmlResponse
    from scrapy.selector import Selector

except ImportError:  # pragma: no cover
    class Selector(object):
        xpath = css = None
    Response = None


# copied the simple_with_archives template in order to show
def pipeline(doc_id=None,
             x_pathmatch_="//file/@id",
             leading_dirs_depth=1):
    """Pipeline to crawl xml datasets from purls
    """

    crawler = crawl_url("https://purl.stanford.edu/" + doc_id + ".xml")
    # adding print_xml to incoming pipeline
    incoming_pipeline = [  # Download all the archives found on the project page
        crawler,
        xpath_match(x_pathmatch_, min_count=1), # changed h-ref to xpath_match
        configure_url,
        print_xml
    ]

    from .simple_with_archives import pipeline as sa_pipeline
    return sa_pipeline(leading_dirs_depth=leading_dirs_depth,
                       add_annex_to_incoming_pipeline=True,
                       incoming_pipeline=incoming_pipeline)


def configure_url(data, keys=['url'], match='match'):
    """Given purl, configure to a url that leads directly to the file
    """
    data = data.copy()

    for key in keys:
        url_elements = data[key].split("/")
        doc_id = url_elements[3][:-4]
        data[key] = "https://stacks.stanford.edu/file/druid:" + doc_id + "/" + data[match]
    yield data


# print generator
def print_xml(data, keys=['url']):
    """Given xml data, get value within 'xml' key and print it
    """
    data = data.copy()
    for key in keys:
        print(key, (data[key]))
    yield data
