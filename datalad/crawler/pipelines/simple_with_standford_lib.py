from ..nodes.matches import xpath_match
try:
    from scrapy.http import Response
    from scrapy.http import XmlResponse
    from scrapy.selector import Selector
except ImportError:  # pragma: no cover
    class Selector(object):
        xpath = css = None
    Response = None


# copied the simple_with_archives template in order to show
def pipeline_2(url=None,
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

    crawler = crawl_xml()
    # adding print_xml to incoming pipeline
    incoming_pipeline = [  # Download all the archives found on the project page
        crawler,
        xpath_match(xpath_match, min_count=1), #changed h-ref to xpath_match
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


# beginning crawl method to crawl xml info
class crawl_xml:
    def __init__(self, url="", file_path='//file[contains(@id)]/@id',
                 doc_path='//contentMetaData[contains(@objectId)]/@objectId'):
        response = XmlResponse(url=url)

        # parse data using selectors from scrapy
        self._file_id = response.select(file_path).extract()
        self._doc_id= response.select(doc_path).extract()
        self._url = "https://stacks.stanford.edu/file/druid:" + self._doc_id + "/" + self._file_id
