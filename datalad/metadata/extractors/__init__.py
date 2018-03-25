# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata extractors"""

import logging as __logging
from datalad.utils import import_modules as __import_modules

__all__ = [
    'annex',
    'audio',
    'bids',
    'datacite',
    'datalad_core',
    'datalad_rfc822',
    'dicom',
    'exif',
    'frictionless_datapackage',
    'image',
    'nidm',
    'nifti1',
    'xmp',
]

__import_modules(
    __all__,
    pkg=__name__,
    msg='Metadata extractor {module} is unusable',
    log=__logging.getLogger(__name__).debug)
