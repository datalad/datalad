# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""EXIF metadata extractor"""

from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.extractors.exif')
from datalad.log import log_progress

from exifread import process_file
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.extractors.base import BaseMetadataExtractor


def _return_as_appropriate_dtype(val):
    # TODO we could make an attempt to detect and convert
    # lists/arrays -- but it would be costly and have little gain
    # as we will in most cases convert back to string very quickly
    try:
        return float(val)
    except:
        try:
            return int(val)
        except:
            return val


class MetadataExtractor(BaseMetadataExtractor):
    def get_metadata(self, dataset, content):
        if not content:
            return {}, []
        log_progress(
            lgr.info,
            'extractorexif',
            'Start EXIF metadata extraction from %s', self.ds,
            total=len(self.paths),
            label='EXIF metadata extraction',
            unit=' Files',
        )
        contentmeta = []
        for f in self.paths:
            absfp = opj(self.ds.path, f)
            log_progress(
                lgr.info,
                'extractorexif',
                'Extract EXIF metadata from %s', absfp,
                update=1,
                increment=True)
            # TODO we might want to do some more elaborate extraction in the future
            # but for now plain EXIF, no maker extensions, no thumbnails
            info = process_file(open(opj(self.ds.path, f), 'rb'), details=False)
            if not info:
                # got nothing, likely nothing there
                continue
            meta = {k.split()[-1]: _return_as_appropriate_dtype(info[k].printable)
                    for k in info}
            contentmeta.append((f, meta))

        log_progress(
            lgr.info,
            'extractorexif',
            'Finished EXIF metadata extraction from %s', self.ds
        )
        return {
            '@context': {
                'exif': {
                    '@id': 'http://www.w3.org/2003/12/exif/ns/',
                    'description': 'Vocabulary to describe an Exif format picture data',
                    'type': vocabulary_id,
                },
            },
        }, \
            contentmeta
