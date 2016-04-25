# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad API exposing user-oriented commands (also available via CLI)"""

from importlib import import_module as _impmod

from .interface.base import update_docstring_with_parameters as _update_docstring
from .interface.base import get_interface_groups as _get_interface_groups
from .interface.base import dedent_docstring as _dedent_docstring
from .distribution.dataset import Dataset

# auto detect all available interfaces and generate a function-based
# API from them

for _grp_name, _grp_descr, _interfaces in _get_interface_groups():
    for _intfspec in _interfaces:
        # turn the interface spec into an instance
        _mod = _impmod(_intfspec[0], package='datalad')
        _intf = getattr(_mod, _intfspec[1])
        _spec = getattr(_intf, '_params_', dict())

        # FIXME no longer using an interface class instance
        # convert the parameter SPEC into a docstring for the function
        _update_docstring(_intf.__call__, _spec,
                          prefix=_dedent_docstring(_intf.__doc__),
                          suffix=_dedent_docstring(_intf.__call__.__doc__))
        # register the function in the namespace, using the name of the
        # module it is defined in
        if len(_intfspec) > 3:
            api_name = _intfspec[3]
        else:
            api_name = _intf.__module__.split('.')[-1]
        globals()[api_name] = _intf.__call__
        # cleanup namespace
        del _mod
        del _intfspec
        del _intf

# be nice and clean up the namespace properly
del _interfaces
del _impmod
del _get_interface_groups
del _grp_name
del _grp_descr
del _spec
del _update_docstring
del _dedent_docstring
