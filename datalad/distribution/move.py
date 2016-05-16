# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for moving a handle

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.interface.base import Interface


class Move(Interface):
    """Move a handle."""

    _params_ = dict(
        handle=Parameter(
            args=('handle',),
            nargs='?',
            doc="name of or path to the handle to be updated",
            constraints=EnsureStr() | EnsureNone()))

    @staticmethod
    def __call__(handle=curdir):

        raise NotImplementedError("TODO")
