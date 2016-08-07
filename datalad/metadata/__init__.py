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
from importlib import import_module
from datalad.distribution.dataset import Dataset
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

    Any non-annex UUID identifier is prefixed for '_:'
    """
    dsid = None
    if ds.repo:
        dsid = ds.repo.repo.config_reader().get_value(
            'annex', 'uuid', default='')
        if not dsid:
            # not an annex
            dsid = '_:{}'.format(ds.repo.get_hexsha())
    else:
        # not even a VCS
        dsid = '_:{}'.format(ds.path.replace(os.sep, '_'))

    return dsid


def _get_implicit_metadata(ds, ds_identifier):
    """Convert git/git-annex info into metadata

    Anything that doesn't come as metadata in dataset **content**, but is
    encoded in the dataset repository itself.
    """
    meta = {
        "@context": "http://schema.org/",
        "@id": ds_identifier,
    }

    # whenever we have a full dataset, give it a type
    if ds.is_installed():
        meta['type'] = 'Dataset'

    # look for known remote annexes, doesn't need configured
    # remote to be meaningful
    # need annex repo instance
    if ds.repo and hasattr(ds.repo, 'repo_info'):
        ds_uuid = ds.repo.repo.config_reader().get_value(
            'annex', 'uuid', default='')
        # retrieve possibly stored origin uuid and list in meta data
        origin_uuid = ''
        if ds.config:
            origin_uuid = ds.config.get_value(
                'annex', 'origin', default='')
            if origin_uuid and ds_uuid != origin_uuid:
                meta['dcterms:isVersionOf'] = {'@id': origin_uuid}

        # get all other annex ids, and filter out this one, origin and
        # non-specific remotes
        sibling_uuids = [
            # flatten list
            item for repolist in
            # extract uuids of all listed repos
            [[r['uuid'] for r in ds.repo.repo_info()[i] if 'uuid' in r]
                # loop over trusted, semi and untrusted
                for i in ds.repo.repo_info()
                if i.endswith('trusted repositories')]
            for item in repolist
            # filter out special ones
            if not item.startswith('00000000-0000-0000-0000-0000000000')
            # and the present one too
            and not item == ds_uuid
            and not item == origin_uuid]
        if len(sibling_uuids):
            version_meta = [{'@id': sibling} for sibling in sibling_uuids]
            if len(version_meta) == 1:
                version_meta = version_meta[0]
            meta['dcterms:hasVersion'] = version_meta

        ## metadata on all subdataset
        subdss = []
        for subds_path in ds.get_subdatasets(recursive=True):
            subds = Dataset(subds_path)
            subds_id = get_dataset_identifier(subds)
            if subds_id.startswith('_:'):
                subdss.append(subds_id)
            else:
                subdss.append({'@id': subds_id})
        if len(subdss):
            if len(subdss) == 1:
                subdss = subdss[0]
            meta['dcterms:hasPart'] = subdss

    return meta


def get_metadata(ds, guess_type=False):
    # TODO handle retrieval of subdataset metadata:
    #      from scratch vs cached
    ds_identifier = get_dataset_identifier(ds)

    # using a list, because we could get multiple sets of meta data per
    # dataset, and we want to quickly collect them without having to do potentially
    # complex graph merges
    meta = []
    meta.append(_get_implicit_metadata(ds, ds_identifier))

    # get native metadata
    nativetype = get_metadata_type(ds, guess=guess_type)
    if not nativetype:
        # compact value
        if len(meta) == 1:
            meta = meta[0]
        return meta

    # keep local, who knows what some parsers might pull in
    from . import parsers
    pmod = import_module('.{}'.format(nativetype), package=parsers.__package__)
    native_meta = pmod.get_metadata(ds, ds_identifier)
    # TODO here we could apply a "patch" to the native metadata, if desired
    meta.append(native_meta)

    # compact value
    if len(meta) == 1:
        meta = meta[0]
    return meta
