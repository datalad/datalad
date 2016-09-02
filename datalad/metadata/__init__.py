# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata handling (parsing, storing, querying)"""


import os
from os.path import join as opj, exists
from importlib import import_module
from datalad.distribution.dataset import Dataset
from datalad.utils import swallow_logs
from ..log import lgr
from datalad.support.json_py import load as jsonload
from datalad.dochelpers import exc_str
from datalad.log import lgr

# common format
metadata_filename = 'meta.json'
metadata_basepath = opj('.datalad', 'meta')


# XXX Could become dataset method
def get_metadata_type(ds, guess=False):
    """Return the metadata type(s)/scheme(s) of a dataset

    Parameters
    ----------
    ds : Dataset
      Dataset instance to be inspected
    guess : bool
      Whether to try to auto-detect the type if no metadata type setting is
      found. All supported metadata schemes are tested in alphanumeric order.

    Returns
    -------
    list(str) or None
      Metadata type labels or `None` if no type setting is found and and
      optional auto-detection yielded no results
    """
    cfg = ds.config
    if cfg and cfg.has_section('metadata'):
        if cfg.has_option('metadata', 'nativetype'):
            return cfg.get_value('metadata', 'nativetype').split()
    mtypes = []
    if guess:
        # keep local, who knows what some parsers might pull in
        from . import parsers
        for mtype in sorted([p for p in parsers.__dict__ if not (p.startswith('_') or p == 'tests')]):
            pmod = import_module('.%s' % (mtype,), package=parsers.__package__)
            if pmod.has_metadata(ds):
                mtypes.append(mtype)
    return mtypes if len(mtypes) else None


def _get_base_dataset_metadata(ds_identifier):
    """Return base metadata as dict for a given ds_identifier
    """

    return {
        "@context": "http://schema.org/",
        "@id": ds_identifier,
        "type": "Dataset",
    }


def get_implicit_metadata(ds, ds_identifier=None):
    """Convert git/git-annex info into metadata

    Anything that doesn't come as metadata in dataset **content**, but is
    encoded in the dataset repository itself.

    Returns
    -------
    dict
    """
    if ds_identifier is None:
        ds_identifier = ds.id

    meta = _get_base_dataset_metadata(ds_identifier)

    if not ds.repo:
        # everything else comes from a repo
        return meta

    # shortcut
    repo = ds.repo.repo
    if repo.head.reference.is_valid():
        meta['dcterms:modified'] = repo.head.commit.authored_datetime.isoformat()
        # maybe use something like git-describe instead -- but tag-references
        # might changes...
        meta['version'] = repo.head.commit.hexsha

    # look for known remote annexes, doesn't need configured
    # remote to be meaningful
    # need annex repo instance
    # TODO refactor to use ds.uuid when #701 is addressed
    if hasattr(ds.repo, 'repo_info'):
        # get all other annex ids, and filter out this one, origin and
        # non-specific remotes
        with swallow_logs():
            # swallow logs, because git annex complains about every remote
            # for which no UUID is configured -- many special remotes...
            repo_info = ds.repo.repo_info()
        annex_meta = []
        for src in ('trusted repositories',
                    'semitrusted repositories',
                    'untrusted repositories'):
            for anx in repo_info.get(src, []):
                anxid = anx.get('uuid', '00000000-0000-0000-0000-0000000000')
                if anxid.startswith('00000000-0000-0000-0000-000000000'):
                    # ignore special
                    continue
                anx_meta = {'@id': anxid}
                if 'description' in anx:
                    anx_meta['description'] = anx['description']
                # XXX maybe report which one is local? Available in anx['here']
                # XXX maybe report the type of annex remote?
                annex_meta.append(anx_meta)
            if len(annex_meta) == 1:
                annex_meta = annex_meta[0]
            meta['availableFrom'] = annex_meta

    ## metadata on all subdataset
    subdss = []
    # we only want immediate subdatasets
    for subds_path in ds.get_subdatasets(recursive=False):
        subds = Dataset(opj(ds.path, subds_path))
        subds_id = subds.id
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


def _get_version_ids_from_implicit_meta(meta):
    # figure out all other version of this dataset: origin or siblings
    # build a flat list of UUIDs
    hv = meta.get('dcterms:hasVersion', [])
    if isinstance(hv, dict):
        hv = [hv]
    versions = set([v['@id'] for v in hv if '@id' in v])
    iv = meta.get('prov:wasDerivedFrom', {})
    if '@id' in iv:
        versions = versions.union([iv['@id']])
    return versions


# XXX might become its own command
def get_metadata(ds, guess_type=False, ignore_subdatasets=False,
                 ignore_cache=False):
    # common identifier
    ds_identifier = ds.id
    # metadata receptacle
    meta = []
    # where things are
    meta_path = opj(ds.path, metadata_basepath)
    main_meta_fname = opj(meta_path, metadata_filename)

    # start with the implicit meta data, currently there is no cache for
    # this type of meta data, as it will change with every clone.
    # In contrast, native meta data is cached, although the UUIDs in it will
    # not necessarily match this clone. However, this clone should have a
    # 'hasVersion' meta data item that lists the respective UUID, and consequently
    # we know which clone was used to extract/cache the meta data
    # XXX it may be worth the put the combined output of this function in a separate
    # cache on the local machine, in order to speed up meta data access, but maybe this
    # is already the domain of a `query` implementation
    implicit_meta = get_implicit_metadata(ds, ds_identifier)
    # create a lookup dict to find parts by subdataset mountpoint
    has_part = implicit_meta.get('dcterms:hasPart', [])
    if not isinstance(has_part, list):
        has_part = [has_part]
    has_part = {hp['location']: hp for hp in has_part}

    # XXX this logic is flawed
    #ds_versions = _get_version_ids_from_implicit_meta(implicit_meta)
    meta.append(implicit_meta)

    # from cache?
    if ignore_cache or not exists(main_meta_fname):
        if not ignore_cache:
            lgr.info('no extracted native meta data available for {}, use the ``aggregate_metadata`` command to avoid slow operation'.format(ds))
        meta.extend(
            get_native_metadata(
                ds,
                guess_type=guess_type,
                ds_identifier=ds_identifier))
    else:
        cached_meta = jsonload(main_meta_fname)
        if isinstance(cached_meta, list):
            meta.extend(cached_meta)
        else:
            meta.append(cached_meta)
    # for any subdataset that is actually registered (avoiding stale copies)
    if not ignore_subdatasets:
        for subds_path in ds.get_subdatasets(recursive=False):
            subds = Dataset(opj(ds.path, subds_path))
            if ignore_cache and subds.is_installed():
                meta.extend(
                    get_metadata(subds, guess_type=guess_type,
                                 ignore_subdatasets=False,
                                 ignore_cache=True))
            else:
                subds_meta_fname = opj(meta_path, subds_path, metadata_filename)
                if exists(subds_meta_fname):
                    subds_meta = jsonload(subds_meta_fname)
                    # we cannot simply append, or we get weired nested graphs
                    # proper way would be to expand the JSON-LD, extend the list and
                    # compact/flatten at the end. However assuming a single context
                    # we can cheat.
                    # get a list of terms from any possible source
                    if isinstance(subds_meta, list) and len(subds_meta) == 1:
                        # simplify structure
                        subds_meta = subds_meta[0]
                    if isinstance(subds_meta, dict) \
                            and sorted(subds_meta.keys()) == ['@context', '@graph'] \
                            and subds_meta.get('@context') == 'http://schema.org/':
                        subds_meta = subds_meta['@graph']
                    elif isinstance(subds_meta, dict):
                        subds_meta = [subds_meta]
                    elif isinstance(subds_meta, list):
                        # list this possibility explicitely to get 'else' to indicate that
                        # we hit something unforseen
                        pass
                    else:
                        raise NotImplementedError(
                            'got some unforseens meta data structure')
                    # make sure we have a meaningful @id for any subdataset in hasPart,
                    # regardless of whether it is installed or not. This is needed to
                    # be able to connect super and subdatasets in the graph of a new clone
                    # we a new UUID
                    if not '@id' in has_part[subds_path]:
                        # this must be an uninstalled subdataset
                        # look for a meta data set that knows about being part of any
                        # sibling of this dataset, so we can use its @id
                        for md in subds_meta:
                            cand_id = md.get('dcterms:isPartOf', None)
                            if cand_id in ds_versions and '@id' in md:
                                has_part[subds_path]['@id'] = md['@id']
                                break

                    # hand over subdataset meta data
                    meta.extend(subds_meta)
                else:
                    lgr.info(
                        'no cached meta data for subdataset at {}, ignoring'.format(
                            subds_path))
        # reassign modified 'hasPart; term
        parts = list(has_part.values())
        if len(parts) == 1:
            parts = parts[0]
        if len(parts):
            implicit_meta['dcterms:hasPart'] = parts

    return meta


def flatten_metadata_graph(obj):
    from pyld import jsonld
    # simplify graph into a sequence of one dict per known dataset, even
    # if multiple meta data set from different sources exist for the same
    # dataset.

    # TODO specify custom/caching document loader in options to speed
    # up term resolution for subsequent calls
    return jsonld.flatten(obj, ctx={"@context": "http://schema.org/"})


def get_native_metadata(ds, guess_type=False, ds_identifier=None):
    """Parse a dataset to gather its native metadata

    Returns
    -------
    List
        Each item in the list is a metadata dictionary (JSON-LD compliant).
        The first items corresponds to the annex-based metadata of the dataset.
        The last items contains the native metadata of the dataset content. Any
        additional items correspond to subdataset metadata sets.
    """
    if ds_identifier is None:
        ds_identifier = ds.id
    # using a list, because we could get multiple sets of meta data per
    # dataset, and we want to quickly collect them without having to do potentially
    # complex graph merges
    meta = []
    # get native metadata
    nativetypes = get_metadata_type(ds, guess=guess_type)
    if not nativetypes:
        return meta

    # keep local, who knows what some parsers might pull in
    from . import parsers
    for nativetype in nativetypes:
        pmod = import_module('.{}'.format(nativetype),
                             package=parsers.__package__)
        try:
            native_meta = pmod.get_metadata(ds, ds_identifier)
        except Exception as e:
            lgr.error('failed to get native metadata ({}): {}'.format(nativetype, exc_str(e)))
            continue
        # TODO here we could apply a "patch" to the native metadata, if desired
        meta.append(native_meta)

    return meta
