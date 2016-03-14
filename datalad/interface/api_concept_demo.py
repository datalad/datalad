# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Temporary demo command. Its purpose is to demonstrate how the class DataSet,
interface callables and constraints work together.
"""

import logging

from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, evaluate_constraints
from datalad.support.dataset import EnsureDataSet

lgr = logging.getLogger('datalad.interface.api-concept-demo')


class APIConceptDemo(Interface):
    """Just a demo.

    Some more doc.

    Examples:

      $ datalad api-concept-demo what/ever/path
    """
    _params_ = dict(
        path=Parameter(
            doc="some path to generate a DataSet instance for.",
            constraints=EnsureDataSet()))

    # TODO:
    # Decorator doesn't work here yet. Class Interface uses inspect to get
    # signature of __call__, which is obscured by the decorator.
    # Tried to use functools.wraps/update_wrapper to assign func_code and
    # func_defaults to the wrapper function (these two are apparently used by
    # getargspec). But didn't work yet. update_wrapper calls setattr, which
    # then raises a ValueError, complaining, that the code object has 0 free
    # vars, where at least one is expected. Not clear yet, who exactly is
    # expecting this and why.
    #
    # May be we don't the decorator here at all. Command line interface doesn't
    # need it, only python API does.
    # So, may be there is a way to apply the decorator, when loading the
    # callable into the API and circumnavigate the inspection.

    #@evaluate_constraints
    def __call__(self, path):
        print "Type received: %s" % type(path)
        print "To string: %s" % path
        try:
            print "Path received: %s" % path._path
        except AttributeError:
            pass




