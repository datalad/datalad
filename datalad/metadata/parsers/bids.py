# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""BIDS metadata parser (http://bids.neuroimaging.io)"""

from os.path import join as opj
from datalad.support.json_py import load as jsonload
from datalad.metadata.parsers.base import BaseMetadataParser


class MetadataParser(BaseMetadataParser):
    _core_metadata_filenames = ['dataset_description.json']

    def _get_metadata(self, ds_identifier, meta, full):
        bids = jsonload(
            self.get_core_metadata_filenames()[0])

        # TODO maybe normalize labels of standard licenses to definition URIs
        # perform mapping
        for bidsterm, dataladterm in (('Name', 'name'),
                                      ('License', 'license'),
                                      ('Authors', 'author'),
                                      ('ReferencesAndLinks', 'citation'),
                                      ('Funding', 'foaf:fundedBy'),
                                      ('Description', 'description')):
            if bidsterm in bids:
                meta[dataladterm] = bids[bidsterm]

        if 'description' not in meta:
            # BIDS uses README to provide description, so if was not
            # explicitly provided to possibly override longer README, let's just
            # load README
            meta['description'] = open(opj(self.ds.path, 'README')).read().strip()

        compliance = ["http://docs.datalad.org/metadata.html#v0-1"]

        # special case
        if bids.get('BIDSVersion'):
            compliance.append(
                'http://bids.neuroimaging.io/bids_spec{}.pdf'.format(
                    bids['BIDSVersion'].strip()))
        else:
            compliance.append('http://bids.neuroimaging.io')
        meta['dcterms:conformsTo'] = compliance
        return meta
