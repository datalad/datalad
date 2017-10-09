# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Audio metadata parser"""
from __future__ import absolute_import

import re
from os.path import join as opj
import logging
lgr = logging.getLogger('datalad.metadata.parser.audio')

from mutagen import File as audiofile
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.parsers.base import BaseMetadataParser


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


class MetadataParser(BaseMetadataParser):
    def get_metadata(self, dataset, content):
        if not content:
            return {}, []
        contentmeta = []
        for f in self.paths:
            info = audiofile(opj(self.ds.path, f), easy=True)
            if info is None:
                continue
            meta = {vocab_map.get(k, 'comment<{}>'.format(k)): info[k][0]
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
                    meta[vocab_map.get(k, 'comment<{}>'.format(k))] = val
            contentmeta.append((re.escape(f), meta))

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
                },
            },
        }, \
            contentmeta
