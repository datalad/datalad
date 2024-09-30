# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

import warnings

warnings.warn(
    "All of datalad.cmdline is deprecated/discontinued as of datalad 0.16. "
    "A new CLI implementation is available at datalad.cli. "
    "Please adjust any imports.",
    DeprecationWarning)
