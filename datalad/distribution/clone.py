# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Compatibility module for datalad.core.distributed.clone.

Use datalad.core.distributed.clone instead."""

__docformat__ = 'restructuredtext'

import warnings

from datalad.core.distributed.clone import (
    Clone,
    _get_installationpath_from_url,
    _handle_possible_annex_dataset,
    _get_tracking_source,
)

warnings.warn("datalad.distribution.clone is obsolete. "
              "Use datalad.core.distributed.clone module instead",
              DeprecationWarning)
