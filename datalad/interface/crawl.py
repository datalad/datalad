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


from os.path import exists, isdir
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureChoice, EnsureNone
from datalad.crawler.pipeline import initiate_pipeline_config

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
        is_pipeline=Parameter(
            args=("--is-pipeline",),
            action="store_true",
            doc="""Flag if provided file is a Python script which defines pipeline()"""),
        is_template=Parameter(
            args=("-t", "--is-template"),
            action="store_true",
            doc="""Flag if provided value is the name of the template to use"""),
        chdir=Parameter(
            args=("-C", "--chdir"),
            constraints=EnsureStr() | EnsureNone(),
            doc="""Directory to chdir to for crawling"""),
        path=Parameter(
            args=('path',),
            metavar='file',
            nargs='?',
            constraints=EnsureStr() | EnsureNone(),
            doc="""Configuration (or pipeline if --is-pipeline) file defining crawling, or a directory
                of a handle on which to perform crawling using its standard crawling specification"""),
    )

    @staticmethod
    def __call__(path=None, dry_run=False, is_pipeline=False, is_template=False, chdir=None):
        from datalad.crawler.pipeline import (
            load_pipeline_from_config, load_pipeline_from_module,
            get_repo_pipeline_config_path, get_repo_pipeline_script_path
        )
        from datalad.crawler.pipeline import run_pipeline
        from datalad.utils import chpwd  # import late so we could mock during tests
        with chpwd(chdir):

            assert not (is_pipeline and is_template), "it is either a pipeline or a template name, can't be both"

            if is_template:
                # generate a config and overload path with its filename
                path = initiate_pipeline_config(template=path,  # kwargs=TODO,
                                                commit=True)

            # TODO: centralize via _params_ handling
            if dry_run:
                if not 'crawl' in cfg.sections():
                    cfg.add_section('crawl')
                cfg.set('crawl', 'dryrun', "True")

            if path is None:

                # get config from the current repository/handle
                if is_pipeline:
                    raise ValueError("You must specify the file if --pipeline")
                # Let's see if there is a config or pipeline in this repo
                path = get_repo_pipeline_config_path()
                if not path or not exists(path):
                    # Check if there may be the pipeline provided
                    path = get_repo_pipeline_script_path()
                    if path and exists(path):
                        is_pipeline = True

            if not path:
                raise RuntimeError("Cannot locate crawler config or pipeline file")

            if is_pipeline:
                lgr.info("Loading pipeline definition from %s" % path)
                pipeline = load_pipeline_from_module(path)
            else:
                lgr.info("Loading pipeline specification from %s" % path)
                pipeline = load_pipeline_from_config(path)

            lgr.info("Running pipeline %s" % str(pipeline))
            # TODO: capture the state of all branches so in case of crash
            # we could gracefully reset back
            try:
                run_pipeline(pipeline)
            except Exception as exc:
                # TODO: config.crawl.failure = full-reset | last-good-master
                # probably ask via ui which action should be performed unless
                # explicitly specified
                raise

            # TODO:  Move gc/clean over here!
