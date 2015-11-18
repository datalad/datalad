# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for crawling a webpage and push extracted data into a handle"""

__docformat__ = 'restructuredtext'


from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureChoice, EnsureNone

from logging import getLogger
lgr = getLogger('datalad.api.crawl')

from .. import cfg

class Crawl(Interface):
    """Crawl online resource to create or update a handle.

    Examples:

      $ datalad crawl  # within a handle having .datalad/crawl/crawl.cfg
    """
    _params_ = dict(
        dry_run=Parameter(
            args=("-n", "--dry-run"),
            action="store_true",
            doc="""Flag if file manipulations to be invoked (e.g., adding to git/annex).
            If not, commands are only printed to the stdout"""),
        config=Parameter(
            metavar='file',
            constraints=EnsureStr() | EnsureNone(),
            doc="""Configuration file(s) defining the structure of the
            'project'"""),
    )

    def __call__(self, config=None, dry_run=False):
        from datalad.crawler.pipeline import load_pipeline_from_config, get_pipeline_config_path
        from datalad.crawler.pipeline import run_pipeline
        from datalad.cmdline.helpers import get_repo_instance

        # TODO: centralize via _params_ handling
        if dry_run:
            if not 'crawl' in cfg.sections():
                cfg.add_section('crawl')
            cfg.set('crawl', 'dryrun', "True")

        if config is None:
            # get config from the current repository/handle
            config = get_pipeline_config_path()

        if not config:
            raise RuntimeError("Cannot locate crawler config file")

        lgr.info("Loading pipeline definition from %s" % config)
        pipeline = load_pipeline_from_config(config)

        lgr.info("Running pipeline %s" % pipeline)
        run_pipeline(pipeline)
