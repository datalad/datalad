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

from os.path import curdir
from .base import Interface
from collections import OrderedDict
from datalad.distribution.dataset import Dataset

from ..dochelpers import exc_str
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone
from ..utils import get_func_kwargs_doc
from ..crawler.pipeline import load_pipeline_from_template, initiate_pipeline_config

from logging import getLogger
lgr = getLogger('datalad.api.crawl_init')
CRAWLER_PIPELINE_SECTION = 'crawl:pipeline'


class CrawlInit(Interface):
    """Initialize crawling configuration

    Allows to specify template and function to generate a crawling pipeline

    Examples:

    $ datalad crawl-init \
        --template openfmri \
        --template-func superdataset_pipeline

    $ datalad crawl-init \
        --template fcptable \
        dataset=Baltimore tarballs=True
    """

    _params_ = dict(
        template=Parameter(
            args=("-t", "--template"),
            action="store",
            constraints=EnsureStr() | EnsureNone(),
            doc="""the name of the template"""),
        template_func=Parameter(
            args=("-f", "--template-func"),
            action="store",
            doc="""the name of the function"""),
        args=Parameter(
            args=("args",),
            nargs="*",
            constraints=EnsureStr() | EnsureNone(),
            doc="""keyword arguments to pass into the template function generating actual pipeline,
            organized in [PY: a dict PY][CMD: key=value pairs CMD]"""),
        save=Parameter(
            args=("--save",),
            action="store_true",
            doc="""flag to save file into git repo"""),
    )

    @staticmethod
    def __call__(args=None, template=None, template_func=None, save=False):

        if args:
            if isinstance(args, str):
                args = [args]
            if isinstance(args, list):
                args = OrderedDict(map(str, it.split('=', 1)) for it in args)
            elif isinstance(args, dict):
                pass
            else:
                raise ValueError(
                    "args entered must be given in a list or dict, were given as %s",
                    type(args))
        elif not template:
            raise TypeError("crawl-init needs a template")
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

        configfile = initiate_pipeline_config(template, template_func, args)

        if save:
            from datalad.api import save
            ds = Dataset(curdir)
            ds.repo.add(configfile, git=True)
            ds.save("committing crawl config file", files=[configfile])
