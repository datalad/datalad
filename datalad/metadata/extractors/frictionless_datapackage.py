# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Extractor for friction-less data packages
(http://specs.frictionlessdata.io/data-packages)
"""

import logging
lgr = logging.getLogger('datalad.metadata.extractors.frictionless_datapackage')
from os.path import join as opj, exists
from datalad.support.json_py import load as jsonload
from datalad.metadata.extractors.base import BaseMetadataExtractor


def _compact_author(obj):
    if isinstance(obj, dict):
        bits = []
        if 'name' in obj:
            bits.append(obj['name'])
        if 'email' in obj:
            bits.append('<{}>'.format(obj['email']))
        if 'web' in obj:
            bits.append('({})'.format(obj['web']))
        return ' '.join(bits)
    else:
        return obj


def _compact_license(obj):
    if isinstance(obj, dict):
        # With obj itself if no url or type
        obj = obj.get('path', obj.get('type', obj))
        if isinstance(obj, dict) and len(obj) == 1:
            # didn't get lucky with compacting, try one more
            obj = obj.popitem()[1]
        return obj
    else:
        return obj


class MetadataExtractor(BaseMetadataExtractor):
    metadatasrc_fname = 'datapackage.json'

    _key2stdkey = {
        'name': 'name',
        'title': 'shortdescription',
        'description': 'description',
        'keywords': 'tag',
        'version': 'version',
        'homepage': 'homepage',
    }

    def _get_dataset_metadata(self):
        meta = {}
        metadata_path = opj(self.ds.path, self.metadatasrc_fname)
        if not exists(metadata_path):
            return meta
        foreign = jsonload(metadata_path)

        for term in self._key2stdkey:
            if term in foreign:
                meta[self._key2stdkey[term]] = foreign[term]
        if 'author' in foreign:
            meta['author'] = _compact_author(foreign['author'])
        if 'contributors' in foreign:
            meta['contributors'] = [_compact_author(c)
                                    for c in foreign['contributors']]
        # two license terms were supported at some point
        if 'license' in foreign:
            meta['license'] = _compact_license(foreign['license'])
        if 'licenses' in foreign:
            meta['license'] = [_compact_license(l) for l in foreign['licenses']]

        meta['conformsto'] = 'http://specs.frictionlessdata.io/data-packages'

        return meta

    def _get_content_metadata(self):
        return []
