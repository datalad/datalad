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
from os.path import join as opj, exists
from os.path import dirname
from importlib import import_module
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
    list(str)
      Metadata type labels or an empty list if no type setting is found and
      optional auto-detection yielded no results
    """
    cfg_ = ds.config
    # TODO give cfg name datalad prefix
    if cfg_ and cfg_.has_section('metadata'):
        if cfg_.has_option('metadata', 'nativetype'):
            return cfg_.get_value('metadata', 'nativetype').split()
    mtypes = []
    if guess:
        # keep local, who knows what some parsers might pull in
        from . import parsers
        for mtype in sorted([p for p in parsers.__dict__ if not (p.startswith('_') or p in ('tests', 'base'))]):
            if mtype == 'aggregate':
                # skip, runs anyway, but later
                continue
            pmod = import_module('.%s' % (mtype,), package=parsers.__package__)
            if pmod.MetadataParser(ds).has_metadata():
                lgr.debug('Predicted presence of "%s" meta data', mtype)
                mtypes.append(mtype)
            else:
                lgr.debug('No evidence for "%s" meta data', mtype)
    return mtypes


def _get_base_metadata_dict(identifier):
    """Return base metadata dictionary for any identifier
    """

    meta = {
        "@context": "http://schema.datalad.org/",
        # increment when changes to meta data representation are done
        "conformsTo": "http://docs.datalad.org/metadata.html#v0-2",
    }
    if identifier is not None:
        meta["@id"] = identifier
    return meta


def _is_versioned_dataset_item(m):
    return 'isVersionOf' in m and m.get('Type', None) == 'Dataset'


def _get_implicit_metadata(ds, identifier):
    meta = _get_base_metadata_dict(identifier)
    # maybe use something like git-describe instead -- but tag-references
    # might changes...
    meta['modified'] = ds.repo.repo.head.commit.authored_datetime.isoformat()

    if ds.id:
        # it has an ID, so we consider it a proper dataset
        meta['Type'] = "Dataset"
        meta['isVersionOf'] = {'@id': ds.id}

    annex_meta = _get_annex_metadata(ds.repo)
    if len(annex_meta):
        meta['availableFrom'] = [{'@id': m['@id']} for m in annex_meta]
    return meta


def _get_annex_metadata(repo):
    meta = []
    if not hasattr(repo, 'repo_info'):
        return meta
    # get all other annex ids, and filter out this one, origin and
    # non-specific remotes
    with swallow_logs():
        # swallow logs, because git annex complains about every remote
        # for which no UUID is configured -- many special remotes...
        repo_info = repo.repo_info(fast=True)
    for src in ('trusted repositories',
                'semitrusted repositories',
                'untrusted repositories'):
        for anx in repo_info.get(src, []):
            anxid = anx.get('uuid', '00000000-0000-0000-0000-0000000000')
            if anxid.startswith('00000000-0000-0000-0000-000000000'):
                # ignore special
                continue
            anx_meta = _get_base_metadata_dict(anxid)
            # TODO find a better type; define in context
            anx_meta['Type'] = 'Annex'
            if 'description' in anx:
                anx_meta['Description'] = anx['description']
            # XXX maybe report which one is local? Available in anx['here']
            # XXX maybe report the type of annex remote?
            meta.append(anx_meta)
    return meta


def _simplify_meta_data_structure(meta):
    # get a list of terms from any possible source
    if isinstance(meta, list) and len(meta) == 1:
        # simplify structure
        meta = meta[0]
    # XXX condition below is outdated (DOAP...), still needed?
    if isinstance(meta, dict) \
            and sorted(meta.keys()) == ['@context', '@graph'] \
            and meta.get('@context') == 'http://schema.datalad.org':
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


# XXX might become its own command
def get_metadata(ds, guess_type=False, ignore_subdatasets=False,
                 from_native=False):
    """Return a list of meta data items for the given dataset

    Parameters
    ----------
    ds : Dataset
      Dataset instance to query for meta data
    guess_type : bool
      Flag whether to make an attempt to guess the native meta data format
      if none is configured
    ignore_subdatasets : bool
      Flag whether to consider meta data for any potential subdatasets
    from_native : bool
      Flag whether to ignore any pre-processed meta data in the given dataset
      (except for those of subdatasets), and (re)read meta data from it native
      format(s). The success of reading from a native format depends on the
      local availability of the respective file(s). Meta data is read from
      native sources anyway when no pre-processed/aggregated meta data is
      available yet. Such meta data can be produced by the
      `aggregate_metadata` command.
    """
    if not ds.repo or not ds.repo.repo.head.is_valid():
        # not a single commit
        return []
    repo = ds.repo.repo
    ds_identifier = repo.head.commit.hexsha
    # where things are
    meta_path = opj(ds.path, metadata_basepath)
    main_meta_fname = opj(meta_path, metadata_filename)
    # metadata receptacle
    meta = []

    # from cache?
    if from_native or not exists(main_meta_fname):
        if ds.id:
            # create a separate item for the abstract (unversioned) dataset
            # just to say that this ID belongs to a dataset
            dm = _get_base_metadata_dict(ds.id)
            dm['Type'] = 'Dataset'
            meta.append(dm)
        # define known annexes by ID
        meta.extend(_get_annex_metadata(ds.repo))
        meta.append(_get_implicit_metadata(ds, ds_identifier))
        # and any native meta data
        meta.extend(
            get_native_metadata(
                ds,
                guess_type=guess_type,
                ds_identifier=ds_identifier))
    else:
        # from cache
        cached_meta = jsonload(main_meta_fname)
        if isinstance(cached_meta, list):
            meta.extend(cached_meta)
        else:
            meta.append(cached_meta)
        # cached meta data doesn't have proper version info for the top-level
        # dataset -> look for the item and update it
        for m in [i for i in meta if i.get('@id', None) == 'THISDATASET!']:
            if _is_versioned_dataset_item(m):
                m.update(_get_implicit_metadata(ds, ds_identifier))
            else:
                m['@id'] = ds_identifier

    if ignore_subdatasets:
        # all done now
        return meta

    from datalad.metadata.parsers.aggregate import MetadataParser as AggregateParser
    agg_parser = AggregateParser(ds)
    if agg_parser.has_metadata():
        agg_meta = agg_parser.get_metadata(ds_identifier)
        # try hard to keep things a simple non-nested list
        if isinstance(agg_meta, list):
            meta.extend(agg_meta)
        else:
            meta.append(agg_meta)

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
    return jsonld.flatten(obj, ctx={"@context": "http://schema.datalad.org/"})


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
        if nativetype == 'aggregate':
            # this is special and needs to be ignored here, even if it was
            # configured. reason: this parser runs anyway in get_metadata()
            continue
        pmod = import_module('.{}'.format(nativetype),
                             package=parsers.__package__)
        try:
            native_meta = pmod.MetadataParser(ds).get_metadata(ds_identifier)
        except Exception as e:
            lgr.error('failed to get native metadata ({}): {}'.format(nativetype, exc_str(e)))
            continue
        if native_meta:
            # TODO here we could apply a "patch" to the native metadata, if desired

            # try hard to keep things a simple non-nested list
            if isinstance(native_meta, list):
                meta.extend(native_meta)
            else:
                meta.append(native_meta)

    return meta
