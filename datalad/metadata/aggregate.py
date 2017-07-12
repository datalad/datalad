# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for aggregating metadata
"""

__docformat__ = 'restructuredtext'

from os.path import join as opj
from os.path import dirname
from os.path import relpath
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import discover_dataset_trace_to_targets
from datalad.interface.save import Save
from datalad.interface.base import build_doc
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import nosave_opt
from datalad.interface.results import get_status_dict
from datalad.distribution.dataset import Dataset
from datalad.metadata.metadata import Metadata
from datalad.metadata.metadata import agginfo_relpath
from datalad.metadata.metadata import _load_json_object
from datalad.distribution.dataset import datasetmethod, EnsureDataset, require_dataset
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.log import lgr
from datalad.support.json_py import dump as jsondump


def _adj2subbranches(base, adj):
    # given a set of parent-child mapping, compute a mapping of each parent
    # to all its (grand)children of any depth level
    branches = dict(adj)
    # from bottom up
    for ds in sorted(adj, reverse=True):
        subbranch = []
        for sub in branches[ds]:
            subbranch.append(sub)
            subbranch.extend(branches.get(sub, []))
        branches[ds] = subbranch
    return branches


def _get_obj_location(info):
    # TODO add 'origin' info into file name, do when needed, code is
    # forward compatible
    return opj('objects', '{}-{}'.format(
        info['type'], info['id']))


def _update_ds_agginfo(baseds, dsmeta, filemeta, agg_base_path, to_save):
    """Update the aggregate metadata (info) of a single dataset"""
    dsid = None
    agginfo = []
    for cmeta in dsmeta:
        ci = {k: cmeta[k]
              for k in ('type', 'id', 'shasum', 'origin')
              if k in cmeta}
        loc = _get_obj_location(cmeta) if cmeta.get('metadata', None) else None
        ci['location'] = loc
        ci_id = ci.get('id', None)
        agginfo.append(ci)
        if dsid is None and ci_id is not None:
            dsid = ci_id
        if dsid != ci_id:
            lgr.warning("internal consistency error: multiple dataset ID for a single dataset")
        # write obj files
        if not loc:
            # no point in empty files
            continue
        opath = opj(agg_base_path, loc)
        # TODO unlock object file
        jsondump(cmeta['metadata'], opath)
        to_save.append(dict(path=opath, type='file'))
    # reduce file metadata, for now limit to our own data sources only, later this would need to be
    # wrapped in a loop across sources
    fm = {relpath(r['path'], start=baseds.path): r['metadata']
          for r in filemeta or []
          if r.get('metadata', None) and r.get('origin', None) == 'datalad'}
    if fm:
        if dsid is None:
            lgr.warning("internal consistency error: file-based metadata, but no dataset ID present")
        # only if there is anything, build agginfo item
        finfo = dict(type='files', id=dsid)
        loc = _get_obj_location(finfo)
        finfo['location'] = loc
        agginfo.append(finfo)
        opath = opj(agg_base_path, loc)
        # TODO unlock object file
        jsondump(fm, opath)
        to_save.append(dict(path=opath, type='file'))
    return agginfo


def _aggregate_dataset(parentds, subds_paths, dsmeta_db, filemeta_db, to_save):
    """Perform metadata aggregation for ds and a given list of subdataset paths"""
    parentds = Dataset(parentds)
    # location info of aggregate metadata
    agginfo_fpath = opj(parentds.path, agginfo_relpath)
    agg_base_path = dirname(agginfo_fpath)
    # load existing aggregate info dict
    agginfos = _load_json_object(agginfo_fpath)
    # make list of object files we no longer reference
    objs2remove = set()
    # and new ones
    objs2add = set()
    # for each subdataset (any depth level)
    for subds_path in subds_paths:
        subds_relpath = relpath(subds_path, start=parentds.path)
        # set of metadata objects currently referenced for this subdataset
        objlocs_was = set([ci['location'] for ci in agginfos.get(subds_relpath, []) if ci['location']])
        # build aggregate info for the current subdataset
        agginfo = _update_ds_agginfo(
            parentds,
            dsmeta_db[subds_path],
            # file metadata could be absent
            filemeta_db.get(subds_path, None),
            agg_base_path,
            to_save)
        agginfos[subds_relpath] = agginfo

        # track changes in object files
        objlocs_is = [ci['location'] for ci in agginfo if ci['location']]
        objs2remove = objs2remove.union(objlocs_was.difference(objlocs_is))
        objs2add = objs2add.union(objlocs_is)
    # secretly remove obsolete object files, not really a result from a
    # user's perspective
    if objs2remove:
        parentds.remove(objs2remove, result_renderer=None, return_type=list)
        if not objs2add and not parentds.path == parentds.path:
            # this is not the base dataset, make sure to save removal in the
            # parentds -- not needed when objects get added, as removal itself
            # is already committed
            to_save(dict(path=parentds.path, type='dataset', staged=True))
    if objs2add:
        # they are added standard way, depending on the repo type
        parentds.add(
            [opj(agg_base_path, p) for p in objs2add],
            save=False, result_renderer=None, return_type=list)
    # write aggregate info file
    jsondump(agginfos, agginfo_fpath)
    parentds.add(agginfo_fpath, save=False, to_git=True,
                 result_renderer=None, return_type=list)
    # queue for save, and mark as staged
    to_save.append(
        dict(path=agginfo_fpath, type='file', staged=True))


@build_doc
class AggregateMetaData(Interface):
    """Aggregate meta data of a dataset for later query.

    By default meta data is aggregated across all configured native meta data
    sources. Optionally, the type of available meta data can guessed, if no
    types are configures. Moreover, it is possible to aggregate meta data from
    any subdatasets into the superdataset, in order to facilitate data
    discovery without having to obtain any subdataset.
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""topmost dataset metadata will be aggregated into. All dataset
            betwween this dataset and any given path will received updated
            aggregated metadata from all given paths.""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path to datasets whose subdataset metadata shall be aggregated.
            When a given path is pointing into a dataset, the metadata of the
            containing dataset will be aggregated.""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        guess_native_type=Parameter(
            args=("--guess-native-type",),
            action="store_true",
            doc="""guess native meta data type of datasets, if none is
            configured. With a configured, or auto-detected meta data type,
            no native meta data will be aggregated."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        save=nosave_opt,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    @eval_results
    def __call__(
            dataset,
            path,
            guess_native_type=False,
            recursive=False,
            recursion_limit=None,
            save=True):
        # basic idea:
        # - use `metadata` to get homogenized metadata for any path
        # - sort into dataset metadata and file metadata
        # - store in form that allows fast access for `metadata`, so
        #   it get use it transparently for metadata reporting of
        #   unavailable dataset components without the need of a dedicated
        #   parser
        # - the point is: `metadata` does the access and homogenization,
        #   while `aggregate` merely composed a joint structure and stores
        #   it in a dataset

        # note to self
        # am : does nothing
        # am -d . : does nothing
        # am -d . sub: aggregates sub metadata into .
        # am -d . -r : aggregates metadata of any sub into .

        refds_path = Interface.get_refds_path(dataset)

        # it really doesn't work without a dataset
        ds = require_dataset(
            dataset, check_installed=True, purpose='meta data aggregation')

        # life is simple now, we just query for metadata using the
        # exact same paths that we were given, so everything will be
        # nice and consistent

        # metadata for each discovered dataset, keys are dataset paths,
        # each value is a result dict from a `metadata` query call on the path
        dsmeta_db = {}
        # metadata for each file, keys are paths of the parent datasets,
        # each value is a dict with file path keys and value with result dicts
        # from a `metadata` query call on the file path
        filemeta_db = {}
        # TODO at the moment this will grab any metadata for any given path
        # whether it is installed or not (goes to aggregate data if needed
        # however, ATM there is no way of saying grab ANY metadata that you can
        # get a hold of, without the need to specific paths that are not even
        # discoverable on the file system
        for res in Metadata.__call__(
                dataset=refds_path,
                path=path,
                # TODO expose as selector for aggregation
                #reporton=...
                recursive=recursive,
                recursion_limit=recursion_limit,
                return_type='generator',
                on_failure='ignore',
                result_renderer=None):
            if not res['action'] == 'metadata' and res['status'] == 'ok':
                # deflect anything that is not a clean result
                yield res
            restype = res.get('type', None)
            if not restype:
                res['status'] = 'impossible'
                res['message'] = "metadata report has no 'type' property, this is likely a bug"
                yield res
                continue
            assert('parentds' in res or res.get('type', None) == 'dataset')
            if restype == 'dataset':
                lgr.info('Extracted metadata for dataset at: %s', res['path'])
                # put in DB with dataset metadata under its own path as key
                # wrap in a list to enable future extension with multiple
                # metadata set for one dataset without having to change the flow
                ds_key = res['path']
                # mark as coming from our own command
                res['origin'] = 'datalad'
                ds_db = dsmeta_db.get(ds_key, [])
                ds_db.append(res)
                dsmeta_db[ds_key] = ds_db
            elif restype == 'file':
                ds_key = res['parentds']
                ds_db = filemeta_db.get(ds_key, [])
                # mark as coming from our own command
                res['origin'] = 'datalad'
                ds_db.append(res)
                filemeta_db[ds_key] = ds_db
            else:
                res['status'] = 'impossible'
                res['message'] = (
                    "unknown metadata type '%s', this is likely a bug", restype)
                yield res
                continue

        # TODO make sure to not create an aggregated copy of a datasets own metadata
        # adjencency info of the dataset tree spanning the base to all leave dataset
        # associated with the path arguments
        ds_adj = {}
        discover_dataset_trace_to_targets(ds.path, dsmeta_db.keys(), [], ds_adj)
        # get a dict that has the list of subdatasets of any depth for any given
        # parent dataset
        subbranches = _adj2subbranches(ds.path, ds_adj)
        to_save = []
        # go over datasets in bottom-up fashion
        # TODO for now effectively just loop over datasets in dsmeta_db, this should be
        # good enough, assuming we always get dataset metadata, which is the case ATM
        for parentds_path in sorted(subbranches, reverse=True):
            lgr.info('Update aggregated metadata in dataset at: %s', parentds_path)
            _aggregate_dataset(
                parentds_path,
                subbranches[parentds_path],
                dsmeta_db,
                filemeta_db,
                to_save)
            # update complete
            yield get_status_dict(
                status='ok',
                action='aggregate_metadata',
                path=parentds_path,
                type='dataset',
                logger=lgr)
        #
        # save potential modifications to dataset global metadata
        #
        if not to_save:
            return
        for res in Save.__call__(
                files=to_save,
                dataset=refds_path,
                message='[DATALAD] dataset aggregate metadata update',
                return_type='generator',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res
