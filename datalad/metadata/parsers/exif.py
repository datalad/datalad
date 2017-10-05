# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""EXIF metadata parser"""

import re
from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.parser.exif')

from exifread import process_file
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.parsers.base import BaseMetadataParser


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


class MetadataParser(BaseMetadataParser):
    def get_metadata(self, dataset, content):
        if not content:
            return {}, []
        contentmeta = []
        for f in self.paths:
            # TODO we might want to do some more elaborate extraction in the future
            # but for now plain EXIF, no maker extensions, no thumbnails
            info = process_file(open(opj(self.ds.path, f), 'rb'), details=False)
            if not info:
                # got nothing, likely nothing there
                continue
            meta = {'exif:{}'.format(k.split()[-1]): _return_as_appropriate_dtype(info[k].printable)
                    for k in info}
            contentmeta.append((re.escape(f), meta))

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
