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
             incoming_pipeline=None):

    assert not incoming_pipeline
    crawler = crawl_url("https://purl.stanford.edu/" + doc_id + ".xml")
    # adding print_xml to incoming pipeline
    incoming_pipeline = [  # Download all the archives found on the project page
        crawler,
        xpath_match(x_pathmatch_, min_count=1), # changed h-ref to xpath_match
        configure_url,
        print_xml
    ]
    return incoming_pipeline


def configure_url(data, keys=['url'], match='match'):
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
