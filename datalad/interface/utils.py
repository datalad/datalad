# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface utility functions

"""

__docformat__ = 'restructuredtext'

import logging
import os
from os import curdir
from os import pardir
from os.path import join as opj
from os.path import lexists
from os.path import isabs
from os.path import isdir
from os.path import dirname
from os.path import normpath
from os.path import relpath
from os.path import sep
from os.path import split as psplit
from itertools import chain

from datalad.dochelpers import exc_str
# avoid import from API to not get into circular imports
from datalad.utils import with_pathsep as _with_sep  # TODO: RF whenever merge conflict is not upon us
from datalad.utils import assure_list
from datalad.utils import get_trace
from datalad.utils import walk
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path
from datalad.distribution.utils import _install_subds_inplace
from datalad.distribution.utils import get_git_dir


lgr = logging.getLogger('datalad.interface.utils')


def handle_dirty_dataset(ds, mode, msg=None):
    """Detect and treat unsaved changes as instructed by `mode`

    Parameters
    ----------
    ds : Dataset or None
      Dataset to be inspected. Does nothing if `None`.
    mode : {'fail', 'ignore', 'save-before'}
      How to act upon discovering unsaved changes.
    msg : str or None
      Custom message to use for a potential commit.

    Returns
    -------
    None
    """
    if ds is None:
        # nothing to be handled
        return
    if msg is None:
        msg = '[DATALAD] auto-saved changes'

    # make sure that all pending changes (batched annex operations, etc.)
    # are actually reflected in Git
    if ds.repo:
        ds.repo.precommit()

    if mode == 'ignore':
        return
    elif mode == 'fail':
        if not ds.repo or ds.repo.repo.is_dirty(index=True,
                                                working_tree=True,
                                                untracked_files=True,
                                                submodules=True):
            raise RuntimeError('dataset {} has unsaved changes'.format(ds))
    elif mode == 'save-before':
        if not ds.is_installed():
            raise RuntimeError('dataset {} is not yet installed'.format(ds))
        from datalad.interface.save import Save
        Save.__call__(dataset=ds, message=msg, all_changes=True)
    else:
        raise ValueError("unknown if-dirty mode '{}'".format(mode))


def handle_dirty_datasets(dpaths,
                          mode,
                          base=None,
                          msg='[DATALAD] auto-saved changes'):
    """Detect and treat unsaved changes as instructed by `mode`

    Parameters
    ----------
    dpaths : sequence(path)
      Dataset to be inspected. Does nothing if `None`.
    mode : {'fail', 'ignore', 'save-before'}
      How to act upon discovering unsaved changes.
    base : path or None, optional
      Path of a common super dataset that should also be handled.
    msg : str
      Custom message to use for a potential saved state.

    Returns
    -------
    None
    """
    if mode == 'save-before':
        save_dataset_hierarchy(
            {d: d for d in dpaths},
            base=base,
            message=msg)
    elif mode == 'ignore':
        return
    elif mode == 'fail':
        for dpath in dpaths:
            ds = Dataset(dpath)
            if not ds.repo:
                continue
            ds.repo.precommit()
            if ds.repo.repo.is_dirty(index=True,
                                     working_tree=True,
                                     untracked_files=True,
                                     submodules=True):
                raise RuntimeError(
                    'dataset {} has unsaved changes'.format(ds))
    else:
        raise ValueError("unknown if-dirty mode '{}'".format(mode))


def get_tree_roots(paths):
    """Return common root paths for a set of paths

    This function determines the smallest set of common root
    paths and sorts all given paths under the respective
    root.

    Returns
    -------
    dict
      paths by root
    """
    paths_ws = [_with_sep(p) for p in paths]
    # sort all paths under their potential roots
    roots = {}
    # start from the top to get all paths down the line
    # and collate them into as few roots as possible
    for s in sorted(paths_ws):
        if any([s.startswith(r) for r in roots]):
            # this path is already covered by a known root
            continue
        # find all sub paths
        subs = [p for p in paths if p.startswith(s)]
        roots[s.rstrip(sep)] = subs
    return roots


def sort_paths_into_subdatasets(superds_path, target_subs, spec):
    # XXX forge a chain: whenever some path needs to be pushed down
    # put the receiving dataset as a components to process into the
    # respective superdataset -- this will enable further processing
    # of all datasets in a completely independent fashion
    # (except for order of processing)

    # get all existing subdataset as candidate nodes of the graph
    # that needs to be built and checked
    subds_graph = Dataset(superds_path).get_subdatasets(
        absolute=True, recursive=True, edges=True, fulfilled=True)
    for t in target_subs:
        trace = get_trace(
            subds_graph,
            # need to strip separator to make `==` work
            superds_path,
            t)
        tosort = [superds_path] + trace + [t]
        # loop over all but the last one, simplifies logic below
        for i, d in enumerate(tosort[:-1]):
            paths = spec.get(d, [])
            keep_paths = []
            next_ds = tosort[i + 1]
            next_dspaths = spec.get(next_ds, [])
            comp = _with_sep(next_ds)
            for p in assure_list(paths):
                if p.startswith(comp):
                    next_dspaths.append(p)
                    # remember that we pushed the path into this dataset
                    keep_paths.append(next_ds)
                else:
                    keep_paths.append(p)
            spec[next_ds] = next_dspaths
            spec[d] = keep_paths


def save_dataset_hierarchy(
        info,
        base=None,
        message='[DATALAD] saved changes',
        version_tag=None):
    """Save (disjoint) hierarchies of datasets.

    Saving is done in an order that guarantees that all to be saved
    datasets reflect any possible change of any other to be saved
    subdataset, before they are saved themselves.

    Parameters
    ----------
    info : dict
      Absolute paths of datasets to be saved are the keys, and paths in each
      dataset to be saved are the values
    base : path or None, optional
      Common super dataset that should also be saved.
    message : str
      Message to be used for saving individual datasets

    Returns
    -------
    list
      Instances of saved datasets, in the order in which they where saved.
    """
    if not isinstance(info, dict):
        info = assure_list(info)
        info = dict(zip(info, [[i] for i in info]))
    print('INFUCK', info)
    # TODO check if `add` can do this and move there if necessary
    #if all_changes:
    #    # we need to make sure to register all possibly untracked subdatasets
    #    # before we build the dataset graph tell can tell us in which order
    #    # things need to be processed
    #    toprocess = assure_list(info.keys())
    #    if not toprocess and base:
    #        # only there arn't any specific base dataset pieces given to process
    #        # consider the entire dataset too
    #        toprocess.append(base.path if isinstance(base, Dataset) else base)
    #    while toprocess:
    #        dpath = toprocess.pop()
    #        new_submodules = untracked_subdatasets_to_submodules(
    #            Dataset(dpath),
    #            info[dpath] if dpath in info else [])
    #        for ns in new_submodules:
    #            dsinfo = info.get(ns, [])
    #            dsinfo.append(ns)
    #            info[ns] = dsinfo
    #            # make sure to look at any new ones too
    #            toprocess.append(ns)
    dpaths = info.keys()
    if base:
        # just a convenience...
        dpaths = assure_list(dpaths)
        dpaths.append(base.path if isinstance(base, Dataset) else base)
    # sort all datasets under their potential superdatasets
    # start from the top to get all subdatasets down the line
    # and collate them into as few superdatasets as possible
    superdss = get_tree_roots(dpaths)
    # for each "superdataset" check the tree of subdatasets and make sure
    # we gather all datasets between the super and any subdataset
    # so we can save them all bottom-up in order to be able to properly
    # save the superdataset
    tocheck = set(dpaths)
    for superds_path in superdss:
        target_subs = superdss[superds_path]
        sort_paths_into_subdatasets(superds_path, target_subs, info)
    # iterate over all datasets, starting at the bottom
    saved = []
    print('INFO', info)
    for dpath in sorted(info.keys(), reverse=True):
        ds = Dataset(dpath)
        if ds.is_installed():
            saved_state = save_dataset(
                ds,
                info[dpath],
                message=message,
                version_tag=version_tag)
            if saved_state:
                saved.append(ds)
    return saved


def save_dataset(
        ds,
        paths=None,
        message=None,
        version_tag=None):
    """Save changes in a single dataset.

    Parameters
    ----------
    ds : Dataset
      The dataset to be saved.
    paths : list, optional
      Paths to dataset components to be saved.
    message: str, optional
      (Commit) message to be attached to the saved state.
    version_tag : str, optional
      Tag to be assigned to the saved state.

    Returns
    -------
    bool
      Whether a new state was saved. If all to be saved content was unmodified
      no new state will be saved.
    """
    # XXX paths must be in the given ds, no further sanity checks!

    # make sure that all pending changes (batched annex operations, etc.)
    # are actually reflected in Git
    ds.repo.precommit()

    # track what is to be committed, so it becomes
    # possible to decide when/what to save further down
    # and one level up
    orig_hexsha = ds.repo.get_hexsha()

    ## TODO this needs to go into `add`
    #new_submodules = untracked_subdatasets_to_submodules(
    #    ds, files)
    #if new_submodules:
    #    # make sure that .gitmodules is added to the list of files
    #    # to be committed.  Adding to index might not be enough iff
    #    # custom files was provided
    #    to_commit.append('.gitmodules')
    #to_commit.extend(new_submodules)

    # always yields list; empty if None
    files = list(
        set(
            [opj(ds.path, f) if not isabs(f) else f for f in assure_list(paths)]))

    if not files:
        return False

    # try to consider existing and changed files, and prevent untracked
    # files from being added
    # XXX not acting upon untracked files would be very expensive, because
    # I see no way to avoid using `add` below and git annex has no equivalent
    # to git add's --update -- so for now don't bother
    # XXX alternatively we could consider --no-ignore-removal to also
    # have it delete any already vanished files
    # asking yourself why we need to `add` at all? For example, freshly
    # unlocked files in a v5 repo are listed as "typechange" and commit
    # refuses to touch them without an explicit `add`
    if isinstance(ds.repo, AnnexRepo):
        # to make this work without calling `git add` in addition,
        # this needs git-annex v6.20161210 (see #1027)
        ds.repo.add(files, commit=False)
    else:
        # --update will ignore any untracked files, sadly git-annex add
        # above does not
        ds.repo.add(files, git_options=['--update'], commit=False)

    _datalad_msg = False
    if not message:
        message = 'Recorded existing changes'
        _datalad_msg = True

    # TODO: commit() should rather report a dedicated ValueError
    # waiting for #1170
    from datalad.support.exceptions import CommandError
    try:
        ds.repo.commit(message, options=files, _datalad_msg=_datalad_msg)
    except CommandError as e:
        # TODO until #1171 is resolved, test here for "normal" failure to commit
        if 'nothing to commit' in str(e):
            lgr.warning(
                "Was instructed to commit %s files but repository is not dirty",
                files)
        elif 'no changes added to commit':
            lgr.info(
                'Nothing to save')
        else:
            raise ValueError(e)

    # MIH: let's tag even if there was nothing commit. I'd forget this
    # option too often...
    if version_tag:
        ds.repo.tag(version_tag)

    _was_modified = ds.repo.get_hexsha() != orig_hexsha

    return ds.repo.repo.head.commit if _was_modified else None


def amend_pathspec_with_superdatasets(spec, topmost=True):
    """Amend a path spec dictionary with entries for superdatasets

    The result will be a superdataset entry (if a superdataset exists)
    for each input dataset. This entry will (at least) contain the path
    to the subdataset.

    Parameters
    ----------
    spec : dict
      Path spec
    topmost : Dataset or bool
      Flag whether to grab the immediate, or the top-most superdataset
      for each entry, alternatively this can be a dataset instance
      that is used as the topmost dataset. If no superdataset matches
      this specific dataset the absolute topmost is used instead.
    Returns
    -------
    dict
      Amended path spec dictionary
    """
    superdss = {}
    for dpath in spec.keys():
        if isinstance(topmost, Dataset) \
                and dpath.startswith(_with_sep(topmost.path)):
            # the given topmost dataset is "above" the current
            # datasets path
            superds = topmost
        else:
            # grab the (topmost) superdataset
            superds = Dataset(dpath).get_superdataset(
                datalad_only=True, topmost=topmost)
        if not superds:
            continue
        # register the subdatasets path in the spec of the superds
        spaths = superdss.get(superds.path, [])
        if not spaths:
            spaths = spec.get(superds.path, [])
        spaths.append(dpath)
        superdss[superds.path] = spaths
    spec.update(superdss)
    return spec


def untracked_subdatasets_to_submodules(ds, consider_paths):
    # treat special case of still untracked subdatasets.
    # those need to become submodules now, as they are otherwise added
    # without an entry in .gitmodules, and subsequently break Git's
    # submodule functionality completely
    dspath = ds.path
    new_modules = []
    if not consider_paths:
        # nothing to test
        return new_modules

    # we cannot ask for "untracked_files", because that requires a working tree
    # that could be expensive to obtain in direct mode repos
    # so a different approach....

    # get a list of all directories (abspath) with content known to git
    # this will include mount points of known subdatasets
    indexed_dirs = set([opj(ds.path, f if isdir(opj(ds.path, f)) else dirname(f))
                        for f in ds.repo.get_indexed_files()])
    # now get all the actual directories in this dataset
    existing_dirs = set([d for testpath in consider_paths
                         for d in get_dataset_directories(testpath,
                                                          ignore_datalad=True)
                         # do not probe for paths in subdatasets
                         if GitRepo.get_toppath(testpath) == ds.path])
    # the difference are directories that could be an untracked subdataset
    subds_candidates = existing_dirs.difference(indexed_dirs)
    for cand_dspath in subds_candidates:
        if not Dataset(cand_dspath).is_installed():
            # this is not the top of an actual dataset
            continue
        _install_subds_inplace(
            ds=ds,
            path=cand_dspath,  # can be ignored, we don't need the return value
            relativepath=relpath(cand_dspath, start=ds.path),
            name=None)
        new_modules.append(cand_dspath)

    return new_modules


def get_paths_by_dataset(paths, recursive=False, recursion_limit=None,
                         out=None, dir_lookup=None):
    """Sort a list of paths per dataset they are contained in.

    Any paths that are not part of a dataset, or presently unavailable are
    reported.

    Parameter
    ---------
    paths : sequence
      A sequence of path specifications to sort.
    recursive : bool
      Flag whether to report subdatasets under any of the given paths
    recursion_limit :
      Depth constraint for recursion. See `Dataset.get_subdatasets()` for more
      information.
    out : dict or None
      By default a new output dictionary is created, however an existing one
      can be provided via this argument to enable incremental processing.
    dir_lookup : dict or None
      Optional lookup cache that maps paths to previously determined datasets.
      This can speed up repeated processing.

    Returns
    -------
    Tuple(dict, list, list)
      Dict of `existing dataset path`: `path` mappings, the list of currently
      non-existing paths (possibly matching currently uninstalled datasets),
      and any paths that are not part of any dataset.
    """
    # sort paths into the respective datasets
    if dir_lookup is None:
        dir_lookup = {}
    if out is None:
        out = {}
    # paths that don't exist (yet)
    unavailable_paths = []
    nondataset_paths = []
    for path in paths:
        if not lexists(path):
            # not there yet, impossible to say which ds it will actually
            # be in, if any
            unavailable_paths.append(path)
            continue
        # the path exists in some shape or form
        if isdir(path):
            # this could contain all types of additional content
            d = path
        else:
            # for everything else we are interested in the container
            d = dirname(path)
            if not d:
                d = curdir
        # this could be `None` if there is no git repo
        dspath = dir_lookup.get(d, GitRepo.get_toppath(d))
        dir_lookup[d] = dspath
        if not dspath:
            nondataset_paths.append(path)
            continue
        if isdir(path):
            ds = Dataset(dspath)
            # we need to doublecheck that this is not a subdataset mount
            # point, in which case get_toppath() would point to the parent
            smpath = ds.get_containing_subdataset(
                path, recursion_limit=1).path
            if smpath != dspath:
                # fix entry
                dir_lookup[d] = smpath
                # submodule still needs to be obtained
                unavailable_paths.append(path)
                continue
            if recursive:
                # make sure we get everything relevant in all _checked out_
                # subdatasets, obtaining of previously unavailable subdataset
                # else done elsewhere
                subs = ds.get_subdatasets(fulfilled=True,
                                          recursive=recursive,
                                          recursion_limit=recursion_limit)
                for sub in subs:
                    subdspath = opj(dspath, sub)
                    if subdspath.startswith(_with_sep(path)):
                        # this subdatasets is underneath the search path
                        # we want it all
                        # be careful to not overwrite anything, in case
                        # this subdataset has been processed before
                        out[subdspath] = out.get(
                            subdspath,
                            [subdspath])
        out[dspath] = out.get(dspath, []) + [path]
    return out, unavailable_paths, nondataset_paths


def get_normalized_path_arguments(paths, dataset=None, default=None):
    """Apply standard resolution to path arguments

    This is nothing more than a helper to standardize path argument
    preprocessing.

    Parameter
    ---------
    paths : sequence or single path
      Path(s) to normalize
    dataset : path or Dataset or None
      Optional dataset identifying something against which to resolve input
      path arguments
    default: sequence of paths or single path or None
      If `paths` is empty, use this instead

    Returns
    -------
    tuple(list(paths), path)
      Normalized paths and path to a potential dataset against which paths were
      resolved.
    """
    dataset_path = dataset.path if isinstance(dataset, Dataset) else dataset
    if not paths and default:
        paths = default
    paths = assure_list(paths)
    # resolve path(s):
    resolved_paths = [resolve_path(p, dataset) for p in paths]
    if dataset:
        # guarantee absolute paths
        resolved_paths = [opj(dataset_path, p) for p in resolved_paths]
    lgr.debug('Resolved input path arguments: %s', resolved_paths)
    return resolved_paths, dataset_path


def path_is_under(values, path=None):
    """Whether a given path is a subdirectory of any of the given test values

    Parameters
    ----------
    values : sequence or dict
      Paths to be tested against. This can be a dictionary in which case
      all values from all keys will be tested against.
    path : path or None
      Test path. If None is given, the process' working directory is
      used.

    Returns
    -------
    bool
    """
    if path is None:
        from datalad.utils import getpwd
        pwd = getpwd()
    if isinstance(values, dict):
        values = chain(*values.values())
    for p in values:
        rpath = relpath(p, start=pwd)
        if rpath == curdir \
                or rpath == pardir \
                or set(psplit(rpath)) == {pardir}:
            # first match is enough
            return True
    return False


def get_dataset_directories(top, ignore_datalad=True):
    """Return a list of directories in the same dataset under a given path

    Parameters
    ----------
    top : path
      Top-level path
    ignore_datalad : bool
      Whether to exlcude the '.datalad' directory of a dataset and its content
      from the results.

    Returns
    -------
    list
      List of directories matching the top-level path, regardless of whether
      these directories are known to Git (i.e. contain tracked files). The
      list does not include the top-level path itself, but it does include
      any subdataset mount points (regardless of whether the particular
      subdatasets are installed or not).
    """
    def func(arg, top, names):
        refpath, ignore, dirs = arg
        legit_names = []
        for n in names:
            path = opj(top, n)
            if not isdir(path) or path in ignore:
                pass
            elif GitRepo.get_toppath(path) != refpath:
                # mount point, keep but don't dive into
                dirs.append(path)
            else:
                legit_names.append(n)
                dirs.append(path)
        names[:] = legit_names

    # collects the directories
    refpath = GitRepo.get_toppath(top)
    if not refpath:
        raise ValueError("`top` path {} is not in a dataset".format(top))
    ignore = [opj(refpath, get_git_dir(refpath))]
    if ignore_datalad:
        ignore.append(opj(refpath, '.datalad'))
    d = []
    walk(top, func, (refpath, ignore, d))
    return d
