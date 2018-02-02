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
__lgr = __logging.getLogger('datalad.metadata.extractors')

from importlib import import_module as __impmod

for __modname in (
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
        'xmp'):
    try:
        globals()[__modname] = __impmod(
            '.{}'.format(__modname),
            'datalad.metadata.extractors')
    except Exception as _e:
        from datalad.dochelpers import exc_str as _exc_str
        __lgr.debug('Metadata extractor %s unusable: %s', __modname, _exc_str(_e))
