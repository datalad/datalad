# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Set and query metadata of datasets and their components"""

__docformat__ = 'restructuredtext'


import logging
import re
import os
from os import makedirs
from os.path import dirname
from os.path import relpath
from os.path import normpath
from os.path import curdir
from os.path import exists
from os.path import join as opj
from importlib import import_module
from collections import OrderedDict
from six import binary_type, string_types

from datalad import cfg
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.base import Interface
from datalad.interface.save import Save
from datalad.interface.results import get_status_dict
from datalad.interface.results import success_status_map
from datalad.interface.results import annexjson2result
from datalad.interface.results import results_from_annex_noinfo
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.metadata.definitions import common_defs
from datalad.metadata.definitions import version as vocabulary_version
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureBool
from datalad.support.constraints import EnsureStr
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
import datalad.support.ansi_colors as ac
from datalad.support.json_py import dump as jsondump
from datalad.support.json_py import load as jsonload
from datalad.support.json_py import load_xzstream
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import merge_native_opt
from datalad.interface.common_opts import reporton_opt
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.utils import unique
from datalad.utils import assure_list
from datalad.utils import with_pathsep as _with_sep
from datalad.ui import ui
from datalad.dochelpers import exc_str
from datalad.dochelpers import single_or_plural


lgr = logging.getLogger('datalad.metadata.metadata')

valid_key = re.compile(r'^[0-9a-z._-]+$')

db_relpath = opj('.datalad', 'metadata', 'dataset.json')
agginfo_relpath = opj('.datalad', 'metadata', 'aggregate.json')

# relative paths which to exclude from any metadata processing
# including anything underneath them
exclude_from_metadata = ('.datalad', '.git', '.gitmodules', '.gitattributes')


def get_metadata_type(ds):
    """Return the metadata type(s)/scheme(s) of a dataset

    Parameters
    ----------
    ds : Dataset
      Dataset instance to be inspected

    Returns
    -------
    list(str)
      Metadata type labels or an empty list if no type setting is found and
      optional auto-detection yielded no results
    """
    cfg_key = 'datalad.metadata.nativetype'
    old_cfg_key = 'metadata.nativetype'
    if cfg_key in ds.config:
        return ds.config[cfg_key]
    # FIXME this next conditional should be removed once datasets at
    # datasets.datalad.org have received the metadata config update
    elif old_cfg_key in ds.config:
        return ds.config[old_cfg_key]
    return []


def _parse_argspec(args):
    """Little helper to get cmdline and python args into a uniform
    shape

    Returns
    -------
    tags, mapping
      A list of tags, and a dict with a mapping of given metadatakeys
      and their associates metadata values
    """
    tags = []
    mapping = {}
    if not args:
        return tags, mapping
    if not isinstance(args, (dict, list, tuple)):
        raise ValueError(
            'invalid metadata specification, must be a dict or sequence')

    asdict = isinstance(args, dict)
    for k in args.items() if isinstance(args, dict) else args:
        v = None
        if asdict:
            # simple, came in from a dict
            k, v = k
            if v:
                mapping[_get_key(k)] = v
            else:
                tags.append(k)
        elif isinstance(k, list):
            # list of lists, came from cmdline
            if len(k) == 1:
                tags.append(k[0])
            elif len(k) > 1:
                mapping[_get_key(k[0])] = k[1:]
            else:
                raise ValueError(
                    'invalid metadata specification, something weird')
        else:
            tags.append(k)
    return tags, mapping


def _get_key(k):
    # annex has caseinsensitive, good enough
    k = k.lower()
    # validate keys against annex constraints
    if not valid_key.match(k):
        raise ValueError(
            'invalid metadata key "{}", must match pattern {}'.format(
                k, valid_key.pattern))
    return k


class MetadataDict(dict):
    """Metadata dict helper class"""
    def merge_none(self, spec):
        # we are not merging, done
        pass

    def merge_init(self, spec):
        for k, v in spec.items() if spec else []:
            if k not in self:
                if isinstance(v, (list, tuple)) and len(v) == 1:
                    v = v[0]
                self[k] = v

    def merge_purge(self, spec):
        for k in spec:
            if k in self:
                del self[k]

    def merge_reset(self, spec):
        for k, v in spec.items():
            self[k] = v

    def merge_add(self, spec):
        for k, v in spec.items():
            # TODO we should probably refuse to add to any
            # keys that start with '@' (JSON-LD reserved keys)
            vals = sorted(unique(
                assure_list(self.get(k, [])) + assure_list(v)))
            if len(vals) == 1:
                vals = vals[0]
            self[k] = vals

    def merge_remove(self, spec):
        for k, v in spec.items():
            existing_data = self.get(k, [])
            if isinstance(existing_data, dict):
                self[k] = {dk: existing_data[dk]
                           for dk in set(existing_data).difference(v)}
            else:
                self[k] = list(set(existing_data).difference(v))
            # wipe out if empty
            if not self[k]:
                del self[k]


def _prep_manipulation_spec(init, add, remove, reset):
    """Process manipulation args and bring in form needed by git-annex"""
    # bring metadataset setter args in shape first
    untag, remove = _parse_argspec(remove)
    purge, reset = _parse_argspec(reset)
    tag_add, add = _parse_argspec(add)
    tag_init, init = _parse_argspec(init)
    # merge all potential sources of tag specifications
    all_untag = remove.get('tag', []) + untag
    if all_untag:
        remove['tag'] = all_untag
    all_addtag = add.get('tag', []) + tag_add
    if all_addtag:
        add['tag'] = all_addtag
    all_inittag = init.get('tag', []) + tag_init
    if all_inittag:
        init['tag'] = all_inittag

    for label, arg in (('init', init),
                       ('add', add),
                       ('remove', remove),
                       ('reset', reset),
                       ('purge', purge)):
        lgr.debug("Will '%s' metadata items: %s", label, arg)
    return init, add, remove, reset, purge


def _load_json_object(fpath, cache=None):
    if cache is None:
        cache = {}
    obj = cache.get(
        fpath,
        jsonload(fpath, fixup=True) if exists(fpath) else {})
    cache[fpath] = obj
    return obj


def _load_xz_json_stream(fpath, cache=None):
    if cache is None:
        cache = {}
    obj = cache.get(
        fpath,
        {s['path']: {k: v for k, v in s.items() if k != 'path'}
         # take out the 'path' from the payload
         for s in load_xzstream(fpath)} if exists(fpath) else {})
    cache[fpath] = obj
    return obj


def _get_metadatarelevant_paths(ds, subds_relpaths):
    return (f for f in ds.repo.get_files()
            if not any(f.startswith(_with_sep(ex)) or
                       f == ex
                       for ex in list(exclude_from_metadata) + subds_relpaths))


def _get_containingds_from_agginfo(info, rpath):
    """Return the relative path of a dataset that contains a relative query path

    Parameters
    ----------
    info : dict
      Content of aggregate.json (dict with relative subdataset paths as keys)
    rpath : str
      Relative query path

    Returns
    -------
    str or None
      None is returned if the is no match, the relative path of the closest
      containing subdataset otherwise.
    """
    if rpath in info:
        dspath = rpath
    else:
        # not a direct hit, hence we find the closest
        # containing subdataset (if there is any)
        containing_ds = sorted(
            [subds for subds in sorted(info)
             if rpath.startswith(_with_sep(subds))],
            # TODO os.sep might not be OK on windows,
            # depending on where it was aggregated, ensure uniform UNIX
            # storage
            key=lambda x: x.count(os.sep), reverse=True)
        dspath = containing_ds[0] if len(containing_ds) else None
    return dspath


def _query_aggregated_metadata(reporton, ds, aps, merge_mode, recursive=False,
                               **kwargs):
    """Query the aggregated metadata in a dataset

    Query paths (`aps`) have to be composed in an intelligent fashion
    by the caller of this function, i.e. it should have been decided
    outside which dataset to query for any given path.

    Also this function doesn't cache anything, hence the caller must
    make sure to only call this once per dataset to avoid waste.

    Parameters
    ----------
    reporton : {'none', 'dataset', 'files', 'all'}
    ds : Dataset
      Dataset to query
    aps : list
      Sequence of annotated paths to query metadata for.
    merge_mode : {'init', 'add', 'reset'}
      Merge strategy for native metadata
    recursive : bool
      Whether or not to report metadata underneath all query paths
      recursively.
    **kwargs
      Any other argument will be passed on to the query result dictionary.

    Returns
    -------
    generator
      Of result dictionaries.
    """
    # TODO recursion_limit

    # TODO rename function and query datalad/annex own metadata
    # for all actually present dataset after looking at aggregated data

    # look for and load the aggregation info for the base dataset
    info_fpath = opj(ds.path, agginfo_relpath)
    agg_base_path = dirname(info_fpath)
    agginfos = _load_json_object(info_fpath)

    # cache once loaded metadata objects for additional lookups
    # TODO possibly supply this cache from outside, if objects could
    # be needed again -- there filename does not change in a superdataset
    # if done, cache under relpath, not abspath key
    cache = {
        'objcache': {},
        'subds_relpaths': None,
    }
    reported = set()

    # for all query paths
    for ap in aps:
        # all metadata is registered via its relative path to the
        # dataset that is being queried
        rpath = relpath(ap['path'], start=ds.path)
        if rpath in reported:
            # we already had this, probably via recursion of some kind
            continue

        containing_ds = _get_containingds_from_agginfo(agginfos, rpath)
        if containing_ds is None:
            # could happen if there was no aggregated metadata at all
            # or the path is in this dataset, but luckily the queried dataset
            # is known to be present
            containing_ds = curdir

        # build list of datasets and paths to be queried for this annotated path
        # in the simple case this is just the containing dataset and the actual
        # query path
        to_query = [(containing_ds, rpath)]
        if recursive:
            # in case of recursion this is also anything in any dataset underneath
            # the query path
            matching_subds = [(sub, sub) for sub in sorted(agginfos)
                              # we already have the base dataset
                              if (rpath == curdir and sub != curdir) or
                              sub.startswith(_with_sep(rpath))]
            to_query.extend(matching_subds)

        for qds, qpath in to_query:
            for r in _query_aggregated_metadata_singlepath(
                    ds, agginfos, agg_base_path, qpath, qds, reporton,
                    cache, merge_mode):
                r.update(kwargs)
                # if we are coming from `search` we want to record why this is being
                # reported
                if 'query_matched' in ap:
                    r['query_matched'] = ap['query_matched']
                if r.get('type', None) == 'file':
                    r['parentds'] = opj(ds.path, qds)
                yield r
                reported.add(qpath)


def _query_aggregated_metadata_singlepath(
        ds, agginfos, agg_base_path, rpath, containing_ds, reporton, cache, merge_mode):
    """This is the workhorse of _query_aggregated_metadata for querying for a
    single path"""
    # info about the dataset that contains the query path
    dsinfo = agginfos.get(containing_ds, dict(id=ds.id))

    metadata = MetadataDict()

    if (rpath == curdir or rpath == containing_ds) and reporton in ('datasets', 'all'):
        # this is a direct match for a dataset (we only have agginfos for
        # datasets) -> prep result
        res = get_status_dict(
            # normpath to avoid trailing dot
            path=normpath(opj(ds.path, rpath)),
            type='dataset',
            metadata=metadata)
        for s, d in (('id', 'dsid'), ('refcommit', 'refcommit')):
            if s in dsinfo:
                res[d] = dsinfo[s]
        if rpath == curdir:
            # we are querying this dataset itself, which we know to be present
            # rerun datalad_core parser to reflect potential local
            # modifications since the last aggregation
            # (if there even was any ever)
            dsmeta, _, errored = _get_metadata(
                ds,
                ['datalad_core'],
                'init',
                # we acknowledge the dataset configuration for global metadata
                global_meta=None,
                # but we force-stop the content metadata query via git-annex
                content_meta=False)
            if errored:
                res['status'] = 'error'
                res['message'] = errored
                yield res
                return
            # merge current dsmeta
            metadata.update(dsmeta)
        # and now blend with any previously aggregated metadata
        objloc = dsinfo.get('dataset_info', None)
        if objloc is not None:
            obj_path = opj(agg_base_path, objloc)
            # TODO get annexed obj file
            #ds.get(path=[obj_path], result_renderer=None)
            obj = _load_json_object(
                obj_path,
                cache=cache['objcache'])
            # must pull out old context before the merge to avoid
            # dtype mangling of the context dict
            context = metadata.get('@context', {})
            getattr(metadata, 'merge_{}'.format(merge_mode))(obj)
            _merge_context(ds, context, obj.get('@context', {}))
            if context:
                metadata['@context'] = context

        # all info on the dataset is gathered -> eject
        res['status'] = 'ok'
        yield res
        if reporton == 'datasets':
            # we had a direct match on a dataset for this path, we are done
            return

    if reporton not in ('files', 'all'):
        return

    #
    # everything that follows is about content metadata
    #
    contentinfo_objloc = dsinfo.get('content_info', None)

    # content info dicts have metadata stored under paths that are relative
    # to the dataset they were aggregated from
    rparentpath = relpath(rpath, start=containing_ds)

    annex_meta = {}
    # TODO this condition is inadequate once we query something in an aggregated subdataset
    # but through the dataset at curdir
    if containing_ds == curdir and ds.config.obtain(
            # TODO this is actuall about requerying present datasets
            # and is a major slow-down on datasets with many files...
            # dedicated switch?
            'datalad.metadata.aggregate-content-datalad-core',
            default=True,
            valtype=EnsureBool()):
        if cache['subds_relpaths'] is None:
            subds_relpaths = ds.subdatasets(
                fulfilled=None,
                result_xfm='relpaths',
                return_type='list',
                result_renderer=None)
            cache['subds_relpaths'] = subds_relpaths
        # we pull out ALL files at once, not just those matching the query paths
        # because this will be much faster than doing it multiple times for
        # multiple queries within the same dataset
        files = _get_metadatarelevant_paths(ds, cache['subds_relpaths'])
        # we are querying this dataset itself, which we know to be present
        # get uptodate file metadata from git-annex to reflect potential local
        # modifications since the last aggregation
        # (if there even was any ever)
        from datalad.metadata.parsers.datalad_core import MetadataParser as DLCP
        # TODO this could be further limited to particular paths (now []), but we would
        # need to get the list of metadata-relevant paths all the way down here
        # without having to recompute
        annex_meta.update(DLCP(ds, [])._get_content_metadata(files))

    # TODO load and turn into a lookup dict -> cache
    # so we have some files to query, and we also have some content metadata
    contentmeta = _load_xz_json_stream(
        opj(agg_base_path, contentinfo_objloc),
        cache=cache['objcache']) if contentinfo_objloc else {}

    for fpath in [f for f in contentmeta.keys()
                  if rparentpath == curdir or
                  f == rparentpath or
                  f.startswith(_with_sep(rparentpath))]:
        # we might be onto something here, prepare result
        # start with the current annex metadata for this path, if anything
        metadata = MetadataDict(annex_meta.get(fpath, {}))

        res = get_status_dict(
            status='ok',
            # the specific match within the containing dataset
            # normpath() because containing_ds could be `curdir`
            path=normpath(opj(ds.path, containing_ds, fpath)),
            # we can only match files
            type='file',
            metadata=metadata)
        for s, d in (('id', 'dsid'), ('refcommit', 'refcommit')):
            if s in dsinfo:
                res[d] = dsinfo[s]

        # merge records for any matching path
        metadata.merge_add(contentmeta.get(fpath, {}))

        yield res


def _merge_context(ds, old, new):
    # keys in contexts should not conflict and we want to union of the
    # vocabulary in any case
    for k, v in new.items():
        if k in old and v != old[k]:
            # there is no point in mangling the keys here, the conflict
            # was introduced by our own parsers, or by a custom
            # definition in this dataset, and should be fixed at the
            # source and not here
            lgr.warning(
                '%s redefines metadata key %s to "%s" (was: %s), ignored',
                ds, k, v, old[k])
        else:
            old[k] = v


def _filter_metadata_fields(d, maxsize=None, blacklist=None):
    if blacklist:
        d = {k: v for k, v in d.items()
             if not any(bl.match(k) for bl in blacklist)}
    if maxsize:
        d = {k: v for k, v in d.items()
             if len(str(v) if not isinstance(v, string_types + (binary_type,)) else v) <= maxsize}
    return d


def _get_metadata(ds, types, merge_mode, global_meta=None, content_meta=None,
                  paths=None):
    """Make a direct query of a dataset to extract its metadata.

    Parameters
    ----------
    ds : Dataset
    types : list
    mode : {'init', 'add', 'reset'}
    """
    errored = False
    dsmeta = MetadataDict()
    # each item in here will be a MetadataDict, but not the whole thing
    contentmeta = {}

    if global_meta is not None and content_meta is not None and \
            not global_meta and not content_meta:
        # both are false and not just none
        return dsmeta, contentmeta, errored

    context = {
        '@vocab': 'http://docs.datalad.org/schema_v{}.json'.format(
            vocabulary_version)}

    # keep local, who knows what some parsers might pull in
    from . import parsers
    for mtype in types:
        try:
            pmod = import_module('.{}'.format(mtype),
                                 package=parsers.__package__)
        except ImportError as e:
            lgr.warning(
                "Failed to import metadata parser for '%s', "
                "broken dataset configuration (%s)? "
                "This type of metadata will be ignored: %s",
                mtype, ds, exc_str(e))
            if cfg.get('datalad.runtime.raiseonerror'):
                raise
            errored = True
            continue
        parser = pmod.MetadataParser(ds, paths=paths)
        try:
            dsmeta_t, contentmeta_t = parser.get_metadata(
                dataset=global_meta if global_meta is not None else ds.config.obtain(
                    'datalad.metadata.aggregate-dataset-{}'.format(mtype.replace('_', '-')),
                    default=True,
                    valtype=EnsureBool()),
                content=content_meta if content_meta is not None else ds.config.obtain(
                    'datalad.metadata.aggregate-content-{}'.format(mtype.replace('_', '-')),
                    default=True,
                    valtype=EnsureBool()))
        except Exception as e:
            lgr.error('Failed to get dataset metadata ({}): {}'.format(
                mtype, exc_str(e)))
            if cfg.get('datalad.runtime.raiseonerror'):
                raise
            errored = True
            # if we dont get global metadata we do not want content metadata
            continue

        if dsmeta_t:
            if dsmeta_t is not None and not isinstance(dsmeta_t, dict):
                lgr.error(
                    "Metadata parser '%s' yielded something other than a dictionary "
                    "for dataset %s -- this is likely a bug, please consider "
                    "reporting it. "
                    "This type of native metadata will be ignored. Got: %s",
                    mtype, ds, repr(dsmeta_t))
                errored = True
            elif dsmeta_t:
                getattr(dsmeta, 'merge_{}'.format(merge_mode))(dsmeta_t)
                # treat @context info dsmeta_t separately
                # keys in their should not conflict and we want to union of the
                # vocabulary in any case
                _merge_context(ds, context, dsmeta_t.get('@context', {}))

        for loc, meta in contentmeta_t or {}:
            if not isinstance(meta, dict):
                lgr.error(
                    "Metadata parser '%s' yielded something other than a dictionary "
                    "for dataset %s content %s -- this is likely a bug, please consider "
                    "reporting it. "
                    "This type of native metadata will be ignored. Got: %s",
                    mtype, ds, loc, repr(meta))
                errored = True
            elif meta:
                if loc in contentmeta:
                    # we already have this on record -> merge
                    getattr(contentmeta[loc], 'merge_{}'.format(merge_mode))(meta)
                else:
                    # no prior record, wrap an helper and store
                    contentmeta[loc] = MetadataDict(meta)

    # pull out potential metadata field blacklist config settings
    blacklist = [re.compile(bl) for bl in assure_list(ds.config.obtain(
        'datalad.metadata.aggregate-ignore-fields',
        default=[]))]
    # enforce size limits
    max_fieldsize = ds.config.obtain('datalad.metadata.maxfieldsize')
    dsmeta = _filter_metadata_fields(
        dsmeta,
        maxsize=max_fieldsize,
        blacklist=blacklist)
    contentmeta = {
        k: _filter_metadata_fields(
            contentmeta[k],
            maxsize=max_fieldsize,
            blacklist=blacklist)
        for k in contentmeta}
    # go through content metadata and inject report of unique keys
    # and values into `dsmeta`
    unique_cm = {}
    for cm in contentmeta.values():
        for k, v in cm.items():
            # TODO instead of a set, it could be a set with counts
            vset = unique_cm.get(k, set())
            # prevent nested structures in unique prop list
            vset.add(', '.join(str(i) if isinstance(i, (int, float)) else i
                               for i in v) if isinstance(v, (tuple, list)) else v)
            unique_cm[k] = vset
    if unique_cm:
        dsmeta['unique_content_properties'] = {
            k: sorted(v) if len(v) > 1 else list(v)[0]
            for k, v in unique_cm.items()}

    # always identify the effective vocabulary - JSON-LD style
    if context:
        dsmeta['@context'] = context

    return dsmeta, contentmeta, errored


# TODO: check call 'datalad metadata -a mike' (no path)


@build_doc
class Metadata(Interface):
    """Metadata manipulation for files and entire datasets

    Two types of metadata are supported:

    1. metadata describing a dataset as a whole (dataset-global metadata), and

    2. metadata for files in a dataset (content metadata).

    Both types can be accessed and modified with this command.

    DataLad's native metadata capabilities are primarily targeting data
    description via arbitrary tags and other (brief) key-value attributes
    (possibly with multiple values for a single key).

    Metadata key names are limited to alphanumerics (and [_-.]). Moreover,
    all key names are converted to lower case.


    *Dataset (global) metadata*

    Metadata describing a dataset as a whole is stored in JSON format
    in the dataset at .datalad/metadata/dataset.json. The amount of
    metadata that can be stored is not limited by DataLad. However,
    it should be kept brief as this information is stored in the Git
    history of the dataset, and access or modification requires to
    read the entire file.

    Arbitrary metadata keys can be used. However, DataLad reserves the
    keys 'tag' and 'definition' for its own use. They can still be
    manipulated without any restrictions like any other metadata items,
    but doing so can impact DataLad's metadata-related functionality --
    handle with care.

    The 'tag' key is used to store a list of (unique) tags or keywords.

    The 'definition' key is used to store key-value mappings that define
    metadata terms (including keys) used elsewhere in the metadata. Using the
    feature is optional (see --define-key). It can be useful in the context of
    data discovery needs, where metadata terms can be precisely defined by
    linking them to specific ontology terms.


    *Content metadata*

    Metadata storage for individual files is provided by git-annex, and
    generally the same rules as for dataset-global metadata apply.
    However, there is just one reserved key name: 'tag'.

    Again, the amount of metadata is not limited, but metadata are stored
    in git-annex's internal data structures in the Git repository of a
    dataset. Large amounts of metadata can slow its performance.


    *Metadata reporting*

    When this command is called on just a path (or multiple paths) without any
    of the metadata manipulation options, the recorded metadata for each path
    are reported. If metadata from other sources has been aggregated previously
    (see 'aggregated-metadata' command), a report comprises the merged
    information from both types of metadata, aggregated and DataLad-native. The
    merge-strategy can be selected via the --merge-native option.

    In contrast, when this command is used to manipulate metadata, the final
    metadata report will only reflect the DataLad-native metadata stored for a
    given path.


    *Metadata manipulation*

    While DataLad supports a variety of metadata standards and formats, only
    DataLad-native metadata can be altered via this command.  Modification of
    any other metadata source is not supported, and requires tailored
    modification of the respective file(s) containing said metadata.

    Manipulation of dataset-global and content metadata uses the same logic and
    semantics (see --apply2global for the switch to select which type of
    metadata to alter). Four manipulation methods are provided:

    --add
      add a value to a key, and create the key if it doesn't exist yet

    --init
      only assign a value to a key, if the key doesn't exist yet

    --remove
      remove a particular value from an existing metadata key

    --reset
      replace any values for a key with the given ones, or
      remove the entire key if no values are given.

    By default, DataLad will refuse to add metadata keys that are undefined.
    A key can either be defined in the basic DataLad vocabulary, or by
    adding a custom definition to the dataset-global metadata (see --define-key).
    While it is possible to override this behavior (see --permit-undefined-keys),
    it is strongly advised to only use defined metadata keys to avoid significantly
    impaired data discovery performance across datasets.

    || CMDLINE >>
    *Output rendering*

    By default, a short summary of the metadata for each dataset
    (component) is rendered::

      <path> (<type>): -|<keys> [<tags>]

    where <path> is the path of the respective component, <type> a label
    for the type of dataset components metadata are presented for. Non-existant
    metadata are indicated by a dash, otherwise a comma-separated list of
    metadata keys (except for 'tag'), is followed by a list of tags, if there
    are any.


    << CMDLINE ||
    """
    # make the custom renderer the default, path reporting isn't the top
    # priority here
    result_renderer = 'tailored'

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""dataset to operate on""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path(s) to set/get metadata for",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        add=Parameter(
            args=('-a', '--add',),
            nargs='+',
            action='append',
            metavar=('KEY', 'VAL'),
            doc="""metadata items to add. If only a key is given, a
            corresponding tag is added. If a key-value mapping (multiple
            values at once are supported) is given, the values are
            added to the metadata item of that key.""",
            constraints=EnsureStr() | EnsureNone()),
        init=Parameter(
            args=('-i', '--init',),
            nargs='+',
            action='append',
            metavar=('KEY', 'VAL'),
            doc="""like --add, but tags are only added if no tag was present
            before. Likewise, values are only added to a metadata key, if that
            key did not exist before.""",
            constraints=EnsureStr() | EnsureNone()),
        remove=Parameter(
            args=('--remove',),
            nargs='+',
            action='append',
            metavar=('KEY', 'VAL'),
            doc="""metadata values to remove. If only a key is given, a
            corresponding tag is removed. If a key-value mapping (multiple
            values at once are supported) is given, only those values are
            removed from the metadata item of that key. If no values are left
            after the removal, the entire item of that key is removed.""",
            constraints=EnsureStr() | EnsureNone()),
        reset=Parameter(
            args=('--reset',),
            nargs='+',
            action='append',
            metavar=('KEY', 'VAL'),
            doc="""metadata items to remove. If only a key is given, a
            corresponding metadata key with all its values is removed.
            If a key-value mapping (multiple values at once are supported)
            is given, any existing values for this key are replaced by the
            given ones.""",
            constraints=EnsureStr() | EnsureNone()),
        define_key=Parameter(
            args=('--define-key',),
            nargs=2,
            action='append',
            metavar=('KEY', 'DEFINITION'),
            doc="""convenience option to add an item in the dataset's
            global metadata ('definition' key). This can be used to
            define (custom) keys used in the datasets's metadata, for
            example by providing a URL to an ontology term for a given
            key label. This option does not need --dataset-global to
            be set to be in effect.""",
            constraints=EnsureStr() | EnsureNone()),
        show_keys=Parameter(
            args=('--show-keys',),
            action='store_true',
            doc="""if set, a list of known metadata keys (including the
            origin of their definition) is shown. No other action is
            performed, even if other arguments are given."""),
        permit_undefined_keys=Parameter(
            args=('--permit-undefined-keys',),
            action='store_true',
            doc="""if set, adding (to) undefined metadata keys is
            permitted. By default such an attempt will result in an
            error. It is better to use --define-key to provide
            a definition for a metadata key, or to use pre-defined
            keys (see --show-keys)."""),
        apply2global=Parameter(
            args=('-g', '--apply2global'),
            action='store_true',
            doc="""Whether to perform metadata modification
            on the global dataset metadata, or on individual dataset
            components. For example, without this switch setting
            metadata using the root path of a dataset, will set the
            given metadata for all files in a dataset, whereas with
            this flag only the metadata record of the dataset itself
            will be altered."""),
        reporton=reporton_opt,
        merge_native=merge_native_opt,
        recursive=recursion_flag,
        recursion_limit=recursion_limit)

    @staticmethod
    @datasetmethod(name='metadata')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            add=None,
            init=None,
            remove=None,
            reset=None,
            define_key=None,
            show_keys=False,
            permit_undefined_keys=False,
            apply2global=False,
            reporton='all',
            merge_native='init',
            recursive=False,
            recursion_limit=None):
        # prep args
        init, add, remove, reset, purge = \
            _prep_manipulation_spec(init, add, remove, reset)
        define_key = dict(define_key) if define_key else None

        # prep results
        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='metadata', logger=lgr)
        if refds_path:
            res_kwargs['refds'] = refds_path

        if show_keys:
            # to get into the ds meta branches below
            apply2global = True
            for k in sorted(common_defs):
                if k.startswith('@'):
                    continue
                ui.message('{}: {} ({})\n  {}'.format(
                    ac.color_word(k, ac.BOLD),
                    common_defs[k]['def'],
                    ac.color_word('builtin', ac.MAGENTA),
                    common_defs[k]['descr']))
            # we need to go on with the command, because further definitions
            # could be provided in each dataset

        if not dataset and not path and not show_keys:
            # makes no sense to have no dataset, go with "here"
            # error generation happens during annotation
            path = curdir

        content_by_ds = OrderedDict()
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='metadata',
                # uninstalled subdatasets could be queried via aggregated metadata
                # -> no 'error'
                unavailable_path_status='',
                nondataset_path_status='error',
                # we need to know when to look into aggregated data
                force_subds_discovery=True,
                force_parentds_discovery=True,
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if ap.get('type', None) == 'dataset' and GitRepo.is_valid_repo(ap['path']):
                ap['process_content'] = True
            to_query = None
            if ap.get('state', None) == 'absent' or \
                    ap.get('type', 'dataset') != 'dataset':
                # this is a lonely absent dataset/file or content in a present dataset
                # -> query through parent
                # there must be a parent, otherwise this would be a non-dataset path
                # and would have errored during annotation
                to_query = ap['parentds']
            else:
                to_query = ap['path']
            if to_query:
                pcontent = content_by_ds.get(to_query, [])
                pcontent.append(ap)
                content_by_ds[to_query] = pcontent

        # first deal with the two simple cases
        if show_keys:
            # report any dataset-defined keys and exit
            for ds_path in content_by_ds:
                db_path = opj(ds_path, db_relpath)
                db = _load_json_object(db_path)
                defs = db.get('definition', {})
                for k in sorted(defs):
                    ui.message('{}: {} ({}: {})'.format(
                        ac.color_word(k, ac.BOLD),
                        defs[k],
                        ac.color_word('dataset', ac.MAGENTA),
                        ds_path))
            return
        elif not (init or purge or reset or add or remove or define_key):
            # just a query of metadata, no modification
            # test for datasets that will be queried, but have never been aggregated
            to_aggregate = [d for d in content_by_ds
                            if not exists(opj(d, agginfo_relpath))]
            if to_aggregate:
                lgr.warning(
                    'Metadata query results might be incomplete, initial '
                    'metadata aggregation was not yet performed in %s at: %s',
                    single_or_plural(
                        'dataset', 'datasets', len(to_aggregate), include_count=True),
                    to_aggregate)

            for ds_path in content_by_ds:
                ds = Dataset(ds_path)
                query_agg = [ap for ap in content_by_ds[ds_path]
                             # this is an available subdataset, will be processed in another
                             # iteration
                             if ap.get('state', None) == 'absent' or
                             not(ap.get('type', None) == 'dataset' and ap['path'] != ds_path)]
                if not query_agg:
                    continue
                # report from aggregated metadata
                for r in _query_aggregated_metadata(
                        reporton, ds, query_agg, merge_native,
                        # recursion was already performed during
                        # path annotation
                        # TODO is that right? it could only recurse into datasets
                        # on the filesystem, but there might be any number of
                        # uninstalled datasets underneath the last installed one
                        # for which we might have metadata -- like this just
                        # needs to pass the flag to the query function
                        recursive=False,
                        **res_kwargs):
                    yield r
            return
        #
        # all the rest is about modification of metadata there is no dedicated
        # query code beyond this point, only git-annex's report on metadata status
        # for files after modification
        #
        # iterate over all datasets, order doesn't matter
        to_save = []
        for ds_path in content_by_ds:
            # check the each path assigned to this dataset to anticipate and intercept
            # potential problems before any processing starts
            content = []
            for ap in content_by_ds[ds_path]:
                if ap.get('type', None) == 'dataset':
                    if ap.get('state', None) == 'absent':
                        # this is a missing dataset, could be an error or not installed
                        # either way we cannot edit its metadata
                        if ap.get('raw_input', False):
                            yield get_status_dict(
                                path=ap['path'],
                                status='error',
                                message='cannot edit metadata of unavailable dataset',
                                **res_kwargs)
                        continue
                    elif ap['path'] != ds_path:
                        # some kind of subdataset that actually exists
                        # -> some other iteration
                        continue
                content.append(ap)
            if not content:
                # any originally given content in this dataset will either be processed
                # in some other context or should not be processed at all.
                # error were yielded before, hence stop here
                continue
            #
            # read dataset metadata, needed in most cases
            # TODO could be made optional, when no global metadata is supposed to be
            # reported, and no key definitions have to be checked
            #
            db_path = opj(ds_path, db_relpath)
            db = MetadataDict(_load_json_object(db_path))
            #
            # key handling
            #
            defs = db.get('definition', {})
            #
            # store new key defintions in the dataset
            # we have to do this in every dataset and cannot inherit definitions
            # from a parent, because the metadata in each dataset need to be
            # consistent and self contained, as it may be part of multiple parents
            #
            added_def = False
            if define_key:
                for k, v in define_key.items():
                    if k not in defs:
                        defs[k] = v
                        added_def = True
                    elif not defs[k] == v:
                        yield get_status_dict(
                            status='error',
                            path=ds_path,
                            message=(
                                "conflicting definition for key '%s': '%s' != '%s'",
                                k, v, defs[k]),
                            **res_kwargs)
                        continue
                db['definition'] = defs
            #
            # validate keys (only possible once dataset-defined keys are known)
            #
            known_keys = set(common_defs.keys()).union(set(defs.keys()))
            key_error = False
            for cat in (init, add, reset) if not permit_undefined_keys else []:
                for k in cat if cat else []:
                    if k not in known_keys:
                        yield get_status_dict(
                            status='error',
                            path=ds_path,
                            type='dataset',
                            message=(
                                "undefined key '%s', check spelling or use --define-key "
                                "and consider suggesting a new pre-configured key "
                                "at https://github.com/datalad/datalad/issues/new",
                                k),
                            **res_kwargs)
                        key_error = True
            if key_error:
                return
            #
            # generic global metadata manipulation
            #
            ds = Dataset(ds_path)
            if not apply2global and not isinstance(ds.repo, AnnexRepo) and \
                    (init or purge or reset or add or remove):
                # not file metadata without annex
                # report on all explicitly requested paths only
                for ap in [c for c in content if ap.get('raw_input', False)]:
                    yield dict(
                        ap,
                        status='impossible',
                        message=(
                            'non-annex dataset %s has no file metadata support', ds),
                        **res_kwargs)
                continue
            if apply2global and \
                    (init or purge or reset or add or remove or define_key):
                # TODO make manipulation order identical to what git-annex does
                db.merge_init(init)
                db.merge_purge(purge)
                db.merge_reset(reset)
                db.merge_add(add)
                db.merge_remove(remove)

            if db and (added_def or (apply2global and
                       (init or purge or reset or add or remove))):
                # store, if there is anything, and we could have touched it
                if not exists(dirname(db_path)):
                    makedirs(dirname(db_path))
                jsondump(db, db_path)
                # use add not save to also cover case of a fresh file
                ds.add(db_path, save=False, to_git=True)
                to_save.append(dict(
                    path=db_path,
                    parentds=ds.path,
                    type='file'))
            if not db and exists(db_path):
                # no global metadata left, kill file
                ds.remove(db_path)
                to_save.append(dict(
                    path=ds.path,
                    type='dataset'))
            # report metadata after modification
            if define_key or (apply2global and
                              (init or purge or reset or add or remove)):
                yield get_status_dict(
                    ds=ds,
                    status='ok',
                    metadata=db,
                    **res_kwargs)
            #
            # file metadata manipulation
            #
            ds_paths = [p['path'] for p in content]
            if not apply2global and (reset or purge or add or init or remove):
                respath_by_status = {}
                for res in ds.repo.set_metadata(
                        ds_paths,
                        reset=reset,
                        add=add,
                        init=init,
                        remove=remove,
                        purge=purge,
                        # we always go recursive
                        # XXX is that a good thing? But how to otherwise distinuish
                        # this kind of recursive from the one across datasets in
                        # the API?
                        recursive=True):
                    res = annexjson2result(
                        # annex reports are always about files
                        res, ds, type='file', **res_kwargs)
                    success = success_status_map[res['status']]
                    respath_by_status[success] = \
                        respath_by_status.get(success, []) + [res['path']]
                    #if not success:
                    #    # if there was success we get the full query after manipulation
                    #    # at the very end
                    yield res
                # report on things requested that annex was silent about
                for r in results_from_annex_noinfo(
                        ds, ds_paths, respath_by_status,
                        dir_fail_msg='could not set metadata for some content in %s %s',
                        noinfo_dir_msg='no metadata to set in %s',
                        noinfo_file_msg="metadata not supported (only annex'ed files)",
                        noinfo_status='impossible',
                        **res_kwargs):
                    if r['status'] in ('ok', 'notneeded'):
                        # for cases where everything is good enough honor `reporton`
                        if reporton in ('none', 'datasets'):
                            # we only get file/directory reports at this stage
                            continue
                        elif r.get('type', None) != 'file' and not reporton == 'all':
                            # anything that is not a file (e.g. directory) is ignored
                            # unless all reports are requested
                            continue
                    yield r
            ## report metadata after modification
            #for r in _query_metadata(reporton, ds, ds_paths, merge_native,
            #                         db=db, **res_kwargs):
            #    yield r
        #
        # save potential modifications to dataset global metadata
        #
        if not to_save:
            return
        for res in Save.__call__(
                path=to_save,
                dataset=refds_path,
                message='[DATALAD] dataset metadata update',
                return_type='generator',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        import datalad.support.ansi_colors as ac
        if res['status'] != 'ok' or not res.get('action', None) == 'metadata':
            # logging complained about this already
            return
        # list the path, available metadata keys, and tags
        path = relpath(res['path'],
                       res['refds']) if res.get('refds', None) else res['path']
        meta = res.get('metadata', {})
        ui.message('{path}{type}:{spacer}{meta}{tags}'.format(
            path=ac.color_word(path, ac.BOLD),
            type=' ({})'.format(
                ac.color_word(res['type'], ac.MAGENTA)) if 'type' in res else '',
            spacer=' ' if len([m for m in meta if m != 'tag']) else '',
            meta=','.join(k for k in sorted(meta.keys())
                          if k not in ('tag', '@context', '@id'))
                 if meta else ' -',
            tags='' if 'tag' not in meta else ' [{}]'.format(
                 ','.join(assure_list(meta['tag'])))))
