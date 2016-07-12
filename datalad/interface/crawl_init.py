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


from .base import Interface
from os.path import exists, isdir, curdir
from os.path import join as opj
from datalad import cfg
from datalad.config import ConfigManager
from datalad.consts import CRAWLER_META_CONFIG_PATH, CRAWLER_META_DIR
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureChoice, EnsureNone
from datalad.crawler.pipeline import initiate_pipeline_config

from logging import getLogger
lgr = getLogger('datalad.api.crawl_init')


class CrawlInit(Interface):
    """
    Allows user to specify template and function to generate a pipelinne

    Example:

    $ datalad crawl-init \
        --template openfmri \
        --func superdataset_pipeline

    $ datalad crawl-init \
        --template fcptable \
        args=[{'dataset': 'Baltimore'}]
    """
    _params_ = dict(
        template=Parameter(
            args=("-t", "--template"),
            action="store",
            constraints=EnsureStr() | EnsureNone(),
            doc="""flag if template is specified by user"""),
        func=Parameter(
            args=("-f", "--func"),
            action="store",
            doc="""flag if function is specified by user"""),
        args=Parameter(
            args=("args",),
            nargs="*",
            metavar="key=value",
            # TODO constraints=EnsureKeyValuePairs() | EnsureNone(),
            doc="""keyword arguments to pass into the template function generating actual pipeline"""),
    )

    @staticmethod
    def __call__(template=None, func=None, args=[]):
        cfg_ = ConfigManager([])
        cfg_.remove_section('general')
        cfg_.add_section('crawl:pipeline')


        if template and func:
            cfg_.set('crawl:pipeline', 'template', template)
            cfg_.set('crawl:pipeline', 'func', func)

            lgr.info("Generated crawl.cfg with provided template and func")


        if template and not func:
            if not args:


        cfg_.write(open(curdir + '/.datalad/crawl/crawl.cfg'))

