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
from datalad.support.json import load as jsonload
from .. import _get_base_dataset_metadata

# XXX Could become a class attribute
_metadata_fname = 'dataset_description.json'


# XXX Could become a class method
def has_metadata(ds):
    return exists(opj(ds.path, _metadata_fname))


# XXX Could become a class method
# XXX consider RFing into get_metadata(ds) and then centrally updating base_metadata
#     with returned meta, or do we foresee some meta without that base?
def get_metadata(ds, ds_identifier):
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

    bids = jsonload(opj(ds.path, _metadata_fname))

    meta = _get_base_dataset_metadata(ds_identifier)

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
