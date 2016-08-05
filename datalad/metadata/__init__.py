# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata"""


import os
from os.path import join as opj
from importlib import import_module
from datalad.support.network import is_url
from .common import predicates, objects


# XXX Could become dataset method
def get_metadata_type(ds, guess=False):
    """Return the metadata type/scheme of a dataset

    Parameters
    ----------
    ds : Dataset
      Dataset instance to be inspected
    guess : bool
      Whether to try to auto-detect the type if no metadata type setting is
      found. All supported metadata schemes are tested in alphanumeric order.
      Only the label of the first matching scheme is reported.

    Returns
    -------
    str or None
      Metadata type label or `None` if no type setting is found and and optional
      auto-detection yielded no results
    """
    cfg = ds.config
    if cfg and cfg.has_section('metadata'):
        if cfg.has_option('metadata', 'nativetype'):
            return cfg.get_value('metadata', 'nativetype')
    if guess:
        # keep local, who knows what some parsers might pull in
        from . import parsers
        for mtype in sorted([p for p in parsers.__dict__ if not (p.startswith('_') or p == 'tests')]):
            pmod = import_module('.%s' % (mtype,), package=parsers.__package__)
            if pmod.has_metadata(ds):
                return mtype
    else:
        return None


# XXX Could become dataset method
def get_dataset_identifier(ds):
    """Returns some appropriate identifier for a dataset.

    Must be compliant with N-triples format, e.g. a blank node or a URI.
    """
    dsid = None
    if ds.repo:
        dsid = ds.repo.repo.config_reader().get_value(
            'annex', 'uuid', default=None)
        if dsid:
            dsid = 'http://db.datalad.org/ds/{}'.format(dsid)
        else:
            # not an annex
            dsid = '_:{}'.format(ds.repo.get_hexsha())
    else:
        # not even a VCS
        dsid = '_:{}'.format(ds.path.replace(os.sep, '_'))

    return dsid


def format_ntriples(triples):
    return '\n'.join(['{subject} {predicate} {object} .'.format(
        subject=autoformat_ntriple_element(sub),
        predicate=autoformat_ntriple_element(
            predicates[pred] if pred in predicates else pred),
        object=autoformat_ntriple_element(
            objects[obj] if obj in objects else obj))
        for sub, pred, obj in triples])


def autoformat_ntriple_element(val):
    if val.startswith('_:'):
        return val
    elif is_url(val):
        return '<{}>'.format(val)
    else:
        return '"{}"'.format(val)


def get_metadata(ds, guess_type=False):
    dsid = get_dataset_identifier(ds)

    triples = []
    if ds.is_installed():
        triples.append((dsid, '@type@', '@dataset@'))

    # get native metadata
    nativetype = get_metadata_type(ds, guess=guess_type)
    if not nativetype:
        return triples

    # keep local, who knows what some parsers might pull in
    from . import parsers
    pmod = import_module('.{}'.format(nativetype), package=parsers.__package__)
    triples.extend(pmod.get_metadata(ds))

    return triples
