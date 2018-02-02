# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""DICOM metadata extractor"""
from __future__ import absolute_import

from six import string_types
from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.extractors.dicom')

try:
    # renamed for 1.0 release
    import pydicom as dcm
    from pydicom.errors import InvalidDicomError
except ImportError:
    import dicom as dcm
    from dicom.errors import InvalidDicomError

from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.extractors.base import BaseMetadataExtractor


def _is_good_type(v):
    if isinstance(v, (int, float, string_types)):
        return True
    elif isinstance(v, (list, tuple)):
        return all(map(_is_good_type, v))
    else:
        return False


context = {
    'dicom': {
        # switch to http://dicom.nema.org/resources/ontology/DCM/
        # but requires mapping plain text terms to numbers
        '@id': 'http://semantic-dicom.org/dcm#',
        'description': 'DICOM vocabulary (seemingly incomplete)',
        'type': vocabulary_id}
}


def _struct2dict(struct):
    return {k: getattr(struct, k)
            for k in struct.dir()
            if hasattr(struct, k) and
            _is_good_type(getattr(struct, k))}


class MetadataExtractor(BaseMetadataExtractor):
    def get_metadata(self, dataset, content):
        imgseries = {}
        imgs = {}
        lgr.info("Attempting to extract DICOM metadata from %i files", len(self.paths))
        for f in self.paths:
            try:
                d = dcm.read_file(opj(self.ds.path, f), stop_before_pixels=True)
            except InvalidDicomError:
                # we can only ignore
                lgr.debug('"%s" does not look like a DICOM file, skipped', f)
                continue
            ddict = None
            if content:
                ddict = _struct2dict(d)
                imgs[f] = ddict
            if d.SeriesInstanceUID not in imgseries:
                # start with a copy of the metadata of the first dicom in a series
                series = _struct2dict(d) if ddict is None else ddict.copy()
                series_files = []
            else:
                series, series_files = imgseries.get(d.SeriesInstanceUID)
                # compare incoming with existing metadata set
                series = {
                    k: series[k] for k in series
                    # only keys that exist and have values that are identical
                    # across all images in the series
                    if hasattr(d, k) and getattr(d, k) == series[k]
                }
            series_files.append(f)
            # store
            imgseries[d.SeriesInstanceUID] = (series, series_files)

        dsmeta = {
            '@context': context,
            'Series': [info for info, files in imgseries.values()]
        }
        return (
            # no dataset metadata (for now), a summary of all DICOM values will
            # from generic code upstairs
            dsmeta,
            # yield the corresponding series description for each file
            imgs.items() if content else []
        )
