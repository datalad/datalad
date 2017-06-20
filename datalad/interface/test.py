# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run internal DataLad (unit)tests to verify correct operation on the system"""


__docformat__ = 'restructuredtext'


import datalad
from .base import Interface
from datalad.interface.utils import build_doc


@build_doc
class Test(Interface):
    """Run internal DataLad (unit)tests.

    This can be used to verify correct operation on the system
    """
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True
    @staticmethod
    def __call__():
        datalad.test()
