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
from ..utils import updated
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

# Options which could augment behavior of the pipeline, could be specified
# only on top of it
PIPELINE_OPTS = dict(
    # nested_pipeline_inherits_opts=True,
    # would use or not values yielded by the nested pipeline
    output='input',    # last-output, outputs, input+outputs
    loop=False,        # either to feed results into itself (until None returned)
)

def run_pipeline(pipeline, data=None):
    """Run a pipeline

    Pipeline is just a list of actions or other pipelines (lists, tuples).
    Unlike nodes it is not yielding the result data but either returns
    a list of the results (with a single element if output=='last-output',
    empty list if =='none' or all results if =='all')
    """
    # just for paranoids and PEP8-disturbed, since theoretically every node
    # should not change the data, so having default {} should be sufficient
    data = data or {}
    opts = PIPELINE_OPTS.copy()
    if not len(pipeline):
        return

    # options for this pipeline
    if isinstance(pipeline[0], dict):
        newopts, pipeline = (pipeline[0], pipeline[1:])
        opts = updated(opts, newopts)

    # verify that we know about all specified options
    unknown_opts = set(opts).difference(set(PIPELINE_OPTS))
    if unknown_opts:
        raise ValueError("Unknown pipeline options %s" % str(unknown_opts))

    data_to_process = [data]
    output = opts['output']
    if output not in ('input',  'last-output', 'outputs', 'input+outputs'):
        raise ValueError("Unknown output=%r" % output)

    results = [] if 'input' not in output else ([data] if data else [])
    data_out = None
    while data_to_process:
        data_in = data_to_process.pop(0)
        try:
            for data_out in run_pipeline_steps(pipeline, data_in, output=output):
                if opts['loop']:
                    data_to_process.append(data_out)
                if 'outputs' in output:
                    results.append(data_out)
        except FinishPipeline as e:
            # TODO: decide what we would like to do -- skip that particular pipeline run
            # or all subsequent or may be go back and only skip that generated result
            lgr.debug("Got a signal that pipeline %s is 'finished'" % pipeline)

    # TODO: this implementation is somewhat bad since all the output logic is
    # duplicated within run_pipeline_steps, but it is probably unavoidable because of
    # loop option
    if output == 'last-output':
        return [data_out] if data_out else None
    elif output == 'input':
        return [data] if data else None
    else:
        return results


def run_pipeline_steps(pipeline, data, output='none'):
    """Actually run pipeline steps, feeding yielded results to the next node

    Recursive beast which runs a single node and then recurses to run the rest,
    possibly multiple times if current node is a generator.
    It yields output from the node/nested pipelines, as directed by output
    argument.
    """
    if not len(pipeline):
        return

    node, pipeline_tail = pipeline[0], pipeline[1:]

    data_in_to_loop = None
    if isinstance(node, (list, tuple)):
        # we have got a step which is yet another entire pipeline
        pipeline_results = run_pipeline(node, data)
        # TODO: I think here I am creating a potential side-effect/confusing behavior
        # that decision to pass original data or data from pipeline would depend not
        # on the pipeline opts but on what it returns, which is not good...
        if pipeline_results:
            # should be similar to as running a node
            data_in_to_loop = pipeline_results
        else:
            # there is no yielding or results from a pipeline
            # and we just then go to the tail with
            #data_in_to_loop = [data]
            data_in_to_loop = []
    else:  # it is a "node" which should generate (or return) us an iterable to feed
           # its elements into the rest of the pipeline
        lgr.debug("Node: %s" % node)
        data_in_to_loop = node(data)

    data_out = None
    for data_ in data_in_to_loop:
        if pipeline_tail:
            # TODO: for heavy debugging we might want to track/report what node has changed in data
            lgr.log(7, " pass %d keys into tail with %d elements" % (len(data_), len(pipeline_tail)))
            for data_out in run_pipeline_steps(pipeline_tail, data_, output=output):
                if 'outputs' in output:
                    yield data_out
        else:
            data_out = data_
            if 'outputs' in output:
                yield data_out

    if output == 'last-output' and data_out:
        yield data_out


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