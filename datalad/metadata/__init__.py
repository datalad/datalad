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
import json
from os.path import join as opj, exists
from importlib import import_module
from datalad.distribution.dataset import Dataset
from datalad.utils import swallow_logs
from ..log import lgr


# common format
metadata_filename = 'meta.json'
metadata_basepath = opj('.datalad', 'meta')
# TODO think about minimizing the JSON output by default
json_dump_kwargs = dict(indent=2, sort_keys=True, ensure_ascii=False)


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
        with swallow_logs():
            # swallow logs, because git annex complains about every remote
            # for which no UUID is configured -- many special remotes...
            repo_info = ds.repo.repo_info()
        sibling_uuids = [
            # flatten list
            item for repolist in
            # extract uuids of all listed repos
            [[r['uuid'] for r in repo_info[i] if 'uuid' in r]
                # loop over trusted, semi and untrusted
                for i in repo_info
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
        # we only want immediate subdatasets
        for subds_path in ds.get_subdatasets(recursive=False):
            subds = Dataset(opj(ds.path, subds_path))
            subds_id = get_dataset_identifier(subds)
            submeta = {
                'location': subds_path,
                'type': 'Dataset'}
            if not subds_id.startswith('_:'):
                submeta['@id'] = subds_id
            subdss.append(submeta)
        if len(subdss):
            if len(subdss) == 1:
                subdss = subdss[0]
            meta['dcterms:hasPart'] = subdss

    return meta


# XXX might become its own command
def get_metadata(ds, guess_type=False, ignore_subdatasets=False,
                 ignore_cache=False, optimize=False):
    meta = []
    # where things are
    meta_path = opj(ds.path, metadata_basepath)
    main_meta_fname = opj(meta_path, metadata_filename)
    # from cache?
    if ignore_cache or not exists(main_meta_fname):
        if not ignore_cache:
            lgr.info('no extracted meta data available for {}, use ``aggregate_metadata`` command to avoid slow operation'.format(ds))
        meta.extend(extract_metadata(ds, guess_type=guess_type))
    else:
        cached_meta = json.load(open(main_meta_fname, 'rb'))
        if isinstance(cached_meta, list):
            meta.extend(cached_meta)
        else:
            meta.append(cached_meta)
    # for any subdataset that is actually registered (avoiding stale copies)
    if not ignore_subdatasets:
        for subds_path in ds.get_subdatasets(recursive=False):
            subds_meta_fname = opj(meta_path, subds_path, metadata_filename)
            if exists(subds_meta_fname):
                subds_meta = json.load(open(subds_meta_fname, 'rb'))
                # we cannot simply append, or we get weired nested graphs
                # proper way would be to expand the JSON-LD, extend the list and
                # compact/flatten at the end. However assuming a single context
                # we can cheat:
                # TODO: better detect when we need to fall back to a proper
                # graph merge via jsonld
                if isinstance(subds_meta, list) and len(subds_meta) == 1:
                    # simplify structure
                    subds_meta = subds_meta[0]
                if isinstance(subds_meta, dict) \
                        and sorted(subds_meta.keys()) == ['@context', '@graph'] \
                        and subds_meta.get('@context') == 'http://schema.org/':
                    meta.extend(subds_meta['@graph'])
                elif isinstance(subds_meta, list):
                    meta.extend(subds_meta)
                elif isinstance(subds_meta, dict):
                    meta.append(subds_meta)
                else:
                    raise NotImplementedError(
                        'got some unforseens meta data structure')
            else:
                lgr.info(
                    'no cached meta data for subdataset at {}, ignoring'.format(
                        subds_path))
    if optimize:
        try:
            from pyld import jsonld
        except ImportError:
            raise ImportError(
                'meta data flattening requested, but pyld is not available')
        try:
            meta = flatten_metadata_graph(meta)
        except jsonld.JsonLdError as e:
            # unfortunately everything gets swallowed into the same exception
            lgr.error('meta data graph simplification failed, no network?')
            raise e
    return meta


def flatten_metadata_graph(obj):
    from pyld import jsonld
    # simplify graph into a sequence of one dict per known dataset, even
    # if multiple meta data set from different sources exist for the same
    # dataset.

    # TODO specify custom/caching document loader in options to speed
    # up term resolution for subsequent calls
    return jsonld.flatten(obj, ctx={"@context": "http://schema.org/"})


def extract_metadata(ds, guess_type=False):
    """Parse a dataset to gather metadata

    Returns
    -------
    List
        Each item in the list is a metadata dictionary (JSON-LD compliant).
        The first items corresponds to the annex-based metadata of the dataset.
        The last items contains the native metadata of the dataset content. Any
        additional items correspond to subdataset metadata sets.
    """
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
        return meta

    # keep local, who knows what some parsers might pull in
    from . import parsers
    pmod = import_module('.{}'.format(nativetype), package=parsers.__package__)
    native_meta = pmod.get_metadata(ds, ds_identifier)
    # TODO here we could apply a "patch" to the native metadata, if desired
    meta.append(native_meta)

    return meta
