# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from .config import load_config, EnhancedConfigParser
from .db import load_db, save_db
from .support.archives import decompress_file
from .crawler.main import DoubleAnnexRepo
from .support.handlerepo import HandleRepo

from .interface.base import update_docstring_with_parameters as _update_docstring
from .interface.base import get_interface_groups as _get_interface_groups
from . import interface as _interfaces

# auto detect all available interfaces and generate a function-based
# API from them

for _grp_name, _grp_descr, _interfaces in _get_interface_groups():
    for _intfcls in _interfaces:
        _intf = _intfcls()
        _spec = getattr(_intf, '_params_', dict())
        # convert the parameter SPEC into a docstring for the function
        _update_docstring(_intf.__call__.__func__, _spec)
        # register the function in the namespace, using the name of the
        # module it is defined in
        globals()[_intf.__module__.split('.')[-1]] = _intf.__call__
        # cleanup namespace
        del _intf
        del _intfcls

# be nice and clean up the namespace properly
del _grp_name
del _grp_descr
del _update_docstring
del _interfaces
del _get_interface_groups
