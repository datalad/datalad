# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata parsers"""

# this is needed to make the on-demand import logic for metadata extraction work
from . import datalad_core
from . import bids
from . import frictionless_datapackage
from . import datalad_rfc822
from . import datacite
from . import audio
from . import exif
from . import xmp
from . import dicom
