# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Pipeline functionality.

Pipeline is depicted by a simple list or tuple of nodes or other nested pipelines.
Each pipeline node is a callable which receives a dictionary (commonly named `data`),
does some processing and yields (once or multiple times) derived dictionary (commonly
a shallow copy of original dict).  For a node to be parametrized it should be
implemented as a callable (i.e. define __call__) class, which could obtain parameters
in its constructor.
"""

from os.path import dirname, join as opj, isabs, exists, curdir

from .newmain import lgr
from ..support.gitrepo import GitRepo
from ..support.configparserinc import SafeConfigParserWithIncludes

# Name of the section in the config file which would define pipeline parameters
crawler_pipeline_section = 'crawler_pipeline'

from logging import getLogger
lgr = getLogger('datalad.crawl.pipeline')


class FinishPipeline(Exception):
    """Exception to use to signal that any given pipeline should be stopped
    """
    pass

# TODO: should may be pipeline return data as well?
#       or may be it should return some stats or smth else than the data
#       use-case: not sure yet. cons: we would need explicit "terminators" for the pipelins
def run_pipeline(pipeline, data=None):
    """Run a pipeline

    Pipeline is just a list of actions or other pipelines (lists, tuples)
    """
    # just for paranoids and PEP8-disturbed, since theoretically every node
    # should not change the data, so having default {} should be sufficient
    data = data or {}
    try:
        run_pipeline_steps(pipeline, data)
    except FinishPipeline as e:
        lgr.debug("Got a signal that pipeline %s is 'finished'" % pipeline)

def run_pipeline_steps(pipeline, data):
    """Actually run pipeline steps, feeding yielded results to the next node

    Recursive beast which runs a single node and then recurses to run the rest,
    possibly multiple times if current node is a generator
    """

    if not len(pipeline):
        return data
    node, pipeline_tail = pipeline[0], pipeline[1:]
    if isinstance(node, (list, tuple)):
        # we have got a step which is yet another entire pipeline
        run_pipeline(node, data)
        # there is no yielding or results from a pipeline
        # and we just then go to the next
        run_pipeline_steps(pipeline_tail, data)
    else:  # it is a "node" which should generate us stuff to feed into the rest of the pipeline
        # TODO: may be allow non generators
        lgr.debug("Node: %s" % node)
        for data_ in node(data):
            # TODO: for heavy debugging we might want to track/report what node has changed in data
            lgr.log(7, " pass %d keys into tail with %d elements" % (len(data_), len(pipeline_tail)))
            run_pipeline_steps(pipeline_tail, data_)


def load_pipeline_from_template(name, opts={}):
    """Given a name, loads that pipeline from datalad.crawler.pipelines

    and later from other locations

    Parameters
    ----------
    name: str
        Name of the pipeline defining the filename. Or full path to it (TODO)
    opts: dict, optional
        Options for the pipeline, passed as **kwargs into the pipeline call
    """

    if (isabs(name) or exists(name)):
        raise NotImplementedError("Don't know how to import straight path %s yet" % name)

    # explicit isabs since might not exist
    filename = name if (isabs(name) or exists(name)) else opj(dirname(__file__), 'pipelines', "%s.py" % name)

    if not exists(filename):
        raise IOError("Pipeline file %s was not found" % filename)

    mod = __import__('datalad.crawler.pipelines.%s' % name, fromlist=['datalad.crawler.pipelines'])
    return mod.pipeline(**opts)


def load_pipeline_from_config(path):
    """Given a path to the pipeline configuration file, instantiate a pipeline
    """

    cfg = SafeConfigParserWithIncludes()
    cfg.read([path])
    if cfg.has_section(crawler_pipeline_section):
        opts = cfg.options(crawler_pipeline_section)
        # must have template
        if 'template' not in opts:
            raise IOError("%s lacks %r field within %s section"
                          % (path, 'template', crawler_pipeline_section))
        opts.pop(opts.index('template'))
        template = cfg.get(crawler_pipeline_section, 'template')
        pipeline = load_pipeline_from_template(
            template,
            {o: cfg.get(crawler_pipeline_section, o) for o in opts})
    else:
        raise IOError("Did not fine %s section within %s" % (crawler_pipeline_section, path))
    return pipeline

def get_pipeline_config_path(repo_path=curdir):
    """Given a path within a repo, return path to the crawl.cfg"""
    if not exists(opj(repo_path, '.datalad')):
        # we need to figure out top path for the repo
        repo_path = GitRepo.get_toppath(repo_path)
        if not repo_path:
            return None
    return opj(repo_path, '.datalad', 'crawl', 'crawl.cfg')