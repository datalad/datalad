# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""BIDS metadata parser (http://bids.neuroimaging.io)"""

from os.path import exists, join as opj
import json
from .. import get_dataset_identifier
from ..common import predicates, objects

def has_metadata(ds):
    return exists(opj(ds.path, 'dataset_description.json'))


def get_metadata(ds):
    """Extract metadata from BIDS datasets.

    Parameters
    ----------
    ds : dataset instance
      Dataset to extract metadata from.

    Returns
    -------
    list
      List of 3-tuples with subject, predicate, and object
    """
    if not has_metadata(ds):
        raise ValueError("no BIDS metadata found at {}".format(ds.path))

    bids = json.load(open(opj(ds.path, 'dataset_description.json')))
    dsid = get_dataset_identifier(ds)

    triples = []
    # common cases
    for bidsterm, dataladterm in (('Name', '@name@'),
                                  ('License', '@license@'),
                                  ('Funding', '@fundedby@'),
                                  ('Description', '@description@')):
        if bidsterm in bids:
            triples.append((dsid, dataladterm, bids[bidsterm]))
    # special case handling
    if 'BIDSVersion' in bids:
        triples.append((dsid, '@conformsto@',
                        'BIDS %s' % (bids['BIDSVersion'],)))
    if 'Authors' in bids:
        for author in bids['Authors']:
            triples.append((dsid, '@contributor@', author))
    if 'ReferencesAndLinks' in bids:
        for ref in bids['ReferencesAndLinks']:
            triples.append((dsid, '@citation@',
                            ref))
    # TODO maybe normalize labels of standard licenses to definition URIs
    return triples
