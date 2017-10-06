# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""BIDS metadata parser (http://bids.neuroimaging.io)"""

import csv
from io import open
from os.path import join as opj
from os.path import exists
from datalad.support.json_py import load as jsonload
from datalad.dochelpers import exc_str
from datalad.metadata.parsers.base import BaseMetadataParser
from datalad.metadata.definitions import vocabulary_id

import logging
lgr = logging.getLogger('datalad.meta.bids')


# BIDS parser metadata definitions (dlp_bids:)
vocabulary = {
    "dlp_bids": {
        'def': 'TODO',
        'descr': 'Vocabulary of the DataLad BIDS metadata parser',
        'type': vocabulary_id},
    # characteristics (metadata keys)
    "dlp_bids:age(years)": {
        '@id': "pato:0000011",
        'unit': "uo:0000036",  # year
        'description': "age of a sample (organism) at the time of data acquisition in years"},
    "dlp_bids:sex": {
        '@id': "pato:0000047",
        'description': "biological sex"},
    # qualities (metadata values)
    "dlp_bids:female": {
        '@id': "pato:0000383",
        'description': "A biological sex quality inhering in an individual or a population that only produces gametes that can be fertilised by male gametes"},
    "dlp_bids:male": {
        '@id': "pato:0000384",
        'description': "A biological sex quality inhering in an individual or a population whose sex organs contain only male gametes"},
}

# only BIDS metadata properties that match a key in this dict will be considered
# for reporting
content_metakey_map = {
    'age': 'dlp_bids:age(years)',
    'sex': 'dlp_bids:sex',
}

sex_label_map = {
    'female': 'dlp_bids:female',
    'f': 'dlp_bids:female',
    'male': 'dlp_bids:male',
    'm': 'dlp_bids:male',
}


class MetadataParser(BaseMetadataParser):
    _core_metadata_filename = 'dataset_description.json'

    _key2stdkey = {
        'Name': 'name',
        'License': 'license',
        'Authors': 'author',
        'ReferencesAndLinks': 'citation',
        'Funding': 'fundedby',
        'Description': 'description',
    }

    def _get_dataset_metadata(self):
        meta = {}
        metadata_path = opj(self.ds.path, self._core_metadata_filename)
        if not exists(metadata_path):
            return meta
        bids = jsonload(metadata_path)

        # TODO maybe normalize labels of standard licenses to definition URIs
        # perform mapping
        for term in self._key2stdkey:
            if term in bids:
                meta[self.get_homogenized_key(term)] = bids[term]

        README_fname = opj(self.ds.path, 'README')
        if not meta.get('description') and exists(README_fname):
            # BIDS uses README to provide description, so if was not
            # explicitly provided to possibly override longer README, let's just
            # load README
            try:
                desc = open(README_fname, encoding="utf-8").read()
            except UnicodeDecodeError as exc:
                lgr.warning(
                    "Failed to decode content of %s. "
                    "Re-loading allowing for UTF-8 errors with replacement: %s"
                    % (README_fname, exc_str(exc))
                )
                desc = open(README_fname, encoding="utf-8", errors="replace").read()

            meta['description'] = desc.strip()

        # special case
        if bids.get('BIDSVersion'):
            meta['conformsto'] = \
                'http://bids.neuroimaging.io/bids_spec{}.pdf'.format(
                    bids['BIDSVersion'].strip())
        else:
            meta['conformsto'] = 'http://bids.neuroimaging.io'
        meta['@context'] = vocabulary
        return meta

    def _get_content_metadata(self):
        participants_fname = opj(self.ds.path, 'participants.tsv')
        if exists(participants_fname):
            for r in yield_participant_info(participants_fname):
                yield r


def yield_participant_info(fname):
    with open(fname, 'rb') as tsvfile:
        # add robustness, use a sniffer
        try:
            dialect = csv.Sniffer().sniff(tsvfile.read(16384))
        except:
            lgr.warning('Could not determine file-format, assuming TSV')
            dialect = 'excel-tab'
        tsvfile.seek(0)
        for row in csv.DictReader(tsvfile, dialect=dialect):
            if 'participant_id' not in row:
                # not sure what this is, but we cannot use it
                break
            props = {}
            for k in row:
                # take away some ambiguity
                normk = k.lower()
                hk = content_metakey_map.get(normk, None)
                val = row[k]
                if hk is None:
                    hk = 'comment({})'.format(normk)
                elif hk == 'dlp_bids:sex':
                    val = sex_label_map.get(row[k].lower(), None)
                if val:
                    props[hk] = val
            if props:
                yield r'^{}/.*'.format(row['participant_id']), props
