# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Parser for friction-less data packages
(http://specs.frictionlessdata.io/data-packages)
"""

from os.path import exists, join as opj
from datalad.support.json_py import load as jsonload
from .. import _get_base_dataset_metadata

_metadata_fname = 'datapackage.json'


def has_metadata(ds):
    fname = opj(ds.path, _metadata_fname)
    try:
        return exists(fname) and 'name' in jsonload(fname)
    except:  # MIH: Some kind of JSONError?
        return False


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
        return obj.get('url', obj.get('type', obj))
    else:
        return obj


def get_metadata(ds, ds_identifier):
    """Extract metadata from a frictionless data package.

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
        raise ValueError(
            "no data package metadata found at {}".format(ds.path))

    foreign = jsonload(opj(ds.path, _metadata_fname))

    meta = _get_base_dataset_metadata(ds_identifier)

    for term in (
            'name', 'title', 'description', 'keywords', 'version',
            'homepage'):
        if term in foreign:
            meta[term] = foreign[term]
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

    meta['dcterms:conformsTo'] = [
        'http://specs.frictionlessdata.io/data-packages',
        'http://docs.datalad.org/metadata.html#v0-1']

    return meta
