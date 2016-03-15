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
from datalad.support.dataset import EnsureDataSet, datasetmethod

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

    @datasetmethod(name="some_method")
    def __call__(self, path):
        # Note: We can either call constraints directly or use the ones defined
        # in _params_ for commandline interface. In the latter case, we can't
        # use 'self', due to the binding to the DataSet class.
        path = APIConceptDemo._params_['path'].constraints(path)

        print("Type received: %s" % type(path))
        print("To string: %s" % path)
        try:
            print("Path received: %s" % path._path)
        except AttributeError:
            pass




