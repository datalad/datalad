# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for a generic template in which arguments are specified by the user"""

__docformat__ = 'restructuredtext'


from datalad import cfg
from datalad.config import ConfigManager
from datalad.consts import CRAWLER_META_CONFIG_PATH, CRAWLER_META_DIR


class CrawlInit(Interface):
    """
    Create a template based off of cmdline arguments specified by user

    Examples:

    $ datalad crawl --init \
        url=http://example.com \
        a_href_match=.*\.(tar.*|dat)) \
          # within a dataset having no .datalad/crawl/crawl.cfg
    """
_params_ = dict(











init = Parameter(
args=("--init",),
action="store_true",
doc="""flag if user can provide arguments needed for template to initate .datalad/crawl/crawl.cfg"""),

    if init:
        url = input("URL: ")
        a_href_match = input("a_href_match: ")
        extract_tarballs = input("extract_tarballs: ")