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
from os.path import join as opj
from os.path import lexists
from os.path import isdir
from os.path import dirname

# avoid import from API to not get into circular imports
from datalad.interface.save import Save
from datalad.utils import with_pathsep as _with_sep  # TODO: RF whenever merge conflict is not upon us
from datalad.utils import assure_list
from datalad.support.gitrepo import GitRepo
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path


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
      By default a new output dictionary is created, howeverm and existing one
      can be provided via this argument to enable incremental processing.
    dir_lookup : dict or None
      Optional lookup cache that maps paths to previously determined datasets.
      This can speed up repeated processing.

    Returns
    -------
    Tuple(dict, list, list)
      Dict of `existing dataset path`: `path` mappings, the list of currently
      non-existing paths (possibly matching currently uninstalled datasets),
      and any paths that are not part of any dataset

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
                        out[subdspath] = out.get(subdspath, [subdspath])
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
