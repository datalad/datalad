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



from os.path import exists, isdir
from .base import Interface
from datalad import cfg
from datalad.config import ConfigManager
from datalad.consts import CRAWLER_META_CONFIG_PATH, CRAWLER_META_DIR
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureChoice, EnsureNone
from datalad.crawler.pipeline import initiate_pipeline_config

from logging import getLogger
lgr = getLogger('datalad.api.crawl')

from .. import cfg


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
        init=Parameter(
            args=("--init",),
            action="store_true",
            doc="""flag if user can provide arguments needed for template to initate .datalad/crawl/crawl.cfg"""),
    )

    @staticmethod
    def __call__(path=None, dry_run=False, is_pipeline=False, is_template=False, chdir=None, init=False):

        if init:
            url = input("URL: ")
            a_href_match = input("a_href_match: ")
            extract_tarballs = input("extract_tarballs: ")