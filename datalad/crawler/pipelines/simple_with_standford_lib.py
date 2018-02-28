from ..nodes.crawl_url import crawl_url
from ..nodes.misc import fix_url
from ..nodes.crawl_url import parse_checksums
from ..nodes.matches import css_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import find_files
from ..nodes.misc import sub
from ..nodes.misc import skip_if
from ..nodes.annex import Annexificator
from ...consts import DATALAD_SPECIAL_REMOTE, ARCHIVES_SPECIAL_REMOTE
from ...support.strings import get_replacement_dict


# copied the simple_with_archives template in order to show
def pipeline_2(url=None,
             x_href_match_='.*/download/.*\.(tgz|tar.*|zip)',
             tarballs=True,
             datalad_downloader=False,
             use_current_dir=False,
             leading_dirs_depth=1,
             rename=None,
             backend='MD5E',
             add_archive_leading_dir=False,
             annex=None,
             incoming_pipeline=None):

    # adding print_xml to incoming pipeline
    incoming_pipeline = [  # Download all the archives found on the project page
        crawler,
        x_pathmatch(x_pathMatch, min_count=1), #changed h-ref to x_pathmatch
        print_xml
    ]


# print generator
def print_xml(data, keys=['xml']):
    """Given xml data, get value within 'xml' key and print it
    """
    data = data.copy()
    for key in keys:
        if key in data: # catches key error if dictionary does not contain key
            print((data[key]).as_str())
    yield data

# beginning crawl method to crawl xml info
class crawl_xml:
    def __init__(self, xml_path = file_id, id):
        xml_path = xml_path
        id = Scrapy.parse(xml_path)