# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" Extensible Metadata Platform (XMP) metadata extractor

https://en.wikipedia.org/wiki/Extensible_Metadata_Platform
"""

import re
from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.extractors.xmp')
from datalad.log import log_progress

from libxmp.utils import file_to_dict
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.extractors.base import BaseMetadataExtractor
from datalad.utils import ensure_unicode


xmp_field_re = re.compile(r'^([^\[\]]+)(\[\d+\]|)(/?.*|)')


class MetadataExtractor(BaseMetadataExtractor):
    def get_metadata(self, dataset, content):
        if not content:
            return {}, []
        context = {}
        contentmeta = []

        # which files to look for
        fname_match_regex = self.ds.config.get(
            'datalad.metadata.xmp.fname-match',
            '.*(jpg|jpeg|pdf|gif|tiff|tif|ps|eps|png|mp3|mp4|avi|wav)$')
        fname_match_regex = re.compile(fname_match_regex)

        log_progress(
            lgr.info,
            'extractorxmp',
            'Start XMP metadata extraction from %s', self.ds,
            total=len(self.paths),
            label='XMP metadata extraction',
            unit=' Files',
        )
        for f in self.paths:
            log_progress(
                lgr.info,
                'extractorxmp',
                'Extract XMP metadata from %s', f,
                update=1,
                increment=True)
            # run basic file name filter for performance reasons
            # it is OK to let false-positives through
            if fname_match_regex.match(f, re.IGNORECASE) is None:
                continue
            absfp = opj(self.ds.path, f)
            info = file_to_dict(absfp)
            if not info:
                # got nothing, likely nothing there
                # TODO check if this is an XMP sidecar file, parse that, and assign metadata
                # to the base file
                continue
            # update vocabulary
            vocab = {info[ns][0][0].split(':')[0]: {'@id': ns, 'type': vocabulary_id} for ns in info}
            # TODO this is dirty and assumed that XMP is internally consistent with the
            # definitions across all files -- which it likely isn't
            context.update(vocab)
            # now pull out actual metadata
            # cannot do simple dict comprehension, because we need to beautify things a little

            meta = {}
            for ns in info:
                for key, val, props in info[ns]:
                    if not val:
                        # skip everything empty
                        continue
                    if key.count('[') > 1:
                        # this is a nested array
                        # MIH: I do not think it is worth going here
                        continue
                    if props['VALUE_IS_ARRAY']:
                        # we'll catch the actual array values later
                        continue
                    # normalize value
                    val = ensure_unicode(val)
                    # non-breaking space
                    val = val.replace(u"\xa0", ' ')

                    field, idx, qual = xmp_field_re.match(key).groups()
                    normkey = u'{}{}'.format(field, qual)
                    if '/' in key:
                        normkey = u'{0}<{1}>'.format(*normkey.split('/'))
                    if idx:
                        # array
                        arr = meta.get(normkey, [])
                        arr.append(val)
                        meta[normkey] = arr
                    else:
                        meta[normkey] = val
            # compact
            meta = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in meta.items()}

            contentmeta.append((f, meta))

        log_progress(
            lgr.info,
            'extractorxmp',
            'Finished XMP metadata extraction from %s', self.ds
        )
        return {
            '@context': context,
        }, \
            contentmeta
