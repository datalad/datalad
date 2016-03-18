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


class Test(Interface):
    """Run internal DataLad (unit)tests.

    This can be used to verify correct operation on the system
    """
    @staticmethod
    def __call__():
        datalad.test()
