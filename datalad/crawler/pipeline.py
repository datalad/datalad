# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from .newmain import lgr

class FinishPipeline(Exception):
    """Exception to use to signal that any given pipeline should be stopped
    """
    pass

# TODO: should may be pipeline return data as well?
#       or may be it should return some stats or smth else than the data
#       use-case: not sure yet. cons: we would need explicit "terminators" for the pipelins
def run_pipeline(pipeline, **data):
    """Run a pipeline

    Pipeline is just a list of actions or other pipelines (lists, tuples)
    """
    try:
        run_pipeline_steps(pipeline, **data)
    except FinishPipeline as e:
        lgr.debug("Got a signal that pipeline %s is 'finished'" % pipeline)

def run_pipeline_steps(pipeline, **data):
    """Actually run pipeline steps, feeding yielded results to the next node

    Recursive beast which runs a single node and then recurses to run the rest,
    possibly multiple times if current node is a generator
    """
    if not len(pipeline):
        return
    node, pipeline_tail = pipeline[0], pipeline[1:]
    if isinstance(node, (list, tuple)):
        # we have got a step which is yet another entire pipeline
        run_pipeline(node, **data)
        # there is no yielding or results from a pipeline
        # and we just then go to the next
        run_pipeline_steps(pipeline_tail, **data)
    else:  # it is a "node" which should generate us stuff to feed into the rest of the pipeline
        # TODO: may be allow non generators
        lgr.debug("Node: %s" % node)
        for data_ in node(**data):
            # TODO: for heavy debugging we might want to track/report what node has changed in data
            lgr.log(7, " pass %d keys into tail with %d elements" % (len(data_), len(pipeline_tail)))
            run_pipeline_steps(pipeline_tail, **data_)
