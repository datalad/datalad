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

import wrapt
import sys
import logging
from os import curdir
from os import pardir
from os import listdir
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

# avoid import from API to not get into circular imports
from datalad.utils import with_pathsep as _with_sep  # TODO: RF whenever merge conflict is not upon us
from datalad.utils import assure_list
from datalad.utils import get_trace
from datalad.utils import walk
from datalad.utils import get_dataset_root
from datalad.utils import swallow_logs
from datalad.utils import better_wraps
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path
from datalad.distribution.utils import _install_subds_inplace
from datalad.distribution.utils import get_git_dir

from .base import Interface
from .base import update_docstring_with_parameters
from .base import alter_interface_docs_for_api


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
            {d: [d] for d in dpaths},
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
    if not subds_graph:
        # no subdatasets, nothing to sort
        return
    for t in target_subs:
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
        spec[c] = list(set(spec[c]))


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
        dpaths.append(base.path if isinstance(base, Dataset) else base)
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
    saved = []
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

    if files or ds.repo.repo.is_dirty(
            index=True,
            working_tree=False,
            untracked_files=False,
            submodules=True):
        # either we have an explicit list of files, or we have something
        # stages otherwise do not attempt to commit, as the underlying
        # repo will happily commit any non-change
        # not checking the working tree or untracked files should make this
        # relavtively cheap

        # TODO: commit() should rather report a dedicated ValueError
        # waiting for #1170
        from datalad.support.exceptions import CommandError
        try:
            # we will blindly call commit not knowing if there is anything to
            # commit -- this is cheaper than to anticipate all possible ways
            # a repo in whatever mode is dirty
            # however, if nothing is dirty the whining wil start
            # --> sucking it up right here
            with swallow_logs(new_level=logging.ERROR) as cml:
                ds.repo.commit(message, options=files, _datalad_msg=_datalad_msg)
        except CommandError as e:
            # TODO until #1171 is resolved, test here for "normal" failure
            # to commit
            if 'nothing to commit' in str(e):
                lgr.debug(
                    "Was instructed to commit %s files but repository is not dirty",
                    files)
            elif 'no changes added to commit' in str(e) or 'nothing added to commit' in str(e):
                lgr.info(
                    'Nothing to save')
            else:
                # relay any prior whining in the exception
                raise ValueError('{} [error log follows] {}; {}'.format(
                    e, e.stdout, e.stderr))

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
    # it discoveres a known dataset (i.e. recorded in the spec)
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
    for p in listdir(path):
        if valid_repo and p == '.git':
            # ignore gitdir to steed things up
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
    diff = repo.commit().diff(since)
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

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter

eval_params = dict(
    _eval_arg1=Parameter(
        doc="first parameter",
        constraints=EnsureStr() | EnsureNone()),
    _eval_arg2=Parameter(
        doc="second parameter",
        constraints=EnsureStr() | EnsureNone()),
)
eval_defaults = dict(
    _eval_arg1="default1",
    _eval_arg2="default2",
)


def eval_results(func):
    """Decorator providing functionality to evaluate return values of datalad
    commands

    Parameters
    ----------
    func: function
      __call__ method of a subclass of Interface,
      i.e. a datalad command definition

    """
    from inspect import isgenerator

    @wrapt.decorator
    def new_func(wrapped, instance, args, kwargs):

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

        def ext_func(*_args, **_kwargs):

            # MARKER for merging:
            # this should correspond to former 'new_func' within 'eval_results'
            # therefore this is the level of 'generator_func' in PR #1350
            # PR #1350 is based on ecd8d8e1b86f0676db22c87182e52899a80d800e in
            # PR #1348, which corresponds to
            # 3825b9b177b0f67a2e93f1d5dbbd5f206c4aa2d in #1350

            _params = {p_name: _kwargs.pop(p_name, eval_defaults[p_name])
                       for p_name in eval_params}

            # use additional arguments to do stuff:
            lgr.debug("_eval_arg1: %s", _params['_eval_arg1'])
            lgr.debug("_eval_arg2: %s", _params['_eval_arg2'])

            # rudimentary wrapper to harvest generators
            results = wrapped(*_args, **_kwargs)
            if isgenerator(results):
                return list(results)
            else:
                return results
        return ext_func(*args, **kwargs)

    return new_func(func)


def build_doc(func):
    """Decorator to build docstrings for datalad commands

    It's intended to decorate the class, the __call__-method of which is the
    actual command. It expects that __call__-method to be decorated by
    eval_results.

    Parameters
    ----------
    func: Interface
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

    lgr.debug("Building doc for {}".format(func))

    # get docs for eval_results parameters:
    eval_doc = ""
    for p in eval_params:
        eval_doc += eval_params[p].get_autodoc(
            p, default=eval_defaults[p], has_default=True)
    # suffix for update_docstring_with_parameters:
    if func.__call__.__doc__:
        eval_doc += func.__call__.__doc__

    # build standard doc and insert eval_doc
    spec = getattr(func, '_params_', dict())
    update_docstring_with_parameters(
        func.__call__, spec,
        prefix=alter_interface_docs_for_api(func.__doc__),
        suffix=alter_interface_docs_for_api(eval_doc)
    )

    # return original
    return func
