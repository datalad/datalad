# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata parsers"""

from . import bids
from . import frictionless_datapackage

# TODO: consider bringing common functionality together via a class hierarchy
# something along the
# BaseMetaParser -> JSONMetaParser -> {BIDS, Frictionless_DataPackage}?