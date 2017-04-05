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

import inspect
import logging
import wrapt
import sys
from os import curdir
from os import pardir
from os import listdir
from os import linesep
from os.path import join as opj
from os.path import lexists
from os.path import isabs
from os.path import isdir
from os.path import dirname
from os.path import relpath
from os.path import sep
from os.path import split as psplit
from itertools import chain
from six import PY2

import json

# avoid import from API to not get into circular imports
from datalad.utils import with_pathsep as _with_sep  # TODO: RF whenever merge conflict is not upon us
from datalad.utils import assure_list
from datalad.utils import get_trace
from datalad.utils import walk
from datalad.utils import get_dataset_root
from datalad.utils import swallow_logs
from datalad.utils import better_wraps
from datalad.utils import unique
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import IncompleteResultsError
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path
from datalad.distribution.utils import get_git_dir
from datalad import cfg as dlcfg
from datalad.dochelpers import exc_str

from datalad.support.constraints import EnsureBool
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureCallable
from datalad.support.param import Parameter

from .base import Interface
from .base import update_docstring_with_parameters
from .base import alter_interface_docs_for_api
from .results import get_status_dict
from .results import known_result_xfms


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
        if not ds.repo or ds.repo.is_dirty(index=True,
                                           untracked_files=True,
                                           submodules=True):
            raise RuntimeError('dataset {} has unsaved changes'.format(ds))
    elif mode == 'save-before':
        if not ds.is_installed():
            raise RuntimeError('dataset {} is not yet installed'.format(ds))
        from datalad.interface.save import Save
        Save.__call__(dataset=ds, message=msg, all_updated=True)
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
        # TODO GENERATOR
        # new returns a generator and yields status dicts
        list(save_dataset_hierarchy(
            {d: [d] for d in dpaths},
            base=base,
            message=msg))
    elif mode == 'ignore':
        return
    elif mode == 'fail':
        for dpath in dpaths:
            ds = Dataset(dpath)
            if not ds.repo:
                continue
            ds.repo.precommit()
            if ds.repo.is_dirty(index=True,
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

    subds = Dataset(superds_path)

    # get all existing subdataset as candidate nodes of the graph
    # that needs to be built and checked
    # OPT TODO:  this is the expensive one!  e.g we might have a big
    #       hierarchy of datasets and interested in analyzing only a single
    #       target_subds -- now it gets the entire hierarchy first (EXPENSIVE)
    #       to look/check just one... bleh... and then even better -- would continue
    #       out of the loop if that dataset is already known
    #       Moreover possibly causing entire recursive traversal of sub-datasets
    #       multiple times if operating from some higher level super and sorted
    #       target_subds in multiple subs
    # Delay expensive operation
    subds_graph = None
    # so we first get immediate children, delaying even check for being fulfilled
    subdss = subds.subdatasets(recursive=False, fulfilled=None, result_xfm='paths')
    if not subdss:
        # no subdatasets, nothing to sort
        return
    for t in target_subs:
        if t in subdss and GitRepo.is_valid_repo(t):  # fastest possible test for "installed?"
            # immediate known kiddo
            continue
        if subds_graph is None:
            subds_graph = [(r['parentpath'], r['path'])
                           for r in Dataset(superds_path).subdatasets(
                           recursive=True, fulfilled=True)]

        trace = get_trace(
            subds_graph,
            superds_path,
            t)
        if not trace:
            # not connected, or identical
            continue
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
    # tidy up -- deduplicate
    for c in spec:
        spec[c] = unique(spec[c])


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
    dpaths = info.keys()
    if base:
        # just a convenience...
        dpaths = assure_list(dpaths)
        base_path = base.path if isinstance(base, Dataset) else base
        if base_path not in dpaths:
            dpaths.append(base_path)
    # sort all datasets under their potential superdatasets
    # start from the top to get all subdatasets down the line
    # and collate them into as few superdatasets as possible
    superdss = get_tree_roots(dpaths)
    # for each "superdataset" check the tree of subdatasets and make sure
    # we gather all datasets between the super and any subdataset
    # so we can save them all bottom-up in order to be able to properly
    # save the superdataset
    for superds_path in superdss:
        target_subs = superdss[superds_path]
        sort_paths_into_subdatasets(superds_path, target_subs, info)
    # iterate over all datasets, starting at the bottom
    for dpath in sorted(info.keys(), reverse=True):
        ds = Dataset(dpath)
        res = get_status_dict('save', ds=ds, logger=lgr)
        if not ds.is_installed():
            res['status'] = 'impossible'
            res['message'] = ('dataset %s is not installed', ds)
            yield res
            continue
        saved_state = save_dataset(
            ds,
            info[dpath],
            message=message,
            version_tag=version_tag)
        if saved_state:
            res['status'] = 'ok'
        else:
            res['status'] = 'notneeded'
        yield res


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

    # always yields list; empty if None
    files = list(
        set(
            [opj(ds.path, f) if not isabs(f) else f for f in assure_list(paths)]))

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
    tostage = [f for f in files if lexists(f)]
    if tostage:
        lgr.debug('staging files for commit: %s', tostage)
        if isinstance(ds.repo, AnnexRepo):
            # to make this work without calling `git add` in addition,
            # this needs git-annex v6.20161210 (see #1027)
            ds.repo.add(tostage, commit=False)
        else:
            # --update will ignore any untracked files, sadly git-annex add
            # above does not
            # will complain about vanished files though, filter them here, but
            # keep them for a later commit call
            ds.repo.add(tostage, git_options=['--update'], commit=False)

    _datalad_msg = False
    if not message:
        message = 'Recorded existing changes'
        _datalad_msg = True

    # TODO: Remove dirty() altogether???
    if files or ds.repo.is_dirty(
            index=True,
            untracked_files=False,
            submodules=True):
        # either we have an explicit list of files, or we have something
        # stages otherwise do not attempt to commit, as the underlying
        # repo will happily commit any non-change
        # not checking the working tree or untracked files should make this
        # relatively cheap

        # we will blindly call commit not knowing if there is anything to
        # commit -- this is cheaper than to anticipate all possible ways
        # a repo in whatever mode is dirty
        ds.repo.commit(message, files=files, _datalad_msg=_datalad_msg,
                       careless=True)

    # MIH: let's tag even if there was nothing commit. I'd forget this
    # option too often...
    if version_tag:
        ds.repo.tag(version_tag)

    _was_modified = ds.repo.get_hexsha() != orig_hexsha

    return ds.repo.repo.head.commit if _was_modified else None


def amend_pathspec_with_superdatasets(spec, topmost=True, limit_single=False):
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
      that is used as the topmost dataset.
    limit_single : bool
      If a `topmost` dataset is provided, and this flag is True, only
      the given topmost dataset will be considered as superdataset. Any
      datasets in the spec that are not underneath this dataset will
      not have associated superdataset entries added to the spec.

    Returns
    -------
    dict
      Amended path spec dictionary
    """
    superdss = {}
    for dpath in spec.keys():
        superds = None
        if isinstance(topmost, Dataset):
            if limit_single and dpath == topmost.path:
                # this is already the topmost, no further superdataset to
                # consider
                continue
            if dpath.startswith(_with_sep(topmost.path)):
                # the given topmost dataset is "above" the current
                # datasets path
                superds = topmost
            elif limit_single:
                continue
        if not superds:
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


def get_paths_by_dataset(paths, recursive=False, recursion_limit=None,
                         out=None, dir_lookup=None, sub_paths=True):
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
      Depth constraint for recursion. See `subdatasets()` for more
      information.
    out : dict or None
      By default a new output dictionary is created, however an existing one
      can be provided via this argument to enable incremental processing.
    dir_lookup : dict or None, optional
      Optional lookup cache that maps paths to previously determined datasets.
      This can speed up repeated processing.
    sub_paths : bool, optional
      Provide a list containing the sub-dataset path, as the entry for that
      sub-dataset.  If False, empty list is assigned

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
        dspath = dir_lookup.get(d, get_dataset_root(d))
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
                for subdspath in ds.subdatasets(
                        fulfilled=True,
                        recursive=recursive,
                        recursion_limit=recursion_limit,
                        result_xfm='paths'):
                    if subdspath.startswith(_with_sep(path)):
                        # this subdatasets is underneath the search path
                        # be careful to not overwrite anything, in case
                        # this subdataset has been processed before
                        out[subdspath] = out.get(
                            subdspath,
                            [subdspath] if sub_paths else [])
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
            elif path != refpath and GitRepo.is_valid_repo(path):
                # mount point, keep but don't dive into
                dirs.append(path)
            else:
                legit_names.append(n)
                dirs.append(path)
        names[:] = legit_names

    # collects the directories
    refpath = get_dataset_root(top)
    if not refpath:
        raise ValueError("`top` path {} is not in a dataset".format(top))
    ignore = [opj(refpath, get_git_dir(refpath))]
    if ignore_datalad:
        ignore.append(opj(refpath, '.datalad'))
    d = []
    walk(top, func, (refpath, ignore, d))
    return d


# XXX the following present a different approach to
# amend_pathspec_with_superdatasets() for discovering datasets between
# processed ones and a base
# let it simmer for a while and RF to use one or the other
# this one here seems more leightweight and less convoluted
def _discover_trace_to_known(path, trace, spec):
    # this beast walks the directory tree from a given `path` until
    # it discovers a known dataset (i.e. recorded in the spec)
    # if it finds one, it commits any accummulated trace of visited
    # datasets on this edge to the spec
    valid_repo = GitRepo.is_valid_repo(path)
    if valid_repo:
        trace = trace + [path]
        if path in spec:
            # found a known repo, commit the trace
            for i, p in enumerate(trace[:-1]):
                spec[p] = list(set(spec.get(p, []) + [trace[i + 1]]))
            # this edge is not done, we need to try to reach any downstream
            # dataset
    # OPT TODO? listdir might be large and we could have only few items
    #  in spec -- so why not to traverse only those in spec which have
    #  leading dir path???
    for p in listdir(path):
        if valid_repo and p == '.git':
            # ignore gitdir to speed things up
            continue
        p = opj(path, p)
        if not isdir(p):
            continue
        _discover_trace_to_known(p, trace, spec)


def filter_unmodified(content_by_ds, refds, since):
    """Filter per-dataset path specifications based on modification history.

    This function takes a path specification dictionary, as produced by
    `Interface._prep()` and filters it such that only that subset of paths
    remains in the dictionary that corresponding to the set of changes in
    the given reference dataset since a given state.

    The change set is traced across all related subdatasets, i.e. if a submodule
    in the reference dataset is reported as modified then all paths for any given
    subdataset in the modified one are tested for changes too (based on the
    state at which the parent dataset reports a change in the subdataset), and so
    on.

    In doing so, not only unmodified given paths are removed, but also modified
    given paths are replaced by the set of actually modified paths within them.

    Only committed changes are considered!

    Parameters
    ----------
    content_by_ds : dict
      Per-dataset path specifications, as produced ,for example, by
      `Interface._prep()`
    refds : Dataset or *Repo or path
      Reference dataset for which to determine the initial change set
    since : state
      Any commit-ish/tree-ish supported by Git (tag, commit, branch, ...).
      Changes between this given state and the most recent commit are
      evaluated.

    Returns
    -------
    dict
      Filtered path spec dictionary. If `since` is not None, the output is
      guaranteed to only contain paths to modified, and presently existing
      components of subdatasets of the given reference dataset (and itself).
    """
    if since is None:
        # we want all, subds not matching the ref are assumed to have been
        # sorted out before (e.g. one level up)
        return content_by_ds
    # turn refds argument into a usable repo instance
    if not hasattr(refds, 'path'):
        # not a Repo or Dataset
        refds_path = refds
        refds = GitRepo(refds, create=False)
    else:
        refds_path = refds.path
    repo = refds.repo
    if hasattr(repo, 'repo'):
        # TODO use GitRepo.diff() when available (gh-1217)
        repo = repo.repo

    # life is simple: we diff the base dataset, and kill anything that
    # does not start with something that is in the diff
    # we cannot really limit the diff paths easily because we might get
    # or miss content (e.g. subdatasets) if we don't figure out which ones
    # are known -- and we don't want that
    try:
        diff = repo.commit().diff(since)
    except GitCommandError as exc:
        # could fail because `since` points to non existing location.
        # Unfortunately there might be no meaningful message
        # e.g. "fatal: ambiguous argument 'HEAD^': unknown revision or path not in the working tree"
        # logged within this GitCommandError for some reason! So let's check
        # that value of since post-error for being correct:
        try:
            refds.repo._git_custom_command(
                [],
                ['git', 'show', '--stat', since, '--'],
                expect_stderr=True, expect_fail=True)
            raise  # re-raise since our idea was incorrect
        except CommandError as ce_exc:
            if ce_exc.stderr.startswith('fatal: bad revision'):
                raise ValueError(
                    "Value since=%r is not valid. Git reports: %s" %
                    (since, exc_str(ce_exc))
                )
            else:
                raise  # re-raise

    # get all modified paths (with original? commit) that are still
    # present
    modified = dict((opj(refds_path, d.b_path),
                    d.b_blob.hexsha if d.b_blob else None)
                    for d in diff)
    if not modified:
        # nothing modified nothing to report
        return {}
    # determine the subset that is a directory and hence is relevant for possible
    # subdatasets
    modified_dirs = {_with_sep(d) for d in modified if isdir(d)}
    # find the subdatasets matching modified paths, this will also kick out
    # any paths that are not in the dataset sub-hierarchy
    mod_subs = {candds: paths
                for candds, paths in content_by_ds.items()
                if candds != refds_path and
                any(_with_sep(candds).startswith(md) for md in modified_dirs)}
    # now query the next level down
    keep_subs = \
        [filter_unmodified(mod_subs, subds_path, modified[subds_path])
         for subds_path in mod_subs
         if subds_path in modified]
    # merge result list into a single dict
    keep = {k: v for d in keep_subs for k, v in d.items()}

    paths_refds = content_by_ds[refds_path]
    keep[refds_path] = [m for m in modified
                        if lexists(m)  # still around
                        and (m in paths_refds  # listed file, or subds
                        # or a modified path under a given directory
                        or any(m.startswith(_with_sep(p)) for p in paths_refds))]
    return keep


# define parameters to be used by eval_results to tune behavior
# Note: This is done outside eval_results in order to be available when building
# docstrings for the decorated functions
# TODO: May be we want to move them to be part of the classes _params. Depends
# on when and how eval_results actually has to determine the class.
# Alternatively build a callable class with these to even have a fake signature
# that matches the parameters, so they can be evaluated and defined the exact
# same way.

eval_params = dict(
    return_type=Parameter(
        doc="""return value behavior switch. If 'item-or-list' a single
        value is returned instead of a one-item return value list, or a
        list in case of multiple return values.""",
        constraints=EnsureChoice('generator', 'list', 'item-or-list')),
    result_filter=Parameter(
        doc="""if given, each to-be-returned
        status dictionary is passed to this callable, and is only
        returned if the callable's return value does not
        evaluate to False or a ValueError exception is raised.""",
        constraints=EnsureCallable()),
    result_xfm=Parameter(
        doc="""if given, each to-be-returned result
        status dictionary is passed to this callable, and its return value
        becomes the result instead. This is different from
        `result_filter`, as it can perform arbitrary transformation of the
        result value. This is mostly useful for top-level command invocations
        that need to provide the results in a particular format. Instead of
        a callable, a label for a pre-crafted result transformation can be
        given.""",
        constraints=EnsureChoice(*list(known_result_xfms.keys())) | EnsureCallable()),
    result_renderer=Parameter(
        doc="""format of return value rendering on stdout""",
        constraints=EnsureChoice('json', 'simple', 'tailored') | EnsureNone()),
    on_failure=Parameter(
        doc="""behavior to perform on failure: 'ignore' any failure is reported,
        but does not cause an exception; 'continue' if any failure occurs an
        exception will be raised at the end, but processing other actions will
        continue for as long as possible; 'stop': processing will stop on first
        failure and an exception is raised. A failure is any result with status
        'impossible' or 'error'. Raised exception is an IncompleteResultsError
        that carries the result dictionaries of the failures in its `failed`
        attribute.""",
        constraints=EnsureChoice('ignore', 'continue', 'stop')),
)
eval_defaults = dict(
    return_type='list',
    result_filter=None,
    result_renderer=None,
    result_xfm=None,
    on_failure='stop',
)


def eval_results(func):
    """Decorator for return value evaluation of datalad commands.

    Note, this decorator is only compatible with commands that return
    status dict sequences!

    Two basic modes of operation are supported: 1) "generator mode" that
    `yields` individual results, and 2) "list mode" that returns a sequence of
    results. The behavior can be selected via the kwarg `return_type`.
    Default is "list mode".

    This decorator implements common functionality for result rendering/output,
    error detection/handling, and logging.

    Result rendering/output can be triggered via the
    `datalad.api.result-renderer` configuration variable, or the
    `result_renderer` keyword argument of each decorated command. Supported
    modes are: 'json' (one object per result, like git-annex), 'simple'
    (status: path), 'tailored' custom output formatting provided by each command
    class (if any).

    Error detection works by inspecting the `status` item of all result
    dictionaries. Any occurrence of a status other than 'ok' or 'notneeded'
    will cause an IncompleteResultsError exception to be raised that carries
    the failed actions' status dictionaries in its `failed` attribute.

    Status messages will be logged automatically, by default the following
    association of result status and log channel will be used: 'ok' (debug),
    'notneeded' (debug), 'impossible' (warning), 'error' (error).  Logger
    instances included in the results are used to capture the origin of a
    status report.

    Parameters
    ----------
    func: function
      __call__ method of a subclass of Interface,
      i.e. a datalad command definition
    """

    default_logchannels = {
        'ok': 'debug',
        'notneeded': 'debug',
        'impossible': 'warning',
        'error': 'error',
    }

    @wrapt.decorator
    def eval_func(wrapped, instance, args, kwargs):

        # determine class, the __call__ method of which we are decorating:
        # Ben: Note, that this is a bit dirty in PY2 and imposes restrictions on
        # when and how to use eval_results as well as on how to name a command's
        # module and class. As of now, we are inline with these requirements as
        # far as I'm aware.
        mod = sys.modules[wrapped.__module__]
        if PY2:
            # we rely on:
            # - decorated function is method of a subclass of Interface
            # - the name of the class matches the last part of the module's name
            #   if converted to lower
            # for example:
            # ..../where/ever/mycommand.py:
            # class MyCommand(Interface):
            #     @eval_results
            #     def __call__(..)
            command_class_names = \
                [i for i in mod.__dict__
                 if type(mod.__dict__[i]) == type and
                 issubclass(mod.__dict__[i], Interface) and
                 i.lower() == wrapped.__module__.split('.')[-1]]
            assert(len(command_class_names) == 1)
            command_class_name = command_class_names[0]
        else:
            command_class_name = wrapped.__qualname__.split('.')[-2]
        _func_class = mod.__dict__[command_class_name]
        lgr.debug("Determined class of decorated function: %s", _func_class)

        common_params = {
            p_name: kwargs.pop(
                p_name,
                getattr(_func_class, p_name, eval_defaults[p_name]))
            for p_name in eval_params}
        result_renderer = common_params['result_renderer']

        def generator_func(*_args, **_kwargs):
            # obtain results
            results = wrapped(*_args, **_kwargs)
            # flag whether to raise an exception
            # TODO actually compose a meaningful exception
            incomplete_results = []
            # inspect and render
            result_filter = common_params['result_filter']
            result_renderer = common_params['result_renderer']
            result_xfm = common_params['result_xfm']
            if result_xfm in known_result_xfms:
                result_xfm = known_result_xfms[result_xfm]
            on_failure = common_params['on_failure']
            if not result_renderer:
                result_renderer = dlcfg.get('datalad.api.result-renderer', None)
            for res in results:
                ## log message
                # use provided logger is possible, or ours if necessary
                # remove logger instance from results, as it is no longer useful
                # after logging was done, it isn't serializable, and generally
                # pollutes the output
                res_lgr = res.pop('logger', lgr)
                if isinstance(res_lgr, logging.Logger):
                    # didn't get a particular log function, go with default
                    res_lgr = getattr(res_lgr, default_logchannels[res['status']])
                if 'message' in res:
                    msg = res['message']
                    if isinstance(msg, tuple):
                        # support string expansion of logging to avoid runtime cost
                        res_lgr(*msg)
                    else:
                        res_lgr(msg)
                ## error handling
                # looks for error status, and report at the end via
                # an exception
                if on_failure in ('continue', 'stop') \
                        and res['status'] in ('impossible', 'error'):
                    incomplete_results.append(res)
                    if on_failure == 'stop':
                        # first fail -> that's it
                        # raise will happen after the loop
                        break
                if result_filter:
                    try:
                        if not result_filter(res):
                            raise ValueError('excluded by filter')
                    except ValueError as e:
                        lgr.debug('not reporting result (%s)', exc_str(e))
                        continue
                ## output rendering
                if result_renderer == 'json':
                    print(json.dumps(
                        {k: v for k, v in res.items()
                         if k not in ('message', 'logger')}))
                elif result_renderer == 'simple':
                    # simple output "STATUS: PATH"
                    # where PATH is relative to a reference dataset, if one is reported in the result
                    print('{status}: {path}'.format(
                        status=res['status'],
                        path=relpath(res['path'], res['refds']) if res.get('refds', None) else res['path']))
                elif result_renderer == 'tailored':
                    if hasattr(_func_class, 'custom_result_renderer'):
                        _func_class.custom_result_renderer(res, **_kwargs)
                elif hasattr(result_renderer, '__call__'):
                    result_renderer(res, **_kwargs)
                if result_xfm:
                    res = result_xfm(res)
                    if res is None:
                        continue
                yield res

            if incomplete_results:
                # stupid catch all message <- tailor TODO
                raise IncompleteResultsError(
                    failed=incomplete_results,
                    msg="Command did not complete successfully")

        if common_params['return_type'] == 'generator':
            return generator_func(*args, **kwargs)
        else:
            @wrapt.decorator
            def return_func(wrapped_, instance_, args_, kwargs_):
                results = wrapped_(*args_, **kwargs_)
                if inspect.isgenerator(results):
                    results = list(results)
                # render summaries
                if not common_params['result_xfm'] and result_renderer == 'tailored':
                    # cannot render transformed results
                    if hasattr(_func_class, 'custom_result_summary_renderer'):
                        _func_class.custom_result_summary_renderer(results)
                if common_params['return_type'] == 'item-or-list' and \
                        len(results) == 1:
                    return results[0]
                else:
                    return results

            return return_func(generator_func)(*args, **kwargs)

    return eval_func(func)


def build_doc(cls):
    """Decorator to build docstrings for datalad commands

    It's intended to decorate the class, the __call__-method of which is the
    actual command. It expects that __call__-method to be decorated by
    eval_results.

    Parameters
    ----------
    cls: Interface
      class defining a datalad command
    """

    # Note, that this is a class decorator, which is executed only once when the
    # class is imported. It builds the docstring for the class' __call__ method
    # and returns the original class.
    #
    # This is because a decorator for the actual function would not be able to
    # behave like this. To build the docstring we need to access the attribute
    # _params of the class. From within a function decorator we cannot do this
    # during import time, since the class is being built in this very moment and
    # is not yet available in the module. And if we do it from within the part
    # of a function decorator, that is executed when the function is called, we
    # would need to actually call the command once in order to build this
    # docstring.

    lgr.debug("Building doc for {}".format(cls))

    # get docs for eval_results parameters:
    eval_doc = ""
    for p in eval_params:
        eval_doc += '{}{}'.format(
            eval_params[p].get_autodoc(
                p,
                default=getattr(cls, p, eval_defaults[p]),
                has_default=True),
            linesep)

    # suffix for update_docstring_with_parameters:
    if cls.__call__.__doc__:
        eval_doc += cls.__call__.__doc__

    # build standard doc and insert eval_doc
    spec = getattr(cls, '_params_', dict())
    update_docstring_with_parameters(
        cls.__call__, spec,
        prefix=alter_interface_docs_for_api(cls.__doc__),
        suffix=alter_interface_docs_for_api(eval_doc)
    )

    # return original
    return cls
