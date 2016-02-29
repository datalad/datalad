# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for removing a handle from another handle

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules


class POCRemove(Interface):
    """Remove a handle from another handle."""

    _params_ = dict(
        src_handle=Parameter(
            args=('handle',),
            nargs='?',
            doc="name of or path to the handle to be removed.",
            constraints=EnsureStr()),
        dst_handle=Parameter(
            args=('handle',),
            nargs='?',
            doc="name of or path to the handle, src-handle is to be removed "
                "from.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, src_handle, dst_handle=curdir):

        raise NotImplementedError("TODO")