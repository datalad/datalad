# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for crawling a webpage and push extracted data into a dataset"""

__docformat__ = 'restructuredtext'


from os.path import exists, isdir
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureChoice, EnsureNone
from datalad.crawler.pipeline import initiate_pipeline_config
from datalad.support.stats import ActivityStats

from logging import getLogger
lgr = getLogger('datalad.api.crawl')

from .. import cfg

class Crawl(Interface):
    """Crawl online resource to create or update a dataset.

    Examples:

      $ datalad crawl  # within a dataset having .datalad/crawl/crawl.cfg
    """
    _params_ = dict(
# Dry run is untested and largely probably not working in this implementation
# so let's not expose it for now at all
#        dry_run=Parameter(
#            args=("-n", "--dry-run"),
#            action="store_true",
#            doc="""flag if file manipulations to be invoked (e.g., adding to git/annex).
#            If not, commands are only printed to the stdout"""),
        is_pipeline=Parameter(
            args=("--is-pipeline",),
            action="store_true",
            doc="""flag if provided file is a Python script which defines pipeline()"""),
        is_template=Parameter(
            args=("-t", "--is-template"),
            action="store_true",
            doc="""flag if provided value is the name of the template to use"""),
        recursive=Parameter(
            args=("-r", "--recursive"),
            action="store_true",
            doc="""flag to crawl subdatasets as well (for now serially)"""),
        chdir=Parameter(
            args=("-C", "--chdir"),
            constraints=EnsureStr() | EnsureNone(),
            doc="""directory to chdir to for crawling"""),
        path=Parameter(
            args=('path',),
            metavar='file',
            nargs='?',
            constraints=EnsureStr() | EnsureNone(),
            doc="""configuration (or pipeline if --is-pipeline) file defining crawling, or a directory
                of a dataset on which to perform crawling using its standard crawling specification"""),
    )

    @staticmethod
    def __call__(path=None, is_pipeline=False, is_template=False, recursive=False, chdir=None): # dry_run=False,
        dry_run = False

        from datalad.crawler.pipeline import (
            load_pipeline_from_config, load_pipeline_from_module,
            get_repo_pipeline_config_path, get_repo_pipeline_script_path
        )
        from datalad.crawler.pipeline import run_pipeline
        from datalad.utils import chpwd  # import late so we could mock during tests
        from datalad.utils import getpwd

        with chpwd(chdir):

            assert not (is_pipeline and is_template), "it is either a pipeline or a template name, can't be both"
            path_orig = path
            if is_template:
                # generate a config and overload path with its filename
                path = initiate_pipeline_config(template=path,  # kwargs=TODO,
                                                commit=True)

            # TODO: centralize via _params_ handling
            if dry_run:
                if 'crawl' not in cfg.sections():
                    cfg.add_section('crawl')
                cfg.set('crawl', 'dryrun', "True")

            if path is None:

                # get config from the current repository/dataset
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
            stats = ActivityStats()
            try:
                output = run_pipeline(pipeline, stats=stats)
            except Exception as exc:
                # TODO: config.crawl.failure = full-reset | last-good-master
                # probably ask via ui which action should be performed unless
                # explicitly specified
                raise
            stats.datasets_crawled += 1

            # TODO:  Move gc/clean over here!

            stats_total = stats.get_total()

            if recursive:
                # get all subdatasets, and crawl them too!
                ## ? assert path_orig is None, "Otherwise not sure what to do with path=%r in subdatasets" % path
                import os
                from ..distribution.dataset import Dataset
                from ..api import crawl
                from ..utils import swallow_logs
                from ..dochelpers import exc_str
                subdatasets = Dataset(os.curdir).get_subdatasets(recursive=recursive)

                lgr.info("Crawling %d subdatasets", len(subdatasets))
                output = [output]
                # TODO: parallelize
                for ds_ in subdatasets:
                    try:
                        # TODO: might be cool to be able to report a 'heart beat' from the swallow into pbar or smth
                        with swallow_logs() as cml:
                            output_, stats_ = crawl(chdir=ds_, recursive=recursive)
                            stats_total += stats_
                            output += output_
                        lgr.info("Crawled %s: %s", ds_, stats_.as_str(mode='line'))
                    except Exception as exc:
                        lgr.warning("Crawling of %s has failed: %s.", #  Log output: %s",
                                    ds_, exc_str(exc)) #, cml.out)

                lgr.info("Overall stats: %s", stats.as_str(mode='line'))

            return output, stats_total
