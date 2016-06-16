# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for moving dataset content

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.interface.base import Interface


class Move(Interface):
    """Move dataset content."""

    _params_ = dict(
        path=Parameter(
            args=('path',),
            nargs='?',
            doc="name of or path to the content to be updated",
            constraints=EnsureStr() | EnsureNone()))

    @staticmethod
    def __call__(path=curdir):

        raise NotImplementedError("TODO")
