# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad API exposing user-oriented commands (also available via CLI)"""

from .interface.base import update_docstring_with_parameters as _update_docstring
from .interface.base import get_interface_groups as _get_interface_groups
from .interface.base import dedent_docstring as _dedent_docstring
# TODO:  make those lazy!  ATM importing api requires importing nearly everything
# which causes even e.g. unrelated to distribution parts import rdflib (300ms alone)
# etc.  Ideally all the bindings/docstrings should be generated upon the first
# access to them from within api module
from . import interface as _interfaces
from .support.dataset import Dataset

# auto detect all available interfaces and generate a function-based
# API from them

for _grp_name, _grp_descr, _interfaces in _get_interface_groups():
    for _intfcls in _interfaces:
        _intf = _intfcls()
        _spec = getattr(_intf, '_params_', dict())
        # convert the parameter SPEC into a docstring for the function
        _update_docstring(_intf.__call__.__func__, _spec,
                          prefix=_dedent_docstring(_intfcls.__doc__),
                          suffix=_dedent_docstring(_intfcls.__call__.__doc__))
        # register the function in the namespace, using the name of the
        # module it is defined in
        globals()[_intf.__module__.split('.')[-1]] = _intf.__call__
        # cleanup namespace
        del _intf
        del _intfcls

# be nice and clean up the namespace properly
del _interfaces
del _get_interface_groups
del _grp_name
del _grp_descr
del _spec
del _update_docstring
del _dedent_docstring
