# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata"""


from git.config import GitConfigParser
from os.path import join as opj
from datalad.support.network import is_url

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
    cfg = GitConfigParser(opj(ds.path, '.datalad', 'config'),
                          read_only=True)
    if cfg.has_section('metadata'):
        return cfg.get_value('metadata', 'type', default=None)
    if guess:
        from . import parsers
        from importlib import import_module
        for mtype in sorted([p for p in parsers.__dict__ if not p.startswith('_')]):
            pmod = import_module('.%s' % (mtype,), package=parsers.__package__)
            if pmod.has_metadata(ds):
                return mtype
    else:
        return None


def get_dataset_identifier(ds):
    """Returns some appropriate identifier for a dataset.

    Must be compliant with N-triples format, e.g. a blank node or a URI.
    """
    return '_:dsid_placeholder'


def format_ntriples(triples):
    return '\n'.join(['{subject} {predicate} {object} .'.format(
        subject=t[0], predicate=t[1], object=t[2]) for t in triples])


def autoformat_ntriple_element(val):
    return '<{}>'.format(val) if is_url(val) else '"{}"'.format(val)
