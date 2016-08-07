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


def get_metadata(ds, identifier):
    """Extract metadata from BIDS datasets.

    Parameters
    ----------
    ds : dataset instance
      Dataset to extract metadata from.

    Returns
    -------
    dict
      JSON-LD compliant
    """
    if not has_metadata(ds):
        raise ValueError("no BIDS metadata found at {}".format(ds.path))

    bids = json.load(open(opj(ds.path, 'dataset_description.json')))

    meta = {
        "@context": "http://schema.org/",
        "@id": identifier,
    }

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
    # special case
    if 'BIDSVersion' in bids:
        meta['dcterms:conformsTo'] = 'BIDS {}'.format(bids['BIDSVersion'])
    return meta
