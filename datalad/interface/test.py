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
from datalad.interface.base import build_doc
from ..support.param import Parameter


@build_doc
class Test(Interface):
    """Run internal DataLad (unit)tests.

    This can be used to verify correct operation on the system.
    It is just a thin wrapper around a call to nose, so number of 
    exposed options is minimal
    """
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True

    _params_ = dict(
        verbose=Parameter(
            args=("-v", "--verbose"),
            action="store_true",
            doc="be verbose - list test names"),
        nocapture=Parameter(
            args=("-s", "--nocapture"),
            action="store_true",
            doc="do not capture stdout"),
        pdb=Parameter(
            args=("--pdb",),
            action="store_true",
            doc="drop into debugger on failures or errors"),
        stop=Parameter(
            args=("-x", "--stop"),
            action="store_true",
            doc="stop running tests after the first error or failure"),
        module=Parameter(
            args=("module",),
            nargs="?",
            doc="be verbose - list test names"),
    )

    @staticmethod
    def __call__(module='datalad', verbose=False, nocapture=False, pdb=False, stop=False):
        datalad.test(module=module, verbose=verbose, nocapture=nocapture, pdb=pdb, stop=stop)
