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


from os.path import exists
from .base import Interface

from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.crawler.pipeline import initiate_pipeline_config
from datalad.support.stats import ActivityStats
from datalad import utils

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
    def __call__(path=None, is_pipeline=False, is_template=False,
                 recursive=False, chdir=None):  # dry_run=False,
        dry_run = False

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
                dryrun_optlabel = 'datalad.crawl.dryrun'
                if dryrun_optlabel in cfg:
                    cfg.unset(dryrun_optlabel, where='local', reload=False)
                cfg.add(dryrun_optlabel, "True", where='local')

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

            stats = ActivityStats()

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
                # Note: we could collect all datasets to be crawled here or pass recursive=True
                # into the subdatasets' crawl.  We will collect all of them here so we might later
                # also introduce automatic commits when super-dataset got successfully updated
                subdatasets = Dataset(os.curdir).subdatasets(recursive=recursive, result_xfm='relpaths')

                lgr.info("Crawling %d subdatasets", len(subdatasets))
                output = [output]
                # TODO: parallelize
                # TODO: assumes that all sub-datasets are 'crawllable', and if not
                # just adds them to crawl_failed count.  But may be we should make it more
                # explicit, that some sub-datasets might not need to be crawled, so they get
                # skipped explicitly?
                for ds_ in subdatasets:
                    ds_logfile = utils.get_logfilename(ds_, 'crawl')
                    try:
                        # TODO: might be cool to be able to report a 'heart beat' from the swallow into pbar or smth
                        with swallow_logs(file_=ds_logfile) as cml:
                            output_, stats_ = crawl(chdir=ds_)
                            stats_total += stats_
                            output.append(output_)
                        lgr.info("Crawled %s: %s (log: %s)", ds_, stats_.as_str(mode='line'), ds_logfile)
                    except Exception as exc:
                        stats_total.datasets_crawl_failed += 1
                        stats_total.datasets_crawled += 1
                        output += [None]
                        lgr.warning("Crawling of %s has failed (more in %s): %s.",  # Log output: %s",
                                    ds_, ds_logfile, exc_str(exc))  # , cml.out)

            lgr.info("Total stats: %s", stats_total.as_str(mode='line'))

            return output, stats_total
