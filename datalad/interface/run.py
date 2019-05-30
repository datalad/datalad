# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Compatibility module for datalad.core.local.run.

Use datalad.core.local.run instead."""

__docformat__ = 'restructuredtext'

import warnings

from datalad.core.local.run import *
from datalad.core.local.run import (
    _execute_command,
    _format_cmd_shorty,
    _install_and_reglob,
    _unlock_or_remove,
)

warnings.warn("datalad.interface.run is obsolete. "
              "Use datalad.core.local.run module instead",
              DeprecationWarning)
