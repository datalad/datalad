# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for adding a handle to another handle

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.cmdline.helpers import POC_get_datalad_master
from .base import Interface
from .POC_helpers import get_submodules


class POCAdd(Interface):
    """Add a handle to another handle."""

    _params_ = dict(
        src_handle=Parameter(
            args=('handle',),
            nargs='?',
            doc="name of or path to the handle to be added.",
            constraints=EnsureStr()),
        dst_handle=Parameter(
            args=('handle',),
            nargs='?',
            doc="name of or path to the handle, src-handle is to be added to.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, src_handle, dst_handle=curdir):

        raise NotImplementedError("TODO")