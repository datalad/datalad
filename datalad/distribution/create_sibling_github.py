# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Import shim to ease the transition after the move under distributed/"""

import warnings
warnings.warn(
    "CreateSiblingGithub has been moved to "
    "datalad.distributed.create_sibling_github. Please adjust the import.",
    DeprecationWarning)

from datalad.distributed.create_sibling_github import CreateSiblingGithub
