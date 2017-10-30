# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""NIfTI metadata parser"""

from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.parser.nifti1')

from math import isnan
import nibabel
import numpy as np
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.parsers.base import BaseMetadataParser
from datalad.dochelpers import exc_str


vocabulary = {
    'nifti1': {
        '@id': 'https://nifti.nimh.nih.gov/nifti-1/documentation/nifti1fields#',
        'description': 'Ad-hoc vocabulary for NIfTI1 header fields',
        'type': vocabulary_id},
    "3d_spatial_resolution(mm)": {
        '@id': "",
        'unit': "",  # mm
        'description': ""},
    "4d_spacing(s)": {
        '@id': "",
        'unit': "",  # mm
        'description': ""},
}


class MetadataParser(BaseMetadataParser):

    _key2stdkey = {
        'descrip': 'description',
    }

    def get_metadata(self, dataset, content):
        if not content:
            return {}, []
        contentmeta = []
        for f in self.paths:
            fpath = opj(self.ds.path, f)
            try:
                header = nibabel.load(fpath).header
            except Exception as e:
                lgr.debug("NIfTI metadata parser failed to load %s: %s",
                          fpath, exc_str(e))
                continue
            if not isinstance(header, nibabel.Nifti1Header):
                # all we can do for now
                lgr.debug("Ignoring non-NIfTI1 file %s", fpath)
                continue

            # blunt conversion of the entire header
            meta = {self._key2stdkey.get(k, 'nifti1:{}'.format(k)):
                    [np.asscalar(i) for i in v]
                    if len(v.shape)
                    # scalar
                    else np.asscalar(v)
                    for k, v in header.items()}
            # filter useless fields (empty strings and NaNs)
            meta = {k: v for k, v in meta.items()
                    if not (isinstance(v, float) and isnan(v)) and
                    not (hasattr(v, '__len__') and not len(v))}
            # a few more convenient targeted extracts from the header
            # spatial resolution in millimeter
            spatial_unit = header.get_xyzt_units()[0]
            # by what factor to multiply by to get to 'mm'
            if spatial_unit == 'unknown':
                lgr.debug(
                    "unit of spatial resolution for '{}' unknown, assuming 'millimeter'".format(
                        fpath))
            spatial_unit_conversion = {
                'unknown': 1,
                'meter': 1000,
                'mm': 1,
                'micron': 0.001}.get(spatial_unit, None)
            if spatial_unit_conversion is None:
                lgr.debug("unexpected spatial unit code '{}' from NiBabel".format(
                    spatial_unit))
            # TODO does not see the light of day
            meta['3d_spatial_resolution(mm)'] = \
                [(i * spatial_unit_conversion) for i in header.get_zooms()[:3]]
            # time
            if len(header.get_zooms()) > 3:
                # got a 4th dimension
                rts_unit = header.get_xyzt_units()[1]
                if rts_unit == 'unknown':
                    lgr.warn(
                        "RTS unit '{}' unkown, assuming 'seconds'".format(
                            fpath))
                # normalize to seconds, if possible
                rts_unit_conversion = {
                    'msec': 0.001,
                    'micron': 0.000001}.get(rts_unit, 1.0)
                if rts_unit not in ('hz', 'ppm', 'rads'):
                    meta['4d_spacing(s)'] = \
                        header.get_zooms()[3] * rts_unit_conversion

            contentmeta.append((f, meta))

        return {
            '@context': vocabulary,
        }, \
            contentmeta
