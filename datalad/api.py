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
from .support.handle import Handle

from .interface.base import Interface as _Interface
from .interface.base import update_docstring as _update_docstring
from . import interface as _interfaces

# auto detect all available interfaces and generate a function-based
# API from them
for _item in _interfaces.__dict__:
    _intfcls = getattr(_interfaces, _item)
    try:
        if not issubclass(_intfcls, _Interface):
            continue
    except TypeError:
        continue
    _intf = _intfcls()
    # convert the parameter SPEC into a docstring for the function
    _update_docstring(_intf.__call__.__func__, _intf._params_)
    # register the function in the namespace, using the name of the
    # module it is defined in
    globals()[_intf.__module__.split('.')[-1]] = _intf.__call__
    # cleanup namespace
    del _intf
    del _intfcls

# be nice and clean up the namespace properly
del _update_docstring
del _interfaces
del _Interface
