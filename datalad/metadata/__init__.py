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
from six import PY2
if PY2:
    import cPickle as pickle
else:
    import pickle
from hashlib import md5
from six.moves.urllib.parse import urlsplit
from six import string_types
from os.path import join as opj, exists, relpath
from os.path import dirname
from importlib import import_module
from datalad.distribution.dataset import Dataset
from datalad.utils import swallow_logs
from datalad.utils import assure_dir
from datalad.support.json_py import load as jsonload
from datalad.dochelpers import exc_str
from datalad.log import lgr
from datalad import cfg


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
    cfg_ = ds.config
    if cfg_ and cfg_.has_section('metadata'):
        if cfg_.has_option('metadata', 'nativetype'):
            return cfg_.get_value('metadata', 'nativetype').split()
    mtypes = []
    if guess:
        # keep local, who knows what some parsers might pull in
        from . import parsers
        for mtype in sorted([p for p in parsers.__dict__ if not (p.startswith('_') or p in ('tests', 'base'))]):
            pmod = import_module('.%s' % (mtype,), package=parsers.__package__)
            if pmod.MetadataParser(ds).has_metadata():
                mtypes.append(mtype)
    return mtypes if len(mtypes) else None


def _get_base_dataset_metadata(ds_identifier):
    """Return base metadata as dict for a given ds_identifier
    """

    meta = {
        "@context": "http://schema.org/",
        "type": "Dataset",
        # increment when changes to meta data representation are done
        "dcterms:conformsTo": "http://docs.datalad.org/metadata.html#v0-1",
    }
    if ds_identifier is not None:
        meta["@id"] = ds_identifier
    return meta


def _get_implicit_metadata(ds, ds_identifier=None, subdatasets=None):
    """Convert git/git-annex info into metadata

    Anything that doesn't come as metadata in dataset **content**, but is
    encoded in the dataset repository itself.

    Returns
    -------
    dict
    """
    if ds_identifier is None:
        ds_identifier = ds.id
    if subdatasets is None:
        subdatasets = []

    meta = _get_base_dataset_metadata(ds_identifier)

    if not ds.repo:
        # everything else comes from a repo
        return meta

    # shortcut
    repo = ds.repo.repo
    if repo.head.is_valid():
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
            repo_info = ds.repo.repo_info(fast=True)
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
    for subds in subdatasets:
        submeta = {
            'location': relpath(subds.path, ds.path),
            'type': 'Dataset'}
        if subds.id:
            submeta['@id'] = subds.id
        subdss.append(submeta)
    if len(subdss):
        if len(subdss) == 1:
            subdss = subdss[0]
        meta['dcterms:hasPart'] = subdss

    return meta


def is_implicit_metadata(meta):
    """Return whether a meta data set looks like our own implicit meta data"""
    std_spec = meta.get('dcterms:conformsTo', '')
    return isinstance(std_spec, string_types) \
        and std_spec.startswith('http://docs.datalad.org/metadata.html#v')


def _simplify_meta_data_structure(meta):
    # get a list of terms from any possible source
    if isinstance(meta, list) and len(meta) == 1:
        # simplify structure
        meta = meta[0]
    if isinstance(meta, dict) \
            and sorted(meta.keys()) == ['@context', '@graph'] \
            and meta.get('@context') == 'http://schema.org/':
        meta = meta['@graph']
    elif isinstance(meta, dict):
        meta = [meta]
    elif isinstance(meta, list):
        # list this possibility explicitely to get 'else' to indicate that
        # we hit something unforseen
        pass
    else:
        raise NotImplementedError(
            'got some unforseens meta data structure')
    return meta


def _adjust_subdataset_location(meta, subds_relpath):
    # find implicit meta data for all contained subdatasets
    for m in meta:
        # skip non-implicit
        if not is_implicit_metadata(m):
            continue
        # prefix all subdataset location information with the relpath of this
        # subdataset
        if 'dcterms:hasPart' in m:
            parts = m['dcterms:hasPart']
            if not isinstance(parts, list):
                parts = [parts]
            for p in parts:
                if 'location' not in p:
                    continue
                loc = p.get('location', subds_relpath)
                if loc != subds_relpath:
                    p['location'] = opj(subds_relpath, loc)


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

    # pregenerate Dataset objects for all relevants subdataset
    # needed to get consistent IDs across the entire meta data graph
    # we need these, even if we `ignore_subdatasets`, as we still want
    # to list the parts of this dataset, even without additional meta data
    # about it
    subdss = [Dataset(opj(ds.path, p)) for p in ds.get_subdatasets(recursive=False)]
    # start with the implicit meta data, currently there is no cache for
    # this type of meta data, as it will change with every clone.
    # In contrast, native meta data is cached.
    implicit_meta = _get_implicit_metadata(
        ds, ds_identifier, subdatasets=subdss)
    # create a lookup dict to find parts by subdataset mountpoint
    has_part = implicit_meta.get('dcterms:hasPart', [])
    if not isinstance(has_part, list):
        has_part = [has_part]
    has_part = {hp['location']: hp for hp in has_part}

    meta.append(implicit_meta)

    # from cache?
    if ignore_cache or not exists(main_meta_fname):
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

    if ignore_subdatasets:
        # all done now
        return meta

    # for any subdataset that is actually registered (avoiding stale copies)
    for subds in subdss:
        subds_path = relpath(subds.path, ds.path)
        if ignore_cache and subds.is_installed():
            # simply pull meta data from actual subdataset and go to next part
            subds_meta = get_metadata(
                subds, guess_type=guess_type,
                ignore_subdatasets=False,
                ignore_cache=True)
            _adjust_subdataset_location(subds_meta, subds_path)
            meta.extend(subds_meta)
            continue

        # we need to look for any aggregated meta data
        subds_meta_fname = opj(meta_path, subds_path, metadata_filename)
        if not exists(subds_meta_fname):
            # nothing -> skip
            lgr.info(
                'no cached meta data for subdataset at {}, ignoring'.format(
                    subds_path))
            continue

        # load aggregated meta data
        subds_meta = jsonload(subds_meta_fname)
        # we cannot simply append, or we get weired nested graphs
        # proper way would be to expand the JSON-LD, extend the list and
        # compact/flatten at the end. However assuming a single context
        # we can cheat.
        subds_meta = _simplify_meta_data_structure(subds_meta)
        _adjust_subdataset_location(subds_meta, subds_path)

        # make sure we have a meaningful @id for any subdataset in hasPart,
        # regardless of whether it is installed or not. This is needed to
        # be able to connect super and subdatasets in the graph of a new clone
        # we a new UUID
        if not subds.is_installed():
            # the ID for this one is not identical to the one referenced
            # in the aggregated meta -> sift through all meta data sets
            # look for a meta data set that knows about being part
            # of this dataset, so we can use its @id
            for md in subds_meta:
                cand_id = md.get('dcterms:isPartOf', None)
                if cand_id == ds_identifier and '@id' in md:
                    has_part[subds_path]['@id'] = md['@id']
                    break

        # hand over subdataset meta data
        meta.extend(subds_meta)

    # reassign modified 'hasPart; term
    parts = list(has_part.values())
    if len(parts) == 1:
        parts = parts[0]
    if len(parts):
        implicit_meta['dcterms:hasPart'] = parts

    return meta


def _cached_load_document(url):
    """Loader of pyld document from a url, which caches loaded instance on disk
    """
    doc_fname = _get_schema_url_cache_filename(url)

    doc = None
    if os.path.exists(doc_fname):
        try:
            lgr.debug("use cached request result to '%s' from %s", url, doc_fname)
            doc = pickle.load(open(doc_fname, 'rb'))
        except Exception as e:  # it is OK to ignore any error and fall back on the true source
            lgr.warning(
                "cannot load cache from '%s', fall back on schema download: %s",
                doc_fname, exc_str(e))

    if doc is None:
        from pyld.jsonld import load_document
        doc = load_document(url)
        assure_dir(dirname(doc_fname))
        # use pickle to store the entire request result dict
        pickle.dump(doc, open(doc_fname, 'wb'))
        lgr.debug("stored result of request to '{}' in {}".format(url, doc_fname))
    return doc


def _get_schema_url_cache_filename(url):
    """Return a filename where to cache schema doc from a url"""
    cache_dir = opj(cfg.obtain('datalad.locations.cache'), 'schema')
    doc_fname = opj(
        cache_dir,
        '{}-{}.p{}'.format(
            urlsplit(url).netloc,
            md5(url.encode('utf-8')).hexdigest(),
            pickle.HIGHEST_PROTOCOL)
    )
    return doc_fname


def flatten_metadata_graph(obj):
    from pyld import jsonld
    # simplify graph into a sequence of one dict per known dataset, even
    # if multiple meta data set from different sources exist for the same
    # dataset.

    # cache schema requests; this also avoid the need for network access
    # for previously "visited" schemas
    jsonld.set_document_loader(_cached_load_document)
    # TODO cache entire graphs to prevent repeated term resolution for
    # subsequent calls
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
            native_meta = pmod.MetadataParser(ds).get_metadata(ds_identifier)
        except Exception as e:
            lgr.error('failed to get native metadata ({}): {}'.format(nativetype, exc_str(e)))
            continue
        # TODO here we could apply a "patch" to the native metadata, if desired
        meta.append(native_meta)

    return meta
