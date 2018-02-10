# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""NIfTI metadata extractor"""

from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.extractors.nifti1')

from math import isnan
import nibabel
import numpy as np
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.extractors.base import BaseMetadataExtractor
from datalad.dochelpers import exc_str


vocabulary = {
    'nifti1': {
        '@id': 'https://nifti.nimh.nih.gov/nifti-1/documentation/nifti1fields#',
        'description': 'Ad-hoc vocabulary for NIfTI1 header fields',
        'type': vocabulary_id},
    "spatial_resolution(mm)": {
        '@id': "idqa:0000162",
        'unit': "uo:0000016",
        'unit_label': 'millimeter',
        'description': "spatial resolution in millimeter"},
    "temporal_spacing(s)": {
        '@id': "idqa:0000213",
        'unit': "uo:0000010",
        'unit_label': 'second',
        'description': "temporal sample distance in 4D (in seconds)"},
}

unit_map = {
    'meter': ('meter', 'uo:0000008'),
    'millimeter': ('millimiter', 'uo:0000016'),
    'mm': ('millimiter', 'uo:0000016'),
    'micron': ('micrometer', 'uo:0000017'),
    'second': ('second', 'uo:0000010'),
    'sec': ('second', 'uo:0000010'),
    'usec': ('microsecond', 'uo:0000029'),
    'hertz': ('hertz', 'uo:0000106'),
    'hz': ('hertz', 'uo:0000106'),
    'ppm': ('parts per million', 'uo:0000109'),
    'rad': ('radian', 'uo:0000123'),
    'rads': ('radian', 'uo:0000123'),
}

# to serve as a default for when expect 0 to be consumable by np.asscalar
_array0 = np.array(0)

class MetadataExtractor(BaseMetadataExtractor):

    _key2stdkey = {
        'descrip': 'description',
    }
    _extractors = {
        'datatype': lambda x: x.get_data_dtype().name,
        'intent': lambda x: x.get_intent(code_repr='label')[0],
        'freq_axis': lambda x: x.get_dim_info()[0],
        'phase_axis': lambda x: x.get_dim_info()[1],
        'slice_axis': lambda x: x.get_dim_info()[2],
        'xyz_unit': lambda x: '{} ({})'.format(
            *unit_map[x.get_xyzt_units()[0]]) if x.get_xyzt_units()[0] in unit_map else '',
        't_unit': lambda x: '{} ({})'.format(
            *unit_map[x.get_xyzt_units()[1]]) if x.get_xyzt_units()[1] in unit_map else '',
        'qform_code': lambda x: nibabel.nifti1.xform_codes.label[
            np.asscalar(x.get('qform_code', _array0))],
        'sform_code': lambda x: nibabel.nifti1.xform_codes.label[
            np.asscalar(x.get('sform_code', _array0))],
        'slice_order': lambda x: nibabel.nifti1.slice_order_codes.label[
            np.asscalar(x.get('slice_code', _array0))],
    }
    _ignore = {
        'datatype',
        'intent_p1',
        'intent_p2',
        'intent_p3',
        'intent_code',
        'dim_info',
        'xyzt_units',
        'qform_code',
        'sform_code',
        'quatern_b',
        'quatern_c',
        'quatern_d',
        'qoffset_x',
        'qoffset_y',
        'qoffset_z',
        'srow_x',
        'srow_y',
        'srow_z',
        'slice_code',
        'bitpix',
        # unused fields in the ANALYZE header
        'data_type',
        'db_name',
        'extents',
        'session_error',
        'regular',
        'glmax',
        'glmin',
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
                lgr.debug("NIfTI metadata extractor failed to load %s: %s",
                          fpath, exc_str(e))
                continue
            if not isinstance(header, nibabel.Nifti1Header):
                # all we can do for now
                lgr.debug("Ignoring non-NIfTI1 file %s", fpath)
                continue

            # blunt conversion of the entire header
            meta = {self._key2stdkey.get(k, k):
                    [np.asscalar(i) for i in v]
                    if len(v.shape)
                    # scalar
                    else np.asscalar(v)
                    for k, v in header.items()
                    if k not in self._ignore}
            # more convenient info from nibabel's support functions
            meta.update(
                {k: v(header) for k, v in self._extractors.items()})
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
            meta['spatial_resolution(mm)'] = \
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
                    meta['temporal_spacing(s)'] = \
                        header.get_zooms()[3] * rts_unit_conversion

            contentmeta.append((f, meta))

        return {
            '@context': vocabulary,
        }, \
            contentmeta
