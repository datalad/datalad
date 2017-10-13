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
import re
from six import PY2
if PY2:
    import cPickle as pickle
else:
    import pickle

from six import string_types
from os.path import join as opj, exists
from os.path import dirname
from importlib import import_module
from datalad.utils import swallow_logs
from datalad.utils import assure_dir
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


def _get_base_dataset_metadata(ds_identifier):
    """Return base metadata as dict for a given ds_identifier
    """

    meta = {
        "@context": {
            "@vocab": "http://schema.org/",
            "doap": "http://usefulinc.com/ns/doap#",
        },
        # increment when changes to meta data representation are done
        "dcterms:conformsTo": "http://docs.datalad.org/metadata.html#v0-1",
    }
    if ds_identifier is not None:
        meta["@id"] = ds_identifier
    return meta


def _get_implicit_metadata(ds, ds_identifier=None):
    """Convert git/git-annex info into metadata

    Anything that doesn't come as metadata in dataset **content**, but is
    encoded in the dataset repository itself. This does not include information
    on submodules, however. Meta data on subdatasets is provided by a dedicated
    parser implementation for "aggregate" meta data.

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

    if ds.id:
        # it has an ID, so we consider it a proper dataset
        meta['type'] = "Dataset"

    # shortcut
    repo = ds.repo.repo
    if repo.head.is_valid():
        meta['dcterms:modified'] = repo.head.commit.authored_datetime.isoformat()
        # maybe use something like git-describe instead -- but tag-references
        # might changes...
        meta['version'] = repo.head.commit.hexsha
    _add_annex_metadata(ds.repo, meta)
    return meta


def _sanitize_annex_description(desc):
    """Sanitize annex description of the remote

    Should not depict name of the local remote (enabled if within [])
    or status (e.g. [datalad-archives] would be for enabled datalad-archives)

    Assumption is that no [ or ] used within remote name, which is hopefully
    a safe one
    """
    # [datalad-archives] -> datalad-archives
    desc = re.sub('^\[(.*)\]$', r'\1', desc)
    # some description [local-remote] -> some description
    desc = re.sub('^(.*) \[.*\]$', r'\1', desc)
    return desc


def _add_annex_metadata(repo, meta):
    # look for known remote annexes, doesn't need configured
    # remote to be meaningful
    # need annex repo instance
    # TODO refactor to use ds.uuid when #701 is addressed
    if hasattr(repo, 'repo_info'):
        # get all other annex ids, and filter out this one, origin and
        # non-specific remotes
        with swallow_logs():
            # swallow logs, because git annex complains about every remote
            # for which no UUID is configured -- many special remotes...
            repo_info = repo.repo_info(fast=True)
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
                    anx_meta['description'] = \
                        _sanitize_annex_description(anx['description'])
                # XXX maybe report which one is local? Available in anx['here']
                # XXX maybe report the type of annex remote?
                annex_meta.append(anx_meta)
        if len(annex_meta) == 1:
            annex_meta = annex_meta[0]
        meta['availableFrom'] = annex_meta


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
    # XXX condition below is outdated (DOAP...), still needed?
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

    # from cache?
    if ignore_cache or not exists(main_meta_fname):
        # start with the implicit meta data, currently there is no cache for
        # this type of meta data, as it will change with every clone.
        # In contrast, native meta data is cached.
        implicit_meta = _get_implicit_metadata(ds, ds_identifier)
        meta.append(implicit_meta)
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
        # cached meta data doesn't have version info for the top-level
        # dataset -> look for the item and update it
        for m in meta:
            if not is_implicit_metadata(m):
                continue
            if m.get('@id', None) == ds_identifier:
                m.update(_get_implicit_metadata(ds, ds_identifier))
                break

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
    from datalad.support.network import get_cached_url_content
    from pyld.jsonld import load_document
    return get_cached_url_content(
        url, name='schema', fetcher=load_document, maxage=1
    )


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
