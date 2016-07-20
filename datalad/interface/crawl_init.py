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
from collections import OrderedDict


from ..dochelpers import exc_str
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone
from ..utils import get_func_kwargs_doc
from ..crawler.pipeline import load_pipeline_from_template, initiate_pipeline_config


from logging import getLogger
lgr = getLogger('datalad.api.crawl_init')
CRAWLER_PIPELINE_SECTION = 'crawl:pipeline'

class CrawlInit(Interface):
    """
    Allows user to specify template and function to generate a pipeline

    Examples:

    $ datalad crawl-init \
        --template openfmri \
        --func superdataset_pipeline

    $ datalad crawl-init \
        --template fcptable \
        dataset=Baltimore tarballs=True
    """
    _params_ = dict(
        template=Parameter(
            args=("-t", "--template"),
            action="store",
            constraints=EnsureStr() | EnsureNone(),
            doc="""flag if template is specified by user"""),
        template_func=Parameter(
            args=("-f", "--template-func"),
            action="store",
            doc="""flag if function is specified by user"""),
        args=Parameter(
            args=("args",),
            nargs="*",
            constraints=EnsureStr() | EnsureNone(),
            doc="""keyword arguments to pass into the template function generating actual pipeline,
            organized in an ordered dict"""),
        commit=Parameter(
            args=("--commit",),
            action="store_true",
            doc="""flag is user wants to commit file into git repo"""),
    )

    @staticmethod
    def __call__(args=None, template=None, template_func=None, commit=False):

        if args:
            if isinstance(args, str):
                args = args.split(" ")
            if isinstance(args, list):
                args = OrderedDict(map(str, it.split('=', 1)) for it in args)
            elif isinstance(args, dict):
                pass
            else:
                raise ValueError(
                    "args entered must be given in a list or dict, were given as %s",
                    type(args))
        else:
            args = {}

        pipeline_func = load_pipeline_from_template(template, template_func, kwargs=args, return_only=True)

        try:
            pipeline = pipeline_func(**args)
        except Exception as exc:
            raise RuntimeError(
                "Running the pipeline function resulted in %s."
                "FYI this pipeline only takes the following args: %s"
                % (exc_str(exc), get_func_kwargs_doc(pipeline_func)))

        if not pipeline:
            raise ValueError("returned pipeline is empty")

        if not isinstance(pipeline, list):
            raise ValueError("pipeline should be represented as a list. Got: %r" % pipeline)

        initiate_pipeline_config(template, template_func, args)
