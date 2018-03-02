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
             x_pathmatch_='.*/download/.*\.(tgz|tar.*|xml)',
             tarballs=True,
             datalad_downloader=False,
             use_current_dir=False,
             leading_dirs_depth=1,
             rename=None,
             backend='MD5E',
             add_archive_leading_dir=False,
             annex=None,
             incoming_pipeline=None):

    crawler = crawl_url("https://purl.stanford.edu/" + doc_id)
    # adding print_xml to incoming pipeline
    incoming_pipeline = [  # Download all the archives found on the project page
        crawler,
        xpath_match('//file[contains(@id)]/@id', min_count=1), #changed h-ref to xpath_match
        print_xml
    ]


# print generator
def print_xml(data, keys=['url']):
    """Given xml data, get value within 'xml' key and print it
    """
    data = data.copy()
    for key in keys:
        if key in data: # catches key error if dictionary does not contain key
            print((data[key]).as_str())
    yield data
