# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
# Compatibility kludge for now to not break anything relying on datalad.version
#

import warnings

from ._version import get_versions

warnings.warn(
    "datalad.version module will be removed in 0.16. "
    "Please use datalad.__version__ (no other __*_version__ variables are to be provided).",
    DeprecationWarning)

__version__ = get_versions()['version']
__hardcoded_version__ = __version__
__full_version__ = __version__

del get_versions
