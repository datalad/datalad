# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad API exposing user-oriented commands (also available via CLI)"""

from datalad.coreapi import *


def _load_plugins():
    from datalad.plugin import _get_plugins
    from datalad.plugin import _load_plugin
    from datalad.interface.base import get_api_name
    import re

    camel = re.compile(r'([a-z])([A-Z])')

    for pname, props in _get_plugins():
        pi = _load_plugin(props['file'], fail=False)
        if pi is None:
            continue
        globals()[camel.sub('\\1_\\2', pi.__name__).lower()] = pi.__call__


_load_plugins()

# Be nice and clean up the namespace properly
del _load_plugins
