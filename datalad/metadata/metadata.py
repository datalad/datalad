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


import glob
import logging
import os
import os.path as op
from collections import (
    OrderedDict,
)
from six import (
    iteritems,
)
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.base import Interface
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
import datalad.support.ansi_colors as ac
from datalad.support.json_py import (
    load as jsonload,
    load_xzstream,
)
from datalad.interface.common_opts import (
    recursion_flag,
    reporton_opt,
)
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.utils import (
    assure_list,
    path_is_subpath,
    path_startswith,
)
from datalad.ui import ui
from datalad.consts import (
    METADATA_DIR,
    METADATA_FILENAME,
)

lgr = logging.getLogger('datalad.metadata.metadata')

aggregate_layout_version = 1

# relative paths which to exclude from any metadata processing
# including anything underneath them
exclude_from_metadata = ('.datalad', '.git', '.gitmodules', '.gitattributes')

# TODO filepath_info is obsolete
location_keys = ('dataset_info', 'content_info', 'filepath_info')


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


def _load_json_object(fpath, cache=None):
    if cache is None:
        cache = {}
    obj = cache.get(
        fpath,
        jsonload(fpath, fixup=True) if op.lexists(fpath) else {})
    cache[fpath] = obj
    return obj


def _load_xz_json_stream(fpath, cache=None):
    if cache is None:
        cache = {}
    obj = cache.get(
        fpath,
        {s['path']: {k: v for k, v in iteritems(s) if k != 'path'}
         # take out the 'path' from the payload
         for s in load_xzstream(fpath)} if op.lexists(fpath) else {})
    cache[fpath] = obj
    return obj


def _get_metadatarelevant_paths(ds, subds_relpaths):
    return (f for f in ds.repo.get_files()
            if not any(path_startswith(f, ex)
                       for ex in list(exclude_from_metadata) + subds_relpaths))


def _get_containingds_from_agginfo(info, rpath):
    """Return the path of a dataset that contains a query path

    If a query path matches a dataset path directly, the matching dataset path
    is return -- not the parent dataset!

    Parameters
    ----------
    info : dict
      Content of aggregate.json (dict with (relative) subdataset paths as keys)
    rpath : str
      Query path can be absolute or relative, but must match the convention
      used in the info dict.

    Returns
    -------
    str or None
      None is returned if there is no match, the path of the closest
      containing subdataset otherwise (in the convention used in the
      info dict).
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
    agginfos, agg_base_path = load_ds_aggregate_db(ds)

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
        rpath = op.relpath(ap['path'], start=ds.path)
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
            containing_ds = op.curdir
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
                              if (rpath == op.curdir and sub != op.curdir) or
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
        lgr.debug(
            'Verifying/achieving local availability of %i metadata objects',
            len(objfiles))
        if objfiles:
            get(path=[dict(path=op.join(agg_base_path, of),
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
                    op.join(agg_base_path, dsobjloc),
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
                    r['parentds'] = op.normpath(op.join(ds.path, qap['metaprovider']))
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
    if (rpath == op.curdir or rpath == containing_ds) and \
            ((reporton is None and qtype == 'dataset') or \
             reporton in ('datasets', 'all')):
        # this is a direct match for a dataset (we only have agginfos for
        # datasets) -> prep result
        res = get_status_dict(
            status='ok',
            metadata=dsmeta,
            # normpath to avoid trailing dot
            path=op.normpath(op.join(ds.path, rpath)),
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
    rparentpath = op.relpath(rpath, start=containing_ds)

    # so we have some files to query, and we also have some content metadata
    contentmeta = _load_xz_json_stream(
        op.join(agg_base_path, contentinfo_objloc),
        cache=cache['objcache']) if contentinfo_objloc else {}

    for fpath in [f for f in contentmeta.keys()
                  if rparentpath == op.curdir or
                  path_startswith(f, rparentpath)]:
        # we might be onto something here, prepare result
        metadata = contentmeta.get(fpath, {})

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
            # normpath() because containing_ds could be `op.curdir`
            path=op.normpath(op.join(ds.path, containing_ds, fpath)),
            # we can only match files
            type='file',
            metadata=metadata)
        yield res


def get_ds_aggregate_db_locations(ds, version='default'):
    """Returns the location of a dataset's aggregate metadata DB

    Parameters
    ----------
    ds : Dataset
      Dataset instance to query
    version : str
      DataLad aggregate metadata layout version. At the moment only a single
      version exists. 'default' will return the locations for the current default
      layout version.

    Returns
    -------
    db_location, db_object_base_path
      Absolute paths to the DB itself, and to the basepath to resolve relative
      object references in the database. Either path may not exist in the
      queried dataset.
    """
    layout_version = aggregate_layout_version \
        if version == 'default' else version

    agginfo_relpath_template = op.join(
        '.datalad',
        'metadata',
        'aggregate_v{}.json')
    agginfo_relpath = agginfo_relpath_template.format(layout_version)
    info_fpath = op.join(ds.path, agginfo_relpath)
    agg_base_path = op.dirname(info_fpath)
    # not sure if this is the right place with these check, better move then to a higher level
    if not op.exists(info_fpath):
        if version == 'default':
            # caller had no specific idea what metadata version is needed/available
            # This dataset does not have aggregated metadata.  Does it have any
            # other version?
            info_glob = agginfo_relpath_template.format('*')
            info_files = glob.glob(info_glob)
            msg = "Found no aggregated metadata info file %s." \
                  % info_fpath
            old_metadata_file = op.join(ds.path, METADATA_DIR, METADATA_FILENAME)
            if op.exists(old_metadata_file):
                msg += " Found metadata generated with pre-0.10 version of " \
                       "DataLad, but it will not be used."
            upgrade_msg = ""
            if info_files:
                msg += " Found following info files, which might have been " \
                       "generated with newer version(s) of datalad: %s." \
                       % (', '.join(info_files))
                upgrade_msg = ", upgrade datalad"
            msg += " You will likely need to either update the dataset from its " \
                   "original location%s or reaggregate metadata locally." \
                   % upgrade_msg
            lgr.warning(msg)
    return info_fpath, agg_base_path


def load_ds_aggregate_db(ds, version='default', abspath=False):
    """Load a dataset's aggregate metadata database

    Parameters
    ----------
    ds : Dataset
      Dataset instance to query
    version : str
      DataLad aggregate metadata layout version. At the moment only a single
      version exists. 'default' will return the content of the current default
      aggregate database version.

    Returns
    -------
    dict [, str]
      A dictionary with the database content is return. If abspath is True,
      all paths in the dictionary (datasets, metadata object archives) are
      absolute. If abspath is False, all paths are relative, and the metadata
      object base path is return as a second value.
    """
    info_fpath, agg_base_path = get_ds_aggregate_db_locations(ds, version)

    # save to call even with a non-existing location
    agginfos = _load_json_object(info_fpath)

    if abspath:
        return {
            # paths in DB on disk are always relative
            # make absolute to ease processing during aggregation
            op.normpath(op.join(ds.path, p)):
            {k: op.normpath(op.join(agg_base_path, v)) if k in location_keys else v
             for k, v in props.items()}
            for p, props in agginfos.items()
        }
    else:
        return agginfos, agg_base_path


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
            agginfos = load_ds_aggregate_db(
                ds,
                version=str(aggregate_layout_version),
                abspath=True
            )
            if not agginfos:
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
            parentds = []
            for dspath in sorted(agginfos):
                info = agginfos[dspath]
                if parentds and not path_is_subpath(dspath, parentds[-1]):
                    parentds.pop()
                info.update(
                    path=dspath,
                    type='dataset',
                    status='ok',
                )
                if dspath == ds.path:
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
            path = op.curdir

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
        path = op.relpath(res['path'],
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
