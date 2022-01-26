# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""generic image metadata extractor"""

from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.extractors.image')
from datalad.log import log_progress

from PIL import Image
from datalad.metadata.extractors.base import BaseMetadataExtractor
from datalad.support.exceptions import CapturedException

vocabulary = {
    "spatial_resolution(dpi)": {
        '@id': "idqa:0000162",
        'unit': "uo:0000240",  # DPI
        'unit_label': 'dpi',
        'description': "spatial resolution in dot-per-inch"},
    "color_mode": {
        '@id': 'idqa:0000160',
        'description': 'color resolution/mode'},
}


mode_map = {
    '1': '1-bit pixels, black and white, stored with one pixel per byte',
    'L': '8-bit pixels, black and white',
    'P': '8-bit pixels, mapped to any other mode using a color palette',
    'RGB': '3x8-bit pixels, true color',
    'RGBA': '4x8-bit pixels, true color with transparency mask',
    'CMYK': '4x8-bit pixels, color separation',
    'YCbCr': '3x8-bit pixels, color video format',
    'LAB': '3x8-bit pixels, the L*a*b color space',
    'HSV': '3x8-bit pixels, Hue, Saturation, Value color space',
    'I': '32-bit signed integer pixels',
    'F': '32-bit floating point pixels',
}


class MetadataExtractor(BaseMetadataExtractor):

    _extractors = {
        'format': lambda x: x.format_description,
        'dcterms:SizeOrDuration': lambda x: x.size,
        'spatial_resolution(dpi)': lambda x: x.info.get('dpi', ''),
        'color_mode': lambda x: mode_map.get(x.mode, ''),
    }

    def get_metadata(self, dataset, content):
        if not content:
            return {}, []
        contentmeta = []
        log_progress(
            lgr.info,
            'extractorimage',
            'Start image metadata extraction from %s', self.ds,
            total=len(self.paths),
            label='image metadata extraction',
            unit=' Files',
        )
        for f in self.paths:
            absfp = opj(self.ds.path, f)
            log_progress(
                lgr.info,
                'extractorimage',
                'Extract image metadata from %s', absfp,
                update=1,
                increment=True)
            try:
                img = Image.open(absfp)
            except Exception as e:
                lgr.debug("Image metadata extractor failed to load %s: %s",
                          absfp, CapturedException(e))
                continue
            meta = {
                'type': 'dctype:Image',
            }

            # run all extractors
            meta.update({k: v(img) for k, v in self._extractors.items()})
            # filter useless fields (empty strings and NaNs)
            meta = {k: v for k, v in meta.items()
                    if not (hasattr(v, '__len__') and not len(v))}
            contentmeta.append((f, meta))

        log_progress(
            lgr.info,
            'extractorimage',
            'Finished image metadata extraction from %s', self.ds
        )
        return {
            '@context': vocabulary,
        }, \
            contentmeta
