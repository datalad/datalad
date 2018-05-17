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
from os.path import dirname
from os.path import relpath
from os.path import normpath
from os.path import curdir
from os.path import exists
from os.path import lexists
from os.path import join as opj
from collections import OrderedDict
from collections import Mapping
from six import binary_type, string_types

from datalad import cfg
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.base import Interface
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.metadata.definitions import version as vocabulary_version
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureBool
from datalad.support.constraints import EnsureStr
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
import datalad.support.ansi_colors as ac
from datalad.support.json_py import load as jsonload
from datalad.support.json_py import load_xzstream
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import reporton_opt
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.utils import assure_list
from datalad.utils import path_is_subpath, path_startswith
from datalad.utils import as_unicode
from datalad.ui import ui
from datalad.dochelpers import exc_str
from datalad.dochelpers import single_or_plural


from datalad.log import log_progress
lgr = logging.getLogger('datalad.metadata.metadata')

aggregate_layout_version = 1
agginfo_relpath = opj(
    '.datalad',
    'metadata',
    'aggregate_v{}.json'.format(aggregate_layout_version))

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


class MetadataDict(dict):
    """Metadata dict helper class"""
    # TODO no longer needed ATM, but keeping for now, avoiding the
    # big diff
    pass


def _load_json_object(fpath, cache=None):
    if cache is None:
        cache = {}
    obj = cache.get(
        fpath,
        jsonload(fpath, fixup=True) if lexists(fpath) else {})
    cache[fpath] = obj
    return obj


def _load_xz_json_stream(fpath, cache=None):
    if cache is None:
        cache = {}
    obj = cache.get(
        fpath,
        {s['path']: {k: v for k, v in s.items() if k != 'path'}
         # take out the 'path' from the payload
         for s in load_xzstream(fpath)} if lexists(fpath) else {})
    cache[fpath] = obj
    return obj


def _get_metadatarelevant_paths(ds, subds_relpaths):
    return (f for f in ds.repo.get_files()
            if not any(path_startswith(f, ex)
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
             if path_is_subpath(rpath, subds)],
            # TODO os.sep might not be OK on windows,
            # depending on where it was aggregated, ensure uniform UNIX
            # storage
            key=lambda x: x.count(os.sep), reverse=True)
        dspath = containing_ds[0] if len(containing_ds) else None
    return dspath


def query_aggregated_metadata(reporton, ds, aps, recursive=False,
                              **kwargs):
    """Query the aggregated metadata in a dataset

    Query paths (`aps`) have to be composed in an intelligent fashion
    by the caller of this function, i.e. it should have been decided
    outside which dataset to query for any given path.

    Also this function doesn't cache anything, hence the caller must
    make sure to only call this once per dataset to avoid waste.

    Parameters
    ----------
    reporton : {None, 'none', 'dataset', 'files', 'all'}
      If `None`, reporting will be based on the `type` property of the
      incoming annotated paths.
    ds : Dataset
      Dataset to query
    aps : list
      Sequence of annotated paths to query metadata for.
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
    from datalad.coreapi import get
    # look for and load the aggregation info for the base dataset
    info_fpath = opj(ds.path, agginfo_relpath)
    agg_base_path = dirname(info_fpath)
    agginfos = _load_json_object(info_fpath)

    # cache once loaded metadata objects for additional lookups
    # TODO possibly supply this cache from outside, if objects could
    # be needed again -- their filename does not change in a superdataset
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
        rap = dict(ap, rpath=rpath, type=ap.get('type', None))

        # we really have to look this up from the aggregated metadata
        # and cannot use any 'parentds' property in the incoming annotated
        # path. the latter will reflect the situation on disk, we need
        # the record of the containing subdataset in the aggregated metadata
        # instead
        containing_ds = _get_containingds_from_agginfo(agginfos, rpath)
        if containing_ds is None:
            # could happen if there was no aggregated metadata at all
            # or the path is in this dataset, but luckily the queried dataset
            # is known to be present
            containing_ds = curdir
        rap['metaprovider'] = containing_ds

        # build list of datasets and paths to be queried for this annotated path
        # in the simple case this is just the containing dataset and the actual
        # query path
        to_query = [rap]
        if recursive:
            # in case of recursion this is also anything in any dataset underneath
            # the query path
            matching_subds = [{'metaprovider': sub, 'rpath': sub, 'type': 'dataset'}
                              for sub in sorted(agginfos)
                              # we already have the base dataset
                              if (rpath == curdir and sub != curdir) or
                              path_is_subpath(sub, rpath)]
            to_query.extend(matching_subds)

        to_query_available = []
        for qap in to_query:
            if qap['metaprovider'] not in agginfos:
                res = get_status_dict(
                    status='impossible',
                    path=qap['path'],
                    message=(
                        'Dataset at %s contains no aggregated metadata on this path',
                        qap['metaprovider']),
                )
                res.update(res, **kwargs)
                if 'type' in qap:
                    res['type'] = qap['type']
                yield res
            else:
                to_query_available.append(qap)

        # one heck of a beast to get the set of filenames for all metadata objects that are
        # required to be present to fulfill this query
        objfiles = set(
            agginfos.get(qap['metaprovider'], {}).get(t, None)
            for qap in to_query_available
            for t in ('dataset_info',) + \
            (('content_info',)
                if ((reporton is None and qap.get('type', None) == 'file') or
                    reporton in ('files', 'all')) else tuple())
        )
        # in case there was no metadata provider, we do not want to start
        # downloading everything: see https://github.com/datalad/datalad/issues/2458
        objfiles.difference_update([None])
        lgr.debug('Verifying/achieving local availability of %i metadata objects', len(objfiles))
        if objfiles:
            get(path=[dict(path=opj(agg_base_path, of),
                           parentds=ds.path, type='file')
                      for of in objfiles if of],
                dataset=ds,
                result_renderer='disabled')
        for qap in to_query_available:
            # info about the dataset that contains the query path
            dsinfo = agginfos.get(qap['metaprovider'], dict(id=ds.id))
            res_tmpl = get_status_dict()
            for s, d in (('id', 'dsid'), ('refcommit', 'refcommit')):
                if s in dsinfo:
                    res_tmpl[d] = dsinfo[s]

            # pull up dataset metadata, always needed if only for the context
            dsmeta = {}
            dsobjloc = dsinfo.get('dataset_info', None)
            if dsobjloc is not None:
                dsmeta = _load_json_object(
                    opj(agg_base_path, dsobjloc),
                    cache=cache['objcache'])

            for r in _query_aggregated_metadata_singlepath(
                    ds, agginfos, agg_base_path, qap, reporton,
                    cache, dsmeta,
                    dsinfo.get('content_info', None)):
                r.update(res_tmpl, **kwargs)
                # if we are coming from `search` we want to record why this is being
                # reported
                if 'query_matched' in ap:
                    r['query_matched'] = ap['query_matched']
                if r.get('type', None) == 'file':
                    r['parentds'] = normpath(opj(ds.path, qap['metaprovider']))
                yield r
                reported.add(qap['rpath'])


def _query_aggregated_metadata_singlepath(
        ds, agginfos, agg_base_path, qap, reporton, cache, dsmeta,
        contentinfo_objloc):
    """This is the workhorse of query_aggregated_metadata() for querying for a
    single path"""
    rpath = qap['rpath']
    containing_ds = qap['metaprovider']
    qtype = qap.get('type', None)
    if (rpath == curdir or rpath == containing_ds) and \
            ((reporton is None and qtype == 'dataset') or \
             reporton in ('datasets', 'all')):
        # this is a direct match for a dataset (we only have agginfos for
        # datasets) -> prep result
        res = get_status_dict(
            status='ok',
            metadata=dsmeta,
            # normpath to avoid trailing dot
            path=normpath(opj(ds.path, rpath)),
            type='dataset')
        # all info on the dataset is gathered -> eject
        yield res

    if (reporton is None and qtype != 'file') or reporton not in (None, 'files', 'all'):
        return

    #
    # everything that follows is about content metadata
    #
    # content info dicts have metadata stored under paths that are relative
    # to the dataset they were aggregated from
    rparentpath = relpath(rpath, start=containing_ds)

    # so we have some files to query, and we also have some content metadata
    contentmeta = _load_xz_json_stream(
        opj(agg_base_path, contentinfo_objloc),
        cache=cache['objcache']) if contentinfo_objloc else {}

    for fpath in [f for f in contentmeta.keys()
                  if rparentpath == curdir or
                  path_startswith(f, rparentpath)]:
        # we might be onto something here, prepare result
        metadata = MetadataDict(contentmeta.get(fpath, {}))

        # we have to pull out the context for each extractor from the dataset
        # metadata
        for tlk in metadata:
            if tlk.startswith('@'):
                continue
            context = dsmeta.get(tlk, {}).get('@context', None)
            if context is None:
                continue
            metadata[tlk]['@context'] = context
        if '@context' in dsmeta:
            metadata['@context'] = dsmeta['@context']

        res = get_status_dict(
            status='ok',
            # the specific match within the containing dataset
            # normpath() because containing_ds could be `curdir`
            path=normpath(opj(ds.path, containing_ds, fpath)),
            # we can only match files
            type='file',
            metadata=metadata)
        yield res


def _filter_metadata_fields(d, maxsize=None, blacklist=None):
    o = d
    if blacklist:
        o = {k: v for k, v in o.items()
             if k.startswith('@') or not any(bl.match(k) for bl in blacklist)}
    if maxsize:
        o = {k: v for k, v in o.items()
             if k.startswith('@') or (len(str(v)
                                      if not isinstance(v, string_types + (binary_type,))
                                      else v) <= maxsize)}
    if len(d) != len(o):
        lgr.info('Removed metadata field(s) due to blacklisting and max size settings: %s',
                 set(d.keys()).difference(o.keys()))
    return o


def _ok_metadata(meta, mtype, ds, loc):
    if meta is None or isinstance(meta, dict):
        return True

    msg = (
        "Metadata extractor '%s' yielded something other than a dictionary "
        "for dataset %s%s -- this is likely a bug, please consider "
        "reporting it. "
        "This type of native metadata will be ignored. Got: %s",
        mtype,
        ds,
        '' if loc is None else ' content {}'.format(loc),
        repr(meta))
    if cfg.get('datalad.runtime.raiseonerror'):
        raise RuntimeError(*msg)

    lgr.error(*msg)
    return False


def _get_metadata(ds, types, global_meta=None, content_meta=None, paths=None):
    """Make a direct query of a dataset to extract its metadata.

    Parameters
    ----------
    ds : Dataset
    types : list
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

    fullpathlist = paths
    if paths and isinstance(ds.repo, AnnexRepo):
        # Ugly? Jep: #2055
        content_info = zip(paths, ds.repo.file_has_content(paths), ds.repo.is_under_annex(paths))
        paths = [p for p, c, a in content_info if not a or c]
        nocontent = len(fullpathlist) - len(paths)
        if nocontent:
            # TODO better fail, or support incremental and label this file as no present
            lgr.warn(
                '{} files have no content present, skipped metadata extraction for {}'.format(
                    nocontent,
                    'them' if nocontent > 10 else [p for p, c, a in content_info if not c and a]))

    # pull out potential metadata field blacklist config settings
    blacklist = [re.compile(bl) for bl in assure_list(ds.config.obtain(
        'datalad.metadata.aggregate-ignore-fields',
        default=[]))]
    # enforce size limits
    max_fieldsize = ds.config.obtain('datalad.metadata.maxfieldsize')
    # keep local, who knows what some extractors might pull in
    from pkg_resources import iter_entry_points  # delayed heavy import
    extractors = {ep.name: ep for ep in iter_entry_points('datalad.metadata.extractors')}

    log_progress(
        lgr.info,
        'metadataextractors',
        'Start metadata extraction from %s', ds,
        total=len(types),
        label='Metadata extraction',
        unit=' extractors',
    )
    for mtype in types:
        mtype_key = mtype
        log_progress(
            lgr.info,
            'metadataextractors',
            'Engage %s metadata extractor', mtype_key,
            update=1,
            increment=True)
        if mtype_key not in extractors:
            # we said that we want to fail, rather then just moan about less metadata
            log_progress(
                lgr.error,
                'metadataextractors',
                'Failed %s metadata extraction from %s', mtype_key, ds,
            )
            raise ValueError(
                'Enable metadata extractor %s is not available in this installation',
                mtype_key)
        try:
            extractor_cls = extractors[mtype_key].load()
            extractor = extractor_cls(ds, paths=paths)
        except Exception as e:
            log_progress(
                lgr.error,
                'metadataextractors',
                'Failed %s metadata extraction from %s', mtype_key, ds,
            )
            raise ValueError(
                "Failed to load metadata extractor for '%s', "
                "broken dataset configuration (%s)?: %s",
                mtype, ds, exc_str(e))
            continue
        try:
            dsmeta_t, contentmeta_t = extractor.get_metadata(
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
                log_progress(
                    lgr.error,
                    'metadataextractors',
                    'Failed %s metadata extraction from %s', mtype_key, ds,
                )
                raise
            errored = True
            # if we dont get global metadata we do not want content metadata
            continue

        if dsmeta_t:
            if _ok_metadata(dsmeta_t, mtype, ds, None):
                dsmeta_t = _filter_metadata_fields(
                    dsmeta_t,
                    maxsize=max_fieldsize,
                    blacklist=blacklist)
                dsmeta[mtype_key] = dsmeta_t
            else:
                errored = True

        unique_cm = {}
        extractor_unique_exclude = getattr(extractor_cls, "_unique_exclude", set())
        for loc, meta in contentmeta_t or {}:
            if not _ok_metadata(meta, mtype, ds, loc):
                errored = True
                continue
            # we also want to store info that there was no metadata(e.g. to get a list of
            # files that have no metadata)
            # if there is an issue that a extractor needlessly produces empty records, the
            # extractor should be fixed and not a general switch. For example the datalad_core
            # issues empty records to document the presence of a file
            #elif not meta:
            #    continue

            meta = MetadataDict(meta)
            # apply filters
            meta = _filter_metadata_fields(
                meta,
                maxsize=max_fieldsize,
                blacklist=blacklist)

            # assign
            # only ask each metadata extractor once, hence no conflict possible
            loc_dict = contentmeta.get(loc, {})
            if meta:
                # do not store empty stuff
                loc_dict[mtype_key] = meta
            contentmeta[loc] = loc_dict

            if ds.config.obtain(
                    'datalad.metadata.generate-unique-{}'.format(mtype_key.replace('_', '-')),
                    default=True,
                    valtype=EnsureBool()):
                # go through content metadata and inject report of unique keys
                # and values into `dsmeta`
                for k, v in meta.items():
                    if k in dsmeta.get(mtype_key, {}):
                        # if the dataset already has a dedicated idea
                        # about a key, we skip it from the unique list
                        # the point of the list is to make missing info about
                        # content known in the dataset, not to blindly
                        # duplicate metadata. Example: list of samples data
                        # were recorded from. If the dataset has such under
                        # a 'sample' key, we should prefer that, over an
                        # aggregated list of a hopefully-kinda-ok structure
                        continue
                    elif k in extractor_unique_exclude:
                        # the extractor thinks this key is worthless for the purpose
                        # of discovering whole datasets
                        # we keep the key (so we know that some file is providing this key),
                        # but ignore any value it came with
                        unique_cm[k] = None
                        continue
                    vset = unique_cm.get(k, set())
                    vset.add(_val2hashable(v))
                    unique_cm[k] = vset

        if unique_cm:
            # per source storage here too
            ucp = dsmeta.get('datalad_unique_content_properties', {})
            # important: we want to have a stable order regarding
            # the unique values (a list). we cannot guarantee the
            # same order of discovery, hence even when not using a
            # set above we would still need sorting. the callenge
            # is that any value can be an arbitrarily complex nested
            # beast
            # we also want to have each unique value set always come
            # in a top-level list, so we known if some unique value
            # was a list, os opposed to a list of unique values
            ucp[mtype_key] = {
                k: [dict(i) if isinstance(i, ReadOnlyDict) else i
                    for i in sorted(
                        v,
                        key=_unique_value_key)] if v is not None else None
                for k, v in unique_cm.items()
                # v == None (disable unique, but there was a value at some point)
                # otherwise we only want actual values, and also no single-item-lists
                # of a non-value
                # those contribute no information, but bloat the operation
                # (inflated number of keys, inflated storage, inflated search index, ...)
                if v is None or (v and not v == {''})}
            dsmeta['datalad_unique_content_properties'] = ucp

    log_progress(
        lgr.info,
        'metadataextractors',
        'Finished metadata extraction from %s', ds,
    )

    # always identify the effective vocabulary - JSON-LD style
    if context:
        dsmeta['@context'] = context

    return dsmeta, contentmeta, errored


def _unique_value_key(x):
    """Small helper for sorting unique content metadata values"""
    if isinstance(x, ReadOnlyDict):
        # turn into an item tuple with keys sorted and values plain
        # or as a hash if *dicts
        x = [(k,
              hash(x[k])
              if isinstance(x[k], ReadOnlyDict) else x[k])
             for k in sorted(x)]
    # we need to force str, because sorted in PY3 refuses to compare
    # any heterogeneous type combinations, such as str/int, tuple(int)/tuple(str)
    return as_unicode(x)


def _val2hashable(val):
    """Small helper to convert incoming mutables to something hashable

    The goal is to be able to put the return value into a set, while
    avoiding conversions that would result in a change of representation
    in a subsequent JSON string.
    """
    if isinstance(val, dict):
        return ReadOnlyDict(val)
    elif isinstance(val, list):
        return tuple(map(_val2hashable, val))
    else:
        return val


class ReadOnlyDict(Mapping):
    # Taken from https://github.com/slezica/python-frozendict
    # License: MIT
    """
    An immutable wrapper around dictionaries that implements the complete
    :py:class:`collections.Mapping` interface. It can be used as a drop-in
    replacement for dictionaries where immutability is desired.
    """
    dict_cls = dict

    def __init__(self, *args, **kwargs):
        self._dict = self.dict_cls(*args, **kwargs)
        self._hash = None

    def __getitem__(self, key):
        return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def copy(self, **add_or_replace):
        return self.__class__(self, **add_or_replace)

    def __iter__(self):
        return iter(self._dict)

    def __len__(self):
        return len(self._dict)

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self._dict)

    def __hash__(self):
        iteritems = getattr(dict, 'iteritems', dict.items) # py2-3 compatibility
        if self._hash is None:
            h = 0
            for key, value in iteritems(self._dict):
                h ^= hash((key, value))
            self._hash = h
        return self._hash


@build_doc
class Metadata(Interface):
    """Metadata reporting for files and entire datasets

    Two types of metadata are supported:

    1. metadata describing a dataset as a whole (dataset-global metadata), and

    2. metadata for files in a dataset (content metadata).

    Both types can be accessed with this command.

    Examples:

      Report the metadata of a single file, as aggregated into the closest
      locally available dataset, containing the query path::

        % datalad metadata somedir/subdir/thisfile.dat

      Sometimes it is helpful to get metadata records formatted in a more accessible
      form, here as pretty-printed JSON::

        % datalad -f json_pp metadata somedir/subdir/thisfile.dat

      Same query as above, but specify which dataset to query (must be
      containing the query path)::

        % datalad metadata -d . somedir/subdir/thisfile.dat

      Report any metadata record of any dataset known to the queried dataset::

        % datalad metadata --recursive --reporton datasets 

      Get a JSON-formatted report of aggregated metadata in a dataset, incl.
      information on enabled metadata extractors, dataset versions, dataset IDs,
      and dataset paths::

        % datalad -f json metadata --get-aggregates
    """
    # make the custom renderer the default, path reporting isn't the top
    # priority here
    result_renderer = 'tailored'

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""dataset to query. If given, metadata will be reported
            as stored in this dataset. Otherwise, the closest available
            dataset containing a query path will be consulted.""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path(s) to query metadata for",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        get_aggregates=Parameter(
            args=('--get-aggregates',),
            action='store_true',
            doc="""if set, yields all (sub)datasets for which aggregate
            metadata are available in the dataset. No other action is
            performed, even if other arguments are given. The reported
            results contain a datasets's ID, the commit hash at which
            metadata aggregation was performed, and the location of the
            object file(s) containing the aggregated metadata."""),
        reporton=reporton_opt,
        recursive=recursion_flag)
        # MIH: not sure of a recursion limit makes sense here
        # ("outdated from 5 levels down?")
        #recursion_limit=recursion_limit)

    @staticmethod
    @datasetmethod(name='metadata')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            get_aggregates=False,
            reporton='all',
            recursive=False):
        # prep results
        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='metadata', logger=lgr)
        if refds_path:
            res_kwargs['refds'] = refds_path

        if get_aggregates:
            # yield all datasets for which we have aggregated metadata as results
            # the get actual dataset results, so we can turn them into dataset
            # instances using generic top-level code if desired
            ds = require_dataset(
                refds_path,
                check_installed=True,
                purpose='aggregate metadata query')
            info_fpath = opj(ds.path, agginfo_relpath)
            if not exists(info_fpath):
                # if there has ever been an aggregation run, this file would
                # exist, hence there has not been and we need to tell this
                # to people
                yield get_status_dict(
                    ds=ds,
                    status='impossible',
                    action='metadata',
                    logger=lgr,
                    message='metadata aggregation has never been performed in this dataset')
                return
            agginfos = _load_json_object(info_fpath)
            parentds = []
            for sd in sorted(agginfos):
                info = agginfos[sd]
                dspath = normpath(opj(ds.path, sd))
                if parentds and not path_is_subpath(dspath, parentds[-1]):
                    parentds.pop()
                info.update(
                    path=dspath,
                    type='dataset',
                    status='ok',
                )
                if sd == curdir:
                    info['layout_version'] = aggregate_layout_version
                if parentds:
                    info['parentds'] = parentds[-1]
                yield dict(
                    info,
                    **res_kwargs
                )
                parentds.append(dspath)
            return

        if not dataset and not path:
            # makes no sense to have no dataset, go with "here"
            # error generation happens during annotation
            path = curdir

        content_by_ds = OrderedDict()
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                # MIH: we are querying the aggregated metadata anyways, and that
                # mechanism has its own, faster way to go down the hierarchy
                #recursive=recursive,
                #recursion_limit=recursion_limit,
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
            for r in query_aggregated_metadata(
                    reporton,
                    # by default query the reference dataset, only if there is none
                    # try our luck in the dataset that contains the queried path
                    # this is consistent with e.g. `get_aggregates` reporting the
                    # situation in the reference dataset only
                    Dataset(refds_path) if refds_path else ds,
                    query_agg,
                    # recursion above could only recurse into datasets
                    # on the filesystem, but there might be any number of
                    # uninstalled datasets underneath the last installed one
                    # for which we might have metadata
                    recursive=recursive,
                    **res_kwargs):
                yield r
        return

    @staticmethod
    def custom_result_renderer(res, **kwargs):
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
                 if meta else ' -' if 'metadata' in res else ' aggregated',
            tags='' if 'tag' not in meta else ' [{}]'.format(
                 ','.join(assure_list(meta['tag'])))))
