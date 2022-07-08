# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for aggregating metadata
"""

__docformat__ = 'restructuredtext'

import logging
import os

from os import makedirs
from os import listdir
import os.path as op

from hashlib import md5
import shutil

import datalad
from datalad.consts import (
    DATASET_CONFIG_FILE,
    DATASET_METADATA_FILE,
)
from datalad.interface.annotate_paths import _minimal_annotate_paths
from datalad.interface.base import Interface
from datalad.interface.utils import (
    eval_results,
    discover_dataset_trace_to_targets,
)
from datalad.core.local.save import Save
from datalad.interface.base import build_doc
from datalad.interface.common_opts import (
    recursion_limit,
    recursion_flag,
    nosave_opt,
)
from datalad.interface.results import get_status_dict
from datalad.distribution.dataset import Dataset
from datalad.metadata.metadata import (
    get_ds_aggregate_db_locations,
    load_ds_aggregate_db,
)
from datalad.metadata.metadata import (
    exclude_from_metadata,
    get_metadata_type,
    _get_metadata,
    _get_metadatarelevant_paths,
    _get_containingds_from_agginfo,
    location_keys,
)
from datalad.distribution.dataset import (
    datasetmethod,
    EnsureDataset,
    require_dataset,
)
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
    EnsureBool,
)
from datalad.support.constraints import EnsureChoice
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CapturedException
from datalad.support import json_py
from datalad.support.path import split_ext
from datalad.utils import (
    path_is_subpath,
    all_same,
    ensure_list,
)
from datalad.core.local.status import get_paths_by_ds

lgr = logging.getLogger('datalad.metadata.aggregate')


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
      A string/tuple is an error message, a list contains all absolute paths
      for all datasets on which info was put into the DB.
    """
    # TODO cache these
    agginfos = load_ds_aggregate_db(Dataset(ds_path), abspath=True)

    seed_ds = _get_containingds_from_agginfo(agginfos, path)
    if seed_ds is None:
        # nothing found
        # this will be the message in the result for the query path
        # and could be a tuple
        return ("No matching aggregated metadata for path '%s' in Dataset at %s",
                op.relpath(path, start=ds_path), ds_path)

    # easy peasy
    db[seed_ds] = agginfos[seed_ds]
    hits = [seed_ds]

    if not recursive:
        return hits

    # a little more complicated: we need to loop over all subdataset
    # records and pick the ones that are underneath the seed
    for agginfo_path in agginfos:
        if path_is_subpath(agginfo_path, seed_ds):
            db[agginfo_path] = agginfos[agginfo_path]
            hits.append(agginfo_path)
    # TODO we must keep the info on these recursively discovered datasets
    # somewhere, because we cannot rediscover them on the filesystem
    # when updating the datasets later on
    return hits


def _the_same_across_datasets(relpath, *dss):
    """Check if the file (present content or not) is identical across two datasets

    Compares files by content if under git, or by checksum if under annex

    Parameters
    ----------
    *ds: Datasets
    relpath: str
        path within datasets

    Returns
    -------
    bool or None
      True if identical, False if not, None if cannot be decided
      (e.g. different git-annex backend used)
    """
    from datalad.utils import md5sum, unique
    from datalad.support.exceptions import FileInGitError
    from datalad.support.digests import Digester

    paths = [op.join(ds.path, relpath) for ds in dss]
    # The simplest check first -- exist in both and content is the same.
    # Even if content is just a symlink file on windows, the same content
    # condition would be correct
    if all(map(op.exists, paths)) and all_same(map(md5sum, paths)):
        return True

    # We first need to find problematic ones which are annexed and
    # have no content locally, and take their
    keys = []
    backends = []
    presents = []
    for ds in dss:
        repo = ds.repo
        key = None
        present = True
        if isinstance(repo, AnnexRepo):
            annexprops = repo.get_file_annexinfo(
                relpath, eval_availability=True)
            if 'key' not in annexprops:
                continue
            key = annexprops['key']
            # For now the rest (e.g. not tracked) remains an error
            if not annexprops['has_content']:
                present = False
                backends.append(repo.get_key_backend(key))
        keys.append(key)
        presents.append(present)

    if all(presents):
        return all_same(map(md5sum, paths))

    backends = unique(backends)
    assert backends, "Since not all present - some must be under annex, and thus must have a backend!"
    # so some files are missing!
    assert not all(presents)
    NeedContentError = RuntimeError
    if len(backends) > 1:
        # TODO: or signal otherwise somehow that we just need to get at least some
        # of those files to do the check!...
        raise NeedContentError(
            "Following paths are missing content and have different annex "
            "backends: %s. Cannot determine here if the same or not!"
            % ", ".join(p for (p, b) in zip(paths, presents) if not b)
        )
    backend = backends[0].lower()
    if backend.endswith('E'):
        backend = backend[':-1']

    if backend not in Digester.DEFAULT_DIGESTS:
        raise NeedContentError(
            "Do not know how to figure out content check for backend %s" % backend
        )

    checksums = [
        split_ext(key).split('--', 1)[1] if key else key
        for key in keys
    ]
    thechecksum = set(
        checksum
        for present, checksum in zip(presents, checksums)
        if present
    )
    if len(thechecksum) > 1:
        # Different checksum (with the same backend)
        return False
    elif not thechecksum:
        raise RuntimeError("We must have had at least one key since prior logic"
                           " showed that not all files have content here")
    thechecksum = thechecksum[0]
    if any(presents):
        # We do need to extract checksum from the key and check the present
        # files' content to match
        digester = Digester([backend])
        for present, path in zip(presents, paths):
            if present and digester(path)[backend] != thechecksum:
                return False
        return True
    return False


def _dump_extracted_metadata(agginto_ds, aggfrom_ds, db, to_save, force_extraction, agg_base_path):
    """Dump metadata from a dataset into object in the metadata store of another

    Info on the metadata objects is placed into a DB dict under the
    absolute path of the dataset whose metadata was aggregated.

    Parameters
    ----------
    agginto_ds : Dataset
    aggfrom_ds : Dataset
    db : dict
    """
    subds_relpaths = aggfrom_ds.subdatasets(result_xfm='relpaths', return_type='list')
    # figure out a "state" of the dataset wrt its metadata that we are describing
    # 1. the latest commit that changed any file for which we could have native metadata
    refcommit = _get_latest_refcommit(aggfrom_ds, subds_relpaths)
    objid = refcommit if refcommit else ''
    # 2, our own dataset-global metadata and the dataset config
    for tfile in (
            op.join(aggfrom_ds.path, DATASET_METADATA_FILE),
            op.join(aggfrom_ds.path, DATASET_CONFIG_FILE)):
        if op.exists(tfile):
            objid += md5(open(tfile, 'r').read().encode()).hexdigest()
    # 3. potential annex-based metadata
    # XXX TODO shouldn't this be the annex extractor?
    if isinstance(aggfrom_ds, AnnexRepo) and \
            aggfrom_ds.config.obtain(
                'datalad.metadata.aggregate-content-datalad-core',
                default=True,
                valtype=EnsureBool()):
        # if there is no annex metadata, this will come out empty,
        # hence hash would be same as for a plain GitRepo
        # and no, we cannot use the shasum of the annex branch,
        # because this will change even when no metadata has changed
        timestamps, _ = aggfrom_ds.repo.call_annex_oneline([
            'metadata',
            '.',
            '-g', 'lastchanged'])
        objid += timestamps.strip()

    if not objid:
        lgr.debug('%s has no metadata-relevant content', aggfrom_ds)
    else:
        lgr.debug(
            'Dump metadata of %s into %s',
            aggfrom_ds, agginto_ds)

    # check if we already have in store what we are about to create
    old_agginfo = db.get(aggfrom_ds.path, {})

    agginfo = {}
    # dataset global
    if aggfrom_ds.id:
        agginfo['id'] = aggfrom_ds.id
    agginfo['refcommit'] = refcommit
    # put in DB
    db[aggfrom_ds.path] = agginfo

    if not objid:
        # this is no error, there is simply no metadata whatsoever
        return False

    # shorten to MD5sum
    objid = md5(objid.encode()).hexdigest()

    # assemble info on the metadata extraction and storage
    #               label  type      targetds    storage method
    metasources = {'ds': {'type': 'dataset', 'targetds': agginto_ds, 'dumper': json_py.dump}}
    # do not store content metadata if either the source or the target dataset
    # do not want it
    # TODO this AND was an OR before (wrong), misses a test
    if aggfrom_ds.config.obtain(
            'datalad.metadata.store-aggregate-content',
            default=True,
            valtype=EnsureBool()) and \
            agginto_ds.config.obtain(
                'datalad.metadata.store-aggregate-content',
                default=True,
                valtype=EnsureBool()):
            metasources['cn'] = {
                'type': 'content',
                'targetds': agginto_ds,
                'dumper': json_py.dump2xzstream}

    # check if we have the extracted metadata for this state already
    # either in the source or in the destination dataset
    # The situation is trickier!  Extracted metadata could change for the same
    # state (commit etc), e.g. if extractors changed.
    # The "correct" thing would be either
    # - to inspect git history either there were changes
    #   within aggfrom_ds since agginto_ds got the metadata committed OR
    # - check by content - if file is under git - compute checksum,
    #   if under annex -- take checksum from the key without asking for the
    #   content
    metafound = {}
    uptodatemeta = []  # record which meta not only found but matching in content
    # TODO: current fixes might break logic for when fromds is not installed
    #       when I guess we just need to skip it?
    if not force_extraction:
        for s, sprop in metasources.items():
            objloc = op.join(agg_base_path,
                             _get_obj_location(objid, s, sprop['dumper']))
            smetafound = [
                # important to test for lexists() as we do not need to
                # or want to `get()` metadata files for this test.
                # Info on identity is NOT sufficient - later compare content if
                # multiple found
                objloc if op.lexists(op.join(d.path, objloc)) else None
                # Order of dss matters later
                for d in (aggfrom_ds, agginto_ds)
            ]
            if all(smetafound):
                # both have it
                metafound[s] = smetafound
                # but are they the same?
                try:
                    if _the_same_across_datasets(objloc, aggfrom_ds, agginto_ds):
                        uptodatemeta.append(s)
                except RuntimeError as exc:
                    # TODO: dedicated test - when meta content changes
                    lgr.debug("For now will just do re-extraction since caught %s",
                              CapturedException(exc))
            # source one has it, so we might be able to copy it
            # TODO: dedicated test - when it is sufficient to copy we do not re-extract

    if len(metafound) != len(metasources):
        # found some (either ds or cn) metadata missing entirely in both
        # from and into datasets
        lgr.debug(
            "Incomplete or absent metadata while aggregating %s <- %s: %s",
              agginto_ds, aggfrom_ds, metafound
        )
        # no metadata found -> extract
        # this places metadata dump files into the configured
        # target dataset and lists them in `to_save`, as well
        # as updates the `db` record for `aggfrom_ds`
        return _extract_metadata(
            agginto_ds,
            aggfrom_ds,
            db,
            to_save,
            objid,
            metasources,
            refcommit,
            subds_relpaths,
            agg_base_path)

    # we did not actually run an extraction, so we need to
    # assemble an aggregation record from the existing pieces
    # that we found
    # simple case: the target dataset has all the records already and they are up to date:
    if len(uptodatemeta) == len(metasources):
        lgr.debug('Sticking with up-to-date metadata for %s', aggfrom_ds)
        # no change, use old record from the target dataset
        db[aggfrom_ds.path] = old_agginfo
        # no error
        return False
    else:
        lgr.debug('Reusing previously extracted metadata for %s', aggfrom_ds)
        # we need to move the metadata dump(s) into the target dataset
        objrelpaths = {
            label: next(filter(bool, smetafound))
            for label, smetafound in metafound.items()
        }
        # make sure all the to-be-moved metadata records are present
        # locally
        aggfrom_ds.get(
            path=[op.join(aggfrom_ds.path, p)
                  for p in objrelpaths.values()],
            result_renderer='disabled')

        # actually copy dump files
        for objrelpath in objrelpaths.values():
            objpath = op.join(agginto_ds.path, objrelpath)
            objdir = op.dirname(objpath)
            if not op.exists(objdir):
                makedirs(objdir)
            if op.lexists(objpath):
                os.unlink(objpath)  # remove previous version first
                # was a wild thought as a workaround for 
                # http://git-annex.branchable.com/bugs/cannot_commit___34__annex_add__34__ed_modified_file_which_switched_its_largefile_status_to_be_committed_to_git_now/#comment-bf70dd0071de1bfdae9fd4f736fd1ec1
                # agginto_ds.repo.remove(objpath)
            # XXX TODO once we have a command that can copy/move files
            # from one dataset to another including file availability
            # info, this should be used here
            shutil.copyfile(
                op.join(aggfrom_ds.path, objrelpath),
                objpath)
            # mark for saving
            to_save.append(dict(
                path=objpath,
                parentds=agginto_ds.path,
                type='file'))

        # lastly get 'self' aggregation record from source dataset and
        # use in target dataset
        db[aggfrom_ds.path] = load_ds_aggregate_db(aggfrom_ds, abspath=True)[aggfrom_ds.path]
        return False


def _extract_metadata(agginto_ds, aggfrom_ds, db, to_save, objid, metasources,
                      refcommit, subds_relpaths, agg_base_path):
    lgr.debug('Performing metadata extraction from %s', aggfrom_ds)
    # we will replace any conflicting info on this dataset with fresh stuff
    agginfo = db.get(aggfrom_ds.path, {})
    # paths to extract from
    relevant_paths = sorted(_get_metadatarelevant_paths(aggfrom_ds, subds_relpaths))
    # get extractors to engage from source dataset
    nativetypes = ['datalad_core', 'annex'] + ensure_list(get_metadata_type(aggfrom_ds))
    # store essential extraction config in dataset record
    agginfo['extractors'] = nativetypes
    agginfo['datalad_version'] = datalad.__version__

    # perform the actual extraction
    dsmeta, contentmeta, errored = _get_metadata(
        aggfrom_ds,
        nativetypes,
        # None indicates to honor a datasets per-extractor configuration and to be
        # on by default
        global_meta=None,
        content_meta=None,
        paths=relevant_paths)

    meta = {
        'ds': dsmeta,
        'cn': (dict(contentmeta[k], path=k) for k in sorted(contentmeta))
    }

    # inject the info which commit we are describing into the core metadata
    # this is done here in order to avoid feeding it all the way down
    coremeta = dsmeta.get('datalad_core', {})
    version = aggfrom_ds.repo.describe(commitish=refcommit)
    if version:
        coremeta['version'] = version
    coremeta['refcommit'] = refcommit
    dsmeta['datalad_core'] = coremeta

    # for both types of metadata
    for label, props in metasources.items():
        dest = props['targetds']
        if not meta[label]:
            continue
        # only write to disk if there is something
        objrelpath = _get_obj_location(objid, label, props['dumper'])
        # place metadata object into the source dataset
        objpath = op.join(dest.path, agg_base_path, objrelpath)

        # write obj files
        if op.exists(objpath):
            dest.unlock(objpath)
        elif op.lexists(objpath):
            # if it gets here, we have a symlink that is pointing nowhere
            # kill it, to be replaced with the newly aggregated content
            dest.repo.remove(objpath)
        # TODO actually dump a compressed file when annexing is possible
        # to speed up on-demand access
        props['dumper'](meta[label], objpath)
        # stage for dataset.save()
        to_save.append(dict(path=objpath, type='file'))

        # important to use abspath here, needs to be rewritten relative to
        # all receiving datasets
        agginfo['{}_info'.format(props['type'])] = objpath

    # overwrite existing info with stuff from just finished extraction
    db[aggfrom_ds.path] = agginfo

    return errored


def _adj2subtrees(base, adj, subs):
    # given a set of parent-child mapping, compute a mapping of each parent
    # to all its (grand)children of any depth level
    subtrees = dict(adj)
    subs = set(subs)
    # from bottom up
    for ds in sorted(adj, reverse=True):
        subtree = []
        for sub in subtrees[ds]:
            subtree.append(sub)
            subtree.extend(subtrees.get(sub, []))
        subtrees[ds] = subtree
    # give each leaf dataset an entry too
    for sub in subs:
        if sub not in subtrees and GitRepo.is_valid_repo(sub):
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
        for rp in [op.join(basepath, p) if basepath else p for p in paths]:
            if rp in exclude:
                continue
            elif any(path_is_subpath(ep, rp) for ep in exclude):
                final_paths.extend(
                    _filterpaths(rp, listdir(op.join(ds.path, rp)), exclude))
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

    return ds.repo.get_last_commit_hexsha(relevant_paths)


def _get_obj_location(hash_str, ref_type, dumper):
    objrelpath = op.join(
        'objects',
        hash_str[:2],
        '{}-{}'.format(
            ref_type,
            hash_str[2:]))

    if dumper is json_py.dump2xzstream:
        objrelpath += '.xz'

    return objrelpath


def _update_ds_agginfo(refds_path, ds_path, subds_paths, incremental, agginfo_db, to_save):
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
      whose agginfo shall be updated within the to-be-updated dataset.
      Any subdataset that is not listed here is assumed to be gone (i.e. no longer
      a subdataset at all, not just not locally installed)
    incremental : bool
      If set, the update will not remove any information on datasets not listed in
      subds_paths
    agginfo_db : dict
      Dictionary with all information on aggregate metadata on all datasets.
      Keys are absolute paths of datasets.
    to_save : list
      List of paths to save eventually. This function will add new paths as
      necessary.
    """
    ds = Dataset(ds_path)
    # load existing aggregate info dict
    # makes sure all file/dataset paths become absolute
    # TODO take from cache, once used in _get_dsinfo_from_aggmetadata()
    agginfo_fpath, agg_base_path = get_ds_aggregate_db_locations(ds)
    ds_agginfos = load_ds_aggregate_db(ds, abspath=True)
    # object locations referenced initially
    objlocs_was = set(ai[k]
                      for ai in ds_agginfos.values()
                      for k in location_keys
                      if k in ai)
    # track which objects need to be copied (each item is a from/to tuple
    objs2copy = []
    # for each subdataset (any depth level)
    procds_paths = [ds.path] + subds_paths
    for dpath in procds_paths:
        ds_dbinfo = agginfo_db.get(dpath, {}).copy()
        # relative path of the current dataset within the dataset we are updating
        drelpath = op.relpath(dpath, start=ds.path)
        for loclabel in location_keys:
            # TODO filepath_info is obsolete
            if loclabel == 'filepath_info' and drelpath == op.curdir:
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
            target_objpath = op.join(agg_base_path, *objloc.split(os.sep)[-3:])
            # make sure we copy the file from its current location to where it is
            # needed in this dataset
            objs2copy.append((
                # this needs to turn into an absolute path
                # `dpath` will be relative to the reference dataset
                #op.normpath(op.join(ds.path, dpath, op.dirname(agginfo_relpath), objloc)),
                objloc,
                target_objpath))
            # now build needed local relpath
            ds_dbinfo[loclabel] = target_objpath
        # (re)assign in case record is new
        ds_agginfos[dpath] = ds_dbinfo
    # remove all entries for which we did not (no longer) have a corresponding
    # subdataset to take care of
    if not incremental:
        ds_agginfos = {k: v
                       for k, v in ds_agginfos.items()
                       if k in procds_paths}
    # set of metadata objects now referenced
    objlocs_is = set(
        ai[k]
        for sdsrpath, ai in ds_agginfos.items()
        for k in location_keys
        if k in ai)
    objs2add = objlocs_is

    # yoh: we appanretly do need to filter the ones to remove - I did
    #      "git reset --hard HEAD^" and
    #      aggregate-metadata failed upon next run trying to remove
    #      an unknown to git file. I am yet to figure out why that
    #      mattered (hopefully not that reflog is used somehow)
    objs2remove = []
    for obj in objlocs_was.difference(objlocs_is):
        if op.lexists(obj):
            objs2remove.append(obj)
        else:
            # not really a warning, we don't need it anymore, it is already gone
            lgr.debug(
                "To-be-deleted metadata object not found, skip deletion (%s)",
                obj
            )

    # secretly remove obsolete object files, not really a result from a
    # user's perspective
    if not incremental and objs2remove:
        ds.remove(
            objs2remove,
            # Don't use the misleading default commit message of `remove`:
            message='[DATALAD] Remove obsolete metadata object files',
            # we do not want to drop these files by default, because we would
            # loose them for other branches, and earlier tags
            # TODO evaluate whether this should be exposed as a switch
            # to run an explicit force-drop prior to calling remove()
            reckless='kill',
            result_renderer='disabled',
            return_type='list')
        if not objs2add and not refds_path == ds_path:
            # this is not the base dataset, make sure to save removal in the
            # parentds -- not needed when objects get added, as removal itself
            # is already committed
            to_save.append(dict(path=ds_path, type='dataset', staged=True))

    objs2copy = [(f, t) for f, t in objs2copy if f != t]
    # must copy object files to local target destination
    # make sure those objects are present
    # use the reference dataset to resolve paths, as they might point to
    # any location in the dataset tree
    Dataset(refds_path).get(
        [f for f, t in objs2copy],
        result_renderer='disabled')
    for copy_from, copy_to in objs2copy:
        copy_from = op.join(agg_base_path, copy_from)
        copy_to = op.join(agg_base_path, copy_to)
        target_dir = op.dirname(copy_to)
        if not op.exists(target_dir):
            makedirs(target_dir)
        # TODO we could be more clever (later) and maybe `addurl` (or similar)
        # the file from another dataset
        if op.lexists(copy_to):
            # no need to unlock, just wipe out and replace
            os.remove(copy_to)
        shutil.copy(copy_from, copy_to)
    to_save.append(
        dict(path=agginfo_fpath, type='file', staged=True))

    if objs2add:
        # they are added standard way, depending on the repo type
        ds.repo.add([op.join(agg_base_path, p) for p in objs2add])
        # queue for save, and mark as staged
        to_save.extend(
            [dict(path=op.join(agg_base_path, p), type='file', staged=True)
             for p in objs2add])
    # write aggregate info file
    if not ds_agginfos:
        return

    _store_agginfo_db(ds, ds_agginfos)
    ds.repo.add(agginfo_fpath, git=True)
    # queue for save, and mark as staged
    to_save.append(
        dict(path=agginfo_fpath, type='file', staged=True))

    # FIXME look for empty object dirs and remove them


def _store_agginfo_db(ds, db):
    # base path in which aggregate.json and objects is located
    agginfo_path, agg_base_path = get_ds_aggregate_db_locations(
        ds, warn_absent=False)
    # make DB paths on disk always relative
    json_py.dump(
        {
            op.relpath(p, start=ds.path):
            {k: op.relpath(v, start=agg_base_path) if k in location_keys else v
             for k, v in props.items()}
            for p, props in db.items()
        },
        agginfo_path
    )


@build_doc
class AggregateMetaData(Interface):
    """Aggregate metadata of one or more datasets for later query.

    Metadata aggregation refers to a procedure that extracts metadata present
    in a dataset into a portable representation that is stored a single
    standardized format. Moreover, metadata aggregation can also extract
    metadata in this format from one dataset and store it in another
    (super)dataset. Based on such collections of aggregated metadata it is
    possible to discover particular datasets and specific parts of their
    content, without having to obtain the target datasets first (see the
    DataLad 'search' command).

    To enable aggregation of metadata that are contained in files of a dataset,
    one has to enable one or more metadata extractor for a dataset. DataLad
    supports a number of common metadata standards, such as the Exchangeable
    Image File Format (EXIF), Adobe's Extensible Metadata Platform (XMP), and
    various audio file metadata systems like ID3. DataLad extension packages
    can provide metadata data extractors for additional metadata sources. For
    example, the neuroimaging extension provides extractors for scientific
    (meta)data standards like BIDS, DICOM, and NIfTI1.  Some metadata
    extractors depend on particular 3rd-party software. The list of metadata
    extractors available to a particular DataLad installation is reported by
    the 'wtf' command ('datalad wtf').

    Enabling a metadata extractor for a dataset is done by adding its name to the
    'datalad.metadata.nativetype' configuration variable -- typically in the
    dataset's configuration file (.datalad/config), e.g.::

      [datalad "metadata"]
        nativetype = exif
        nativetype = xmp

    If an enabled metadata extractor is not available in a particular DataLad
    installation, metadata extraction will not succeed in order to avoid
    inconsistent aggregation results.

    Enabling multiple extractors is supported. In this case, metadata are
    extracted by each extractor individually, and stored alongside each other.
    Metadata aggregation will also extract DataLad's own metadata (extractors
    'datalad_core', and 'annex').

    Metadata aggregation can be performed recursively, in order to aggregate all
    metadata across all subdatasets, for example, to be able to search across
    any content in any dataset of a collection. Aggregation can also be performed
    for subdatasets that are not available locally. In this case, pre-aggregated
    metadata from the closest available superdataset will be considered instead.

    Depending on the versatility of the present metadata and the number of dataset
    or files, aggregated metadata can grow prohibitively large. A number of
    configuration switches are provided to mitigate such issues.

    datalad.metadata.aggregate-content-<extractor-name>
      If set to false, content metadata aggregation will not be performed for
      the named metadata extractor (a potential underscore '_' in the extractor name must
      be replaced by a dash '-'). This can substantially reduce the runtime for
      metadata extraction, and also reduce the size of the generated metadata
      aggregate. Note, however, that some extractors may not produce any metadata
      when this is disabled, because their metadata might come from individual
      file headers only. 'datalad.metadata.store-aggregate-content' might be
      a more appropriate setting in such cases.

    datalad.metadata.aggregate-ignore-fields
      Any metadata key matching any regular expression in this configuration setting
      is removed prior to generating the dataset-level metadata summary (keys
      and their unique values across all dataset content), and from the dataset
      metadata itself. This switch can also be used to filter out sensitive
      information prior aggregation.

    datalad.metadata.generate-unique-<extractor-name>
      If set to false, DataLad will not auto-generate a summary of unique content
      metadata values for a particular extractor as part of the dataset-global metadata
      (a potential underscore '_' in the extractor name must be replaced by a dash '-').
      This can be useful if such a summary is bloated due to minor uninformative (e.g.
      numerical) differences, or when a particular extractor already provides a
      carefully designed content metadata summary.

    datalad.metadata.maxfieldsize
      Any metadata value that exceeds the size threshold given by this configuration
      setting (in bytes/characters) is removed.

    datalad.metadata.store-aggregate-content
      If set, extracted content metadata are still used to generate a dataset-level
      summary of present metadata (all keys and their unique values across all
      files in a dataset are determined and stored as part of the dataset-level
      metadata aggregate, see datalad.metadata.generate-unique-<extractor-name>),
      but metadata on individual files are not stored.
      This switch can be used to avoid prohibitively large metadata files. Discovery
      of datasets containing content matching particular metadata properties will
      still be possible, but such datasets would have to be obtained first in order
      to discover which particular files in them match these properties.
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""topmost dataset metadata will be aggregated into. All dataset
            between this dataset and any given path will receive updated
            aggregated metadata from all given paths.""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path to datasets that shall be aggregated.
            When a given path is pointing into a dataset, the metadata of the
            containing dataset will be aggregated.  If no paths given, current
            dataset metadata is aggregated.""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        update_mode=Parameter(
            args=('--update-mode',),
            constraints=EnsureChoice('all', 'target'),
            doc="""which datasets to update with newly aggregated metadata:
            all datasets from any leaf dataset to the top-level target dataset
            including all intermediate datasets (all), or just the top-level
            target dataset (target)."""),
        incremental=Parameter(
            args=('--incremental',),
            action='store_true',
            doc="""If set, all information on metadata records of subdatasets
            that have not been (re-)aggregated in this run will be kept unchanged.
            This is useful when (re-)aggregation only a subset of a dataset hierarchy,
            for example, because not all subdatasets are locally available."""),
        force_extraction=Parameter(
            args=('--force-extraction',),
            action='store_true',
            doc="""If set, all enabled extractors will be engaged regardless of
            whether change detection indicates that metadata has already been
            extracted for a given dataset state."""),
        save=nosave_opt,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    @eval_results
    def __call__(
            path=None,
            *,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            update_mode='target',
            incremental=False,
            force_extraction=False,
            save=True):
        refds_path = require_dataset(dataset)

        # it really doesn't work without a dataset
        ds = require_dataset(
            dataset, check_installed=True, purpose='metadata aggregation')
        path = ensure_list(path)
        if not path:
            # then current/reference dataset is "aggregated"
            # We should not add ds.path always since then --recursive would
            # also recurse current even if paths are given
            path.append(ds.path)

        agginfo_db_location, agg_base_path = get_ds_aggregate_db_locations(
            ds,
            # do not warn here, next call triggers the same warning
            warn_absent=False)
        agginfo_db = load_ds_aggregate_db(ds, abspath=True)

        to_save = []
        to_aggregate = set()
        paths_by_ds, errors = get_paths_by_ds(
            require_dataset(dataset),
            dataset,
            paths=ensure_list(path),
            subdsroot_mode='super')
        for ap in _minimal_annotate_paths(
                paths_by_ds,
                errors,
                action='aggregate_metadata',
                recursive=recursive,
                recursion_limit=recursion_limit):
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
                errored = _dump_extracted_metadata(
                    ds,
                    Dataset(aggsrc),
                    agginfo_db,
                    to_save,
                    force_extraction,
                    agg_base_path)
                if errored:
                    yield get_status_dict(
                        status='error',
                        message='Metadata extraction failed (see previous error message, set datalad.runtime.raiseonerror=yes to fail immediately)',
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
        # get adjencency info of the dataset tree spanning the base to all leaf dataset
        # associated with the path arguments
        if update_mode == 'all':
            ds_adj = {}
            discover_dataset_trace_to_targets(
                ds.path, to_aggregate, [], ds_adj,
                # we know that to_aggregate only lists datasets, existing and
                # absent ones -- we want to aggregate all of them, either from
                # just extracted metadata, or from previously aggregated metadata
                # of the closest superdataset
                includeds=to_aggregate)
            # TODO we need to work in the info about dataset that we only got from
            # aggregated metadata, that had no trace on the file system in here!!
            subtrees = _adj2subtrees(ds.path, ds_adj, to_aggregate)
        elif update_mode == 'target':
            subtrees = {ds.path: list(agginfo_db.keys())}
        else:
            raise ValueError(
                "unknown `update_mode` '%s' for metadata aggregation", update_mode)

        # go over datasets in bottom-up fashion
        for parentds_path in sorted(subtrees, reverse=True):
            lgr.info('Update aggregate metadata in dataset at: %s', parentds_path)

            _update_ds_agginfo(
                ds.path,
                parentds_path,
                subtrees[parentds_path],
                incremental,
                agginfo_db,
                to_save)
            # update complete
            res = get_status_dict(
                status='ok',
                action='aggregate_metadata',
                path=parentds_path,
                type='dataset',
                logger=lgr)
            res.update(agginfo_db.get(parentds_path, {}))
            yield res
        #
        # save potential modifications to dataset global metadata
        #
        if not to_save:
            return
        lgr.info('Attempting to save %i files/datasets', len(to_save))
        for res in Save.__call__(
                # save does not need any pre-annotated path hints
                path=[r['path'] for r in to_save],
                dataset=refds_path,
                message='[DATALAD] Dataset aggregate metadata update',
                return_type='generator',
                result_renderer='disabled',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res
