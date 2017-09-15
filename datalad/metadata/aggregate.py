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

import os
from os import makedirs
from os import listdir
from os.path import join as opj
from os.path import dirname
from os.path import relpath
from os.path import isabs
from os.path import exists
from os.path import curdir

from hashlib import md5
import shutil

from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import discover_dataset_trace_to_targets
from datalad.interface.save import Save
from datalad.interface.base import build_doc
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import merge_native_opt
from datalad.interface.results import get_status_dict
from datalad.distribution.dataset import Dataset
from datalad.metadata.metadata import agginfo_relpath
from datalad.metadata.metadata import exclude_from_metadata
from datalad.metadata.metadata import get_metadata_type
from datalad.metadata.metadata import _load_json_object
from datalad.metadata.metadata import _get_metadata
from datalad.metadata.metadata import _get_metadatarelevant_paths
from datalad.metadata.metadata import _get_containingds_from_agginfo
from datalad.distribution.dataset import datasetmethod, EnsureDataset, require_dataset
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import CommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.log import lgr
from datalad.support.json_py import dump as jsondump

from datalad.utils import with_pathsep as _with_sep
from datalad.utils import assure_list


location_keys = ('dataset_info', 'content_info', 'filepath_info')


def _get_dsinfo_from_aggmetadata(ds_path, path, recursive, db):
    """Grab info on aggregated metadata for a path from a given dataset.

    The actual info is stored in a `db` dict under the absolute path
    of the dataset that contains the query path, plus any subdataset
    in case of recursion (with their own DB entries).

    Parameters
    ----------
    ds : Dataset
      source dataset
    path : str
      absolute path for which to obtain metadata
    recursive : bool

    Returns
    -------
    str or list
      A string is an error message, a list contains all absolute paths for
      all datasets on which info was put into the DB.
    """
    def _ensure_abs_obj_location(rec):
        # object location in the DB must be absolute so we can copy easily
        # to all relevant datasets
        for key in location_keys:
            if key in rec and not isabs(rec[key]):
                rec[key] = opj(ds_path, agginfo_relpath, rec[key])

    info_fpath = opj(ds_path, agginfo_relpath)
    # TODO cache these
    agginfos = _load_json_object(info_fpath)

    rpath = relpath(path, start=ds_path)
    seed_ds = _get_containingds_from_agginfo(agginfos, rpath)
    if seed_ds is None:
        # nothing found
        # this will be the message in the result for the query path
        # and could be a tuple
        return ("No matching aggregated metadata in Dataset at %s", ds_path)

    # easy peasy
    seed_abs = opj(ds_path, seed_ds)
    db[seed_abs] = _ensure_abs_obj_location(agginfos[seed_ds])
    hits = [seed_abs]

    if not recursive:
        return hits

    # a little more complicated: we need to loop over all subdataset
    # records an pick the ones that are underneath the seed
    for agginfo_path in agginfos:
        if agginfo_path.startswith(_with_sep(seed_ds)):
            absp = opj(ds_path, agginfo_path)
            db[absp] = _ensure_abs_obj_location(agginfos[agginfo_path])
            hits.append(absp)
    # TODO we must keep the info on these recursively discovered datasets
    # somewhere, because we cannot rediscover them on the filesystem
    # when updating the datasets later on
    return hits


def _extract_metadata(agginto_ds, aggfrom_ds, db, merge_native, to_save):
    """Dump metadata from a dataset into object in the metadata store of another

    Info on the metadata objects is placed into a DB dict under the
    absolute path of the dataset whose metadata was aggregated.

    Parameters
    ----------
    agginto_ds : Dataset
    aggfrom_ds : Dataset
    db : dict
    merge_native : str
      Merge mode.
    """
    subds_relpaths = aggfrom_ds.subdatasets(result_xfm='relpaths', return_type='list')
    # figure out a "state" of the dataset wrt its metadata that we are describing
    # 1. the latest commit that changed any file for which we could have native metadata
    refcommit = _get_latest_refcommit(aggfrom_ds, subds_relpaths)
    objid = refcommit if refcommit else ''
    # 2, our own dataset-global metadata
    dsmetafile = opj(aggfrom_ds.path, '.datalad', 'metadata', 'dataset.json')
    if exists(dsmetafile):
        objid += md5(open(dsmetafile, 'r').read().encode()).hexdigest()
    # 3. potential annex-based metadata
    if isinstance(aggfrom_ds, AnnexRepo):
        # if there is no annex metadata, this will come out empty,
        # hence hash would be same as for a plain GitRepo
        # and no, we cannot use the shasum of the annex branch,
        # because this will change even when no metadata has changed
        timestamps, _ = aggfrom_ds.repo._run_annex_command(
            'metadata',
            '.',
            '-g', 'lastchanged')
        objid += timestamps.strip()

    if not objid:
        lgr.debug('%s has no metadata-relevant content', aggfrom_ds)
    else:
        lgr.debug(
            'Dump metadata of %s (merge mode: %s) into %s',
            aggfrom_ds, merge_native, agginto_ds)

    agginfo = {}
    # dataset global
    if aggfrom_ds.id:
        agginfo['id'] = aggfrom_ds.id
    agginfo['refcommit'] = refcommit
    # put in DB
    db[aggfrom_ds.path] = agginfo

    if objid:  # if there is any chance for metadata
        # obtain metadata for dataset and content
        # guessing is ON -- this slows things!
        # TODO make config switch for guessing
        nativetypes = get_metadata_type(aggfrom_ds, guess=True)
        dsmeta, contentmeta, errored = _get_metadata(
            aggfrom_ds,
            # core must come first
            ['datalad_core'] + assure_list(nativetypes),
            merge_native,
            global_meta=True,
            content_meta=True)
    else:
        dsmeta = contentmeta = None
        # this is no error, there is simply no metadata whatsoever
        return False

    # shorten to MD5sum
    objid = md5(objid.encode()).hexdigest()

    metasources = [('ds', 'dataset', dsmeta, aggfrom_ds),
                   ('cn', 'content', contentmeta, aggfrom_ds)]

    if contentmeta and aggfrom_ds != agginto_ds:
        # we have content metadata and we are aggregation into another dataset,
        # grab and store list of metadata-relevant files
        metasources.append((
            'fs',
            'filepath',
            sorted(_get_metadatarelevant_paths(aggfrom_ds, subds_relpaths)),
            agginto_ds))
    # TODO collect list of files from aggfrom_ds.repo.get_files()
    # and store in reference dataset to enable file lookup based
    # on metadata

    # for both types of metadata
    for label, mtype, meta, dest in metasources:
        if not meta:
            continue
        # only write to disk if there is something
        objrelpath = _get_obj_location(objid, label)
        # place metadata object into the source dataset
        objpath = opj(dest.path, dirname(agginfo_relpath), objrelpath)

        # write obj files
        if exists(objpath):
            dest.unlock(objpath)
        # TODO actually dump a compressed file when annexing is possible
        # to speed up on-demand access
        jsondump(meta, objpath)
        # stage for dataset.save()
        to_save.append(dict(path=objpath, type='file'))

        # important to use abspath here, needs to be rewritten relative to
        # all receiving datasets
        agginfo['{}_info'.format(mtype)] = objpath

    return errored


def _adj2subtrees(base, adj):
    # given a set of parent-child mapping, compute a mapping of each parent
    # to all its (grand)children of any depth level
    subtrees = dict(adj)
    subs = set()
    # from bottom up
    for ds in sorted(adj, reverse=True):
        subtree = []
        for sub in subtrees[ds]:
            subs.add(sub)
            subtree.append(sub)
            subtree.extend(subtrees.get(sub, []))
        subtrees[ds] = subtree
    # give each leaf dataset an entry too
    for sub in subs:
        if sub not in subtrees:
            subtrees[sub] = []
    return subtrees


def _get_latest_refcommit(ds, subds_relpaths):
    """Find the latest commit that changed any real content

    This will ignore anything at or underneath:

    - .git
    - .datalad
    - .gitmodules
    - .gitattributes
    - any submodule

    Returns
    -------
    str or None
      None is return if no commit can be found, or no relevant content
      files were found at all. Otherwise the full commit hash if the
      last commit that touch any relevant content is returned.
    """

    def _filterpaths(basepath, paths, exclude):
        final_paths = []
        for rp in [opj(basepath, p) if basepath else p for p in paths]:
            if rp in exclude:
                continue
            elif any(ep.startswith(_with_sep(rp)) for ep in exclude):
                final_paths.extend(
                    _filterpaths(rp, listdir(opj(ds.path, rp)), exclude))
                pass
            else:
                final_paths.append(rp)
        return final_paths

    relevant_paths = _filterpaths(
        '',
        listdir(ds.path),
        # NOTE: this will also ignore datalad's native dataset-global metadata
        # rationale: the metadata still describes the dataset content, so
        # even if it changes, the description changes, but not the content
        # it is describing -> ref commit should be unaffected
        list(exclude_from_metadata) + subds_relpaths)

    if not relevant_paths:
        return None

    try:
        stdout, stderr = ds.repo._git_custom_command(
            relevant_paths,
            ['git', 'log', '-n', '1', '--pretty=format:%H'],
            expect_fail=True)
        commit = stdout.strip()
        return commit
    except CommandError as e:
        if 'does not have any commits' in e.stderr:
            return None
        raise


def _get_obj_location(hash_str, ref_type):
    return opj(
        'objects',
        hash_str[:3],
        '{}-{}'.format(
            ref_type,
            hash_str[3:]))


def _update_ds_agginfo(refds_path, ds_path, subds_paths, agginfo_db, to_save):
    """Perform metadata aggregation for ds and a given list of subdataset paths

    Parameters
    ----------
    refds_path : str
      Absolute path to the reference dataset that aggregate_metadata() was
      called on.
    ds_path : str
      Absolute path to the dataset to have its aggregate info updates
    subds_paths : list(str)
      Sequence of absolute paths of subdatasets of the to-be-updated dataset,
      whose agginfo shall be updated within the to-be-updated dataset
    agginfo_db : dict
      Dictionary with all information on aggregate metadata on all datasets.
      Keys are absolute paths of datasets.
    to_save : list
      List of paths to save eventually. This function will add new paths as
      necessary.
    """
    ds = Dataset(ds_path)
    # location info of aggregate metadata
    # aggregate.json
    agginfo_fpath = opj(ds.path, agginfo_relpath)
    # base path in which aggregate.json and objects is located
    agg_base_path = dirname(agginfo_fpath)
    # load existing aggregate info dict
    # TODO take from cache, once used in _get_dsinfo_from_aggmetadata()
    ds_agginfos = _load_json_object(agginfo_fpath)
    # object locations referenced initially
    objlocs_was = set(ai[k]
                      for ai in ds_agginfos.values()
                      for k in location_keys
                      if k in ai)
    # track which objects need to be copied
    objs2copy = []
    # for each subdataset (any depth level)
    for dpath in [ds_path] + subds_paths:
        # relative path of the currect dataset within the dataset we are updating
        drelpath = relpath(dpath, start=ds.path)
        # build aggregate info for the current subdataset
        ds_dbinfo = agginfo_db.get(dpath, {}).copy()
        for loclabel in location_keys:
            if loclabel == 'filepath_info' and drelpath == curdir:
                # do not write a file list into the dataset it is from
                if 'filepath_info' in ds_dbinfo:
                    del ds_dbinfo['filepath_info']
                continue
            # abspath to object
            objloc = ds_dbinfo.get(loclabel, None)
            if objloc is None:
                continue
            # XXX needs to change when layout of object store is changed
            # current is ./datalad/metadata/objects/{hash}/{hash}
            target_objrelpath = opj(*objloc.split(os.sep)[-3:])
            # make sure we copy the file from its current location to where it is
            # needed in this dataset
            target_objpath = opj(agg_base_path, target_objrelpath)
            objs2copy.append((objloc, target_objpath))
            # now build needed local relpath
            ds_dbinfo[loclabel] = target_objrelpath
        # (re)assign in case record is new
        ds_agginfos[drelpath] = ds_dbinfo
    # set of metadata objects now referenced
    objlocs_is = set(ai[k]
                     for ai in ds_agginfos.values()
                     for k in location_keys
                     if k in ai)
    objs2remove = objlocs_was.difference(objlocs_is)
    objs2add = objlocs_is

    # secretly remove obsolete object files, not really a result from a
    # user's perspective
    if objs2remove:
        ds.remove(
            [opj(agg_base_path, p) for p in objs2remove],
            # we do not want to drop these files by default, because we would
            # loose them for other branches, and earlier tags
            # TODO evaluate whether this should be exposed as a switch
            # to run an explicit force-drop prior to calling remove()
            check=False,
            result_renderer=None, return_type=list)
        if not objs2add and not refds_path == ds_path:
            # this is not the base dataset, make sure to save removal in the
            # parentds -- not needed when objects get added, as removal itself
            # is already committed
            to_save(dict(path=ds_path, type='dataset', staged=True))

    # must copy object files to local target destination
    for copy_from, copy_to in objs2copy:
        if copy_to == copy_from:
            continue
        target_dir = dirname(copy_to)
        if not exists(target_dir):
            makedirs(target_dir)
        # TODO we could be more clever (later) and maybe `addurl` (or similar)
        # the file from another dataset
        if exists(copy_to):
            # no need to unlock, just wipe out and replace
            os.remove(copy_to)
        shutil.copy(copy_from, copy_to)
    to_save.append(
        dict(path=agginfo_fpath, type='file', staged=True))

    if objs2add:
        # they are added standard way, depending on the repo type
        ds.add(
            [opj(agg_base_path, p) for p in objs2add],
            save=False, result_renderer=None, return_type=list)
        # queue for save, and mark as staged
        to_save.extend(
            [dict(path=opj(agg_base_path, p), type='file', staged=True)
             for p in objs2add])
    # write aggregate info file
    if not ds_agginfos:
        return

    jsondump(ds_agginfos, agginfo_fpath)
    ds.add(agginfo_fpath, save=False, to_git=True,
           result_renderer=None, return_type=list)
    # queue for save, and mark as staged
    to_save.append(
        dict(path=agginfo_fpath, type='file', staged=True))

    # FIXME look for empty object dirs and remove them


@build_doc
class AggregateMetaData(Interface):
    """Aggregate meta data of a dataset for later query.

    By default meta data is aggregated across all configured native meta data
    sources. Optionally, the type of available meta data can guessed, if no
    types are configured. Moreover, it is possible to aggregate meta data from
    any subdatasets into the superdataset, in order to facilitate data
    discovery without having to obtain any subdataset.
    """
    _params_ = dict(
        # TODO add option to not update aggregated data/info in intermediate
        # datasets
        # TODO add option for full aggregation (not incremental), so when something
        # is not present nothing about it is preserved in the aggregated metadata
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""topmost dataset metadata will be aggregated into. All dataset
            between this dataset and any given path will receive updated
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
        merge_native=merge_native_opt,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        save=nosave_opt,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            guess_native_type=False,
            merge_native='init',
            recursive=False,
            recursion_limit=None,
            save=True):
        refds_path = Interface.get_refds_path(dataset)

        # it really doesn't work without a dataset
        ds = require_dataset(
            dataset, check_installed=True, purpose='meta data aggregation')
        # always include the reference dataset
        path = assure_list(path)
        path.append(ds.path)

        agginfo_db = {}
        to_save = []
        to_aggregate = set()
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='aggregate_metadata',
                # uninstalled subdatasets could be queried via aggregated metadata
                # -> no 'error'
                unavailable_path_status='',
                nondataset_path_status='error',
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            ap_type = ap.get('type', None)
            ap_state = ap.get('state', None)
            assert('parentds' in ap or ap_type == 'dataset')
            if ap_type == 'dataset' and ap_state != 'absent':
                # a present dataset, we can take directly from it
                aggsrc = ap['path']
                lgr.info('Aggregate metadata for dataset %s', aggsrc)
            else:
                # everything else needs to come from the parent
                aggsrc = ap['parentds']
                if ap_state == 'absent':
                    lgr.info(
                        'Attempt to use pre-aggregate metadata for absent %s from dataset at %s',
                        ap['path'],
                        aggsrc)
                else:
                    lgr.info(
                        'Aggregate metadata for %s from dataset at %s',
                        ap['path'],
                        aggsrc)

            to_aggregate.add(aggsrc)

            if ap_state == 'absent':
                # key thought: recursive is done by path annotation, hence
                # once we hit an absent dataset, we are 100% certain that
                # there is nothing to recurse into on the file system
                # hence we only have to look into the aggregated metadata
                # of the last available dataset in the dataset tree edge
                #
                # if there is nothing at this path, we need to look into the
                # parentds and check if we know anything about this path
                # if we do, we need to grab all the info and objects
                # if not, we need to error
                res = _get_dsinfo_from_aggmetadata(
                    aggsrc, ap['path'], recursive, agginfo_db)
                if not isinstance(res, list):
                    yield get_status_dict(
                        status='impossible',
                        message=res,
                        action='aggregate_metadata',
                        path=ap['path'],
                        logger=lgr)
                    continue
                # cue for aggregation
                to_aggregate.update(res)
            else:
                # actually aggregate metadata for this dataset, immediately place
                # generated objects into the aggregated or reference dataset,
                # and put info into DB to get the distributed to all datasets
                # that need to be updated
                errored = _extract_metadata(
                    ds,
                    Dataset(aggsrc),
                    agginfo_db,
                    merge_native,
                    to_save)
                if errored:
                    yield get_status_dict(
                        status='error',
                        message='Metadata extraction failed (see previous error message)',
                        action='aggregate_metadata',
                        path=aggsrc,
                        logger=lgr)

        # at this point we have dumped all aggregated metadata into object files
        # somewhere, we know what needs saving, but having saved anything, and
        # we know about the states of all aggregated dataset in the DB
        # what remains to do is to update all dataset, so they have there own copy
        # of aggregated metadata and update their respective aggregate.json with
        # info on what states we just aggregated from

        # first, let's figure out what dataset need updating at all
        # get adjencency info of the dataset tree spanning the base to all leave dataset
        # associated with the path arguments
        ds_adj = {}
        discover_dataset_trace_to_targets(ds.path, to_aggregate, [], ds_adj)
        # TODO we need to work in the info about dataset that we only got from
        # aggregated metadata, that had no trace on the file system in here!!
        subtrees = _adj2subtrees(ds.path, ds_adj)
        # push an empty entry for each present leaf dataset that we aggregated
        # from -> also needs its agginfo updated
        for d in to_aggregate:
            if d not in subtrees:
                subtrees[d] = []
        # go over datasets in bottom-up fashion
        for parentds_path in sorted(subtrees, reverse=True):
            lgr.info('Update aggregate metadata in dataset at: %s', parentds_path)

            _update_ds_agginfo(
                ds.path,
                parentds_path,
                subtrees[parentds_path],
                agginfo_db,
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
                path=to_save,
                dataset=refds_path,
                message='[DATALAD] dataset aggregate metadata update',
                return_type='generator',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res
