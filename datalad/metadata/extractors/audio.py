# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Audio metadata extractor"""
from __future__ import absolute_import

from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.extractors.audio')
from datalad.log import log_progress

from mutagen import File as audiofile
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.extractors.base import BaseMetadataExtractor


# how properties reported by mutagen map onto our vocabulary
vocab_map = {
    'album': 'music:album',
    'artist': 'music:artist',
    'channels': 'music:channels',
    'composer': 'music:Composer',
    'copyright': 'dcterms:rights',
    'genre': 'music:Genre',
    'length': 'duration(s)',
    'sample_rate': 'music:sample_rate',
    'title': 'name',
}


class MetadataExtractor(BaseMetadataExtractor):

    _unique_exclude = {'bitrate'}

    def get_metadata(self, dataset, content):
        if not content:
            return {}, []
        log_progress(
            lgr.info,
            'extractoraudio',
            'Start audio metadata extraction from %s', self.ds,
            total=len(self.paths),
            label='audio metadata extraction',
            unit=' Files',
        )
        contentmeta = []
        for f in self.paths:
            absfp = opj(self.ds.path, f)
            log_progress(
                lgr.info,
                'extractoraudio',
                'Extract audio metadata from %s', absfp,
                update=1,
                increment=True)
            info = audiofile(absfp, easy=True)
            if info is None:
                continue
            meta = {vocab_map.get(k, k): info[k][0]
                    if isinstance(info[k], list) and len(info[k]) == 1 else info[k]
                    for k in info}
            if hasattr(info, 'mime') and len(info.mime):
                meta['format'] = 'mime:{}'.format(info.mime[0])
            for k in ('length', 'channels', 'bitrate', 'sample_rate'):
                if hasattr(info.info, k):
                    val = getattr(info.info, k)
                    if k == 'length':
                        # duration comes in seconds, cap at millisecond level
                        val = round(val, 3)
                    meta[vocab_map.get(k, k)] = val
            contentmeta.append((f, meta))

        log_progress(
            lgr.info,
            'extractoraudio',
            'Finished audio metadata extraction from %s', self.ds
        )
        return {
            '@context': {
                'music': {
                    '@id': 'http://purl.org/ontology/mo/',
                    'description': 'Music Ontology with main concepts and properties for describing music',
                    'type': vocabulary_id,
                },
                'duration(s)': {
                    "@id": 'time:Duration',
                    "unit": "uo:0000010",
                    'unit_label': 'second',
                },
            },
        }, \
            contentmeta
