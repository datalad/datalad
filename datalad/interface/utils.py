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
from os import curdir
from os import pardir
from os.path import join as opj
from os.path import lexists
from os.path import isdir
from os.path import dirname
from os.path import relpath
from os.path import sep
from os.path import split as psplit
from itertools import chain

# avoid import from API to not get into circular imports
from datalad.interface.save import Save
from datalad.utils import with_pathsep as _with_sep  # TODO: RF whenever merge conflict is not upon us
from datalad.utils import assure_list
from datalad.utils import get_trace
from datalad.utils import walk
from datalad.support.gitrepo import GitRepo
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path
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
        Save.__call__(dataset=ds, message=msg, auto_add_changes=True)
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
            dpaths,
            base=base,
            message=msg,
            auto_add_changes=True)
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


def save_dataset_hierarchy(
        dpaths,
        base=None,
        message='[DATALAD] saved changes',
        auto_add_changes=False):
    """Save a (disjoint) hierarchy of dataset.

    Saving is done in an order that guarantees that all to be saved
    datasets reflect any possible change of any other to be saved
    subdataset, before they are saved themselves.

    Parameters
    ----------
    dpaths : sequence
      Absolute paths of datasets to be saved
    base : path or None, optional
      Common super dataset that should also be saved.
    message : str
      Message to be used for saving individual datasets
    auto_add_changes : bool
      Whether to auto include any modifications in a dataset.
    """
    if base:
        # just a convenience...
        dpaths = assure_list(dpaths)
        dpaths.append(base.path if isinstance(base, Dataset) else base)
    dpaths_ws = [_with_sep(d) for d in dpaths]
    # sort all datasets under their potential superdatasets
    superdss = {}
    # start from the top to get all subdatasets down the line
    # and collate them into as few superdatasets as possible
    for s in sorted(dpaths_ws):
        if any([s.startswith(d) for d in superdss]):
            # this path is already covered by a known superdataset
            continue
        # find all subdatasets
        subs = [d for d in dpaths if d.startswith(s)]
        superdss[s] = subs
    # for each "superdataset" check the tree of subdatasets and make sure
    # we gather all datasets between the super and any subdataset
    # so we can save them all bottom-up in order to be able to properly
    # save the superdataset
    tosave = set(dpaths)
    for superds_path in superdss:
        target_subs = superdss[superds_path]
        subds_graph = Dataset(superds_path).get_subdatasets(
            absolute=True, recursive=True, edges=True, fulfilled=True)
        for t in target_subs:
            trace = get_trace(
                subds_graph,
                # need to strip separator to make `==` work
                superds_path.rstrip(sep),
                t)
            if trace:
                tosave = tosave.union(trace)
    # iterate over all datasets, starting at the bottom
    for dpath in sorted(tosave, reverse=True):
        ds = Dataset(dpath)
        if ds.is_installed():
            Save.__call__(
                dataset=ds,
                message=message,
                auto_add_changes=auto_add_changes,
                recursive=False)
        superds = ds.get_superdataset(
            datalad_only=False,
            topmost=False)
        if superds and superds.path in tosave:
            # stage the new state known in a superdataset, but only if it is
            # to be saved
            superds.repo.add(
                relpath(dpath, start=superds.path),
                git=True)


def get_paths_by_dataset(paths, recursive=False, recursion_limit=None,
                         out=None, dir_lookup=None, mark_recursive=False):
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
      By default a new output dictionary is created, howeverm and existing one
      can be provided via this argument to enable incremental processing.
    dir_lookup : dict or None
      Optional lookup cache that maps paths to previously determined datasets.
      This can speed up repeated processing.
    mark_recursive : bool
      If True, subdatasets "discovered" by recursion are marked such that
      their value is a one-item list that contains `curdir` as the only item,
      otherwise the item will be the same as the key -- the absolute path to
      the respective dataset.

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
                            [curdir if mark_recursive else subdspath])
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
      list does not include the top-level path itself, nor does it include
      any subdataset mount point (regardless of whether the particular
      subdatasets are installed or not).
    """
    def func(arg, top, names):
        refpath, ignore, dirs = arg
        legit_names = []
        for n in names:
            path = opj(top, n)
            if not isdir(path) \
                    or path in ignore \
                    or not GitRepo.get_toppath(path) == refpath:
                pass
            else:
                legit_names.append(n)
                dirs.append(path)
        names[:] = legit_names

    # collects the directories
    refpath = GitRepo.get_toppath(top)
    if not refpath:
        raise ValueError("`top` path {} is not in a dataset".format(top))
    ignore = [opj(refpath, get_git_dir(refpath))]
    # always ignore subdataset mount points
    ignore.extend(Dataset(refpath).get_subdatasets(
        absolute=True, recursive=False, fulfilled=False))
    if ignore_datalad:
        ignore.append(opj(refpath, '.datalad'))
    d = []
    walk(top, func, (refpath, ignore, d))
    return d
