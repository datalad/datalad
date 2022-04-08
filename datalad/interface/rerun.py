# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Obsolete module: moved to `local.rerun`
"""

import warnings
warnings.warn(
    "ReRun has been moved to datalad.local.rerun. "
    "This module was deprecated in 0.16.0, and will be removed in a future "
    "release. Please adjust the import.",
    DeprecationWarning)

# Import command class to ease 3rd-party transitions
from datalad.local.rerun import *
