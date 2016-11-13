# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for uninstalling dataset content

"""

__docformat__ = 'restructuredtext'

import os
import logging
from itertools import chain

from os.path import relpath, split as psplit
from os.path import curdir
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod, require_dataset
from datalad.interface.base import Interface
from datalad.interface.save import Save
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.utils import get_normalized_path_arguments
from datalad.interface.utils import handle_dirty_dataset
from datalad.interface.utils import get_paths_by_dataset
from datalad.utils import rmtree
from datalad.utils import getpwd
from datalad.utils import assure_list
from datalad.utils import with_pathsep as _with_sep

lgr = logging.getLogger('datalad.distribution.uninstall')


def _uninstall_dataset(ds, remove_handles, check, kill=False):
    results = []
    if not kill and remove_handles and ds.get_subdatasets(fulfilled=True):
        raise ValueError(
            "{} still has present subdatasets, will not remove "
            "it (missing --recursive?)".format(ds))
    if not (remove_handles and not check):
        # remove data when asked, but not if handles will go and checks are
        # disabled
        if hasattr(ds.repo, 'drop'):
            lgr.debug("Dropping content from %s", ds)
            opts = ['--force'] if not check else []
            results.extend(
                assure_list(
                    ds.repo.drop(curdir, options=opts)))
        elif not remove_handles:
            lgr.warning("cannot uninstall data only, not an annex dataset")

    if not remove_handles:
        # we are done here
        return results

    # TODO: Check that branch(es) are pushed somewhere before the kill
    rmtree(ds.path)
    results.append(ds)

    return results


def _uninstall_files(ds, files, remove_handles, check):
    results = []
    if not (remove_handles and not check):
        # remove data when asked, but not if handles will go and checks are
        # disabled (AKA kill)
        if hasattr(ds.repo, 'drop'):
            opts = ['--force'] if not check else []
            results.extend(ds.repo.drop(files, options=opts))
        elif not remove_handles:
            lgr.warning("cannot uninstall data only, not an annex dataset")

    if not remove_handles:
        # we are done here
        return results

    # and now make the handles disappear
    # always recurse into directories
    results.extend(ds.repo.remove(files, r=True))

    return results


def _record_change_in_subdatasets(ds, ds2save, kill):
    # deal with any datasets that have changed in
    # the process already
    out = {}
    for subds_path in ds2save:
        dstestpath = _with_sep(ds.path)
        if subds_path.startswith(dstestpath):
            # add this change to the parent, but don't save,
            # will do elsewhere, use relpath
            subds_relpath = subds_path[len(dstestpath):]
            if ds2save[subds_path]:
                # kill requested and entire dataset is gone
                # remove submodule reference
                submodule = [sm for sm in ds.repo.repo.submodules
                             if sm.path == subds_relpath][0]
                if kill:
                    lgr.debug("Unregister subdataset '%s' from %s",
                              subds_relpath, ds)
                    submodule.remove()
                else:
                    # put back empty dir as mount point
                    os.makedirs(subds_path)
                    ds.repo.add(subds_relpath, git=True)
            else:
                ds.repo.add(subds_relpath, git=True)
        else:
            out[subds_path] = ds2save[subds_path]
    return out


class Uninstall(Interface):
    """Uninstall a dataset component or entire dataset(s)


    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="DATASET",
            doc="""specify the dataset to perform the uninstall operation on.
            If no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path/name of the component to be uninstalled",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        remove_handles=Parameter(
            args=("--remove-handles",),
            doc="""if given, matching file handles are removed. This flag is required
            for deleting entire datasets""",
            action="store_true"),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        check=Parameter(
            args=("--nocheck",),
            doc="""whether to perform checks to assure the configured minimum number
            (remote) source for data to be uninstalled.[CMD:  Give this option to skip
            checks CMD]""",
            action="store_false",
            dest='check'),
        kill=Parameter(
            args=("--kill",),
            action="store_true",
            doc="""**WARNING -- extremely dangerous**. It will simply force remove,
            without consideration of being a dataset, a file, or a directory or
            any other option given to uninstall.  To be used only with full
            awareness of its consequences"""
        ),
        if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name='uninstall')
    def __call__(
            path=None,
            dataset=None,
            remove_handles=False,
            recursive=False,
            recursion_limit=None,
            check=True,
            kill=False,
            if_dirty='save-before'):

        #1115 uninstall saved originating repository while I was trying to
        #     "drop" a file under some git-annex repo underneath
        #1105 uninstall is to picky with subdatasets (require --recursives
        #     too often)
        #1079 uninstall cannot be used (without --kill) to merely de-init
        #     sub-datasets
        #1078 uninstall is not usable to uninstall correctly super-datasets
        #     (with or without sub-datasets installed)
        #1046 uninstall --kill must reincarnate the directory of the repository
        #     if it is a submodule of supermodule
        #970  uninstall would fail uninstall submodule with special remotes!
        #863  uninstall mode of operation which doesn't deinit submodule

        # upfront check prior any resolution attempt to avoid disaster
        if path is None and dataset is None:
            raise InsufficientArgumentsError(
                "insufficient information for uninstallation (needs at "
                "least a dataset or a path. To uninstall an entire dataset "
                "it needs to be given explicitly.")

        if remove_handles and recursion_limit is not None:
            raise ValueError(
                "impossible to remove handles recursively with recursion limit")

        if kill:
            remove_handles = True
            check = False

        path, dataset_path = get_normalized_path_arguments(
            path, dataset, default=curdir)

        # collect paths that got uninstalled for reporting
        results = []

        # if recursivecontent_by_ds will
        content_by_ds, unavailable_paths, nondataset_paths = \
            get_paths_by_dataset(path,
                                 recursive=recursive,
                                 recursion_limit=recursion_limit)
        if remove_handles:
            # behave like `rm -r` and refuse to remove where we are
            pwd = getpwd()
            for p in chain(*content_by_ds.values()):
                rpath = relpath(p, start=pwd)
                if rpath == os.curdir \
                        or rpath == os.pardir \
                        or set(psplit(rpath)) == {os.pardir}:
                    raise ValueError(
                        "refusing to remove current or parent directory")

        if dataset_path and not content_by_ds:
            # we got a dataset, but there is nothing actually installed
            nondataset_paths.append(dataset_path)
        # complain about nondataset and non-existing paths
        if nondataset_paths:
            raise ValueError(
                "will not touch paths outside of installed datasets: %s"
                % nondataset_paths)
        if unavailable_paths:
            lgr.warning('ignored non-existing paths: %s', unavailable_paths)

        if dataset_path:
            dataset = require_dataset(
                dataset, check_installed=True, purpose='uninstall')
        else:
            dataset = None

        ds2save = {}
        # iterate over all datasets, starting at the bottom
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            paths = content_by_ds[ds_path]

            if remove_handles:
                ds2save = _record_change_in_subdatasets(ds, ds2save, kill)

            # make sure we get to an expected state
            if not kill:
                handle_dirty_dataset(ds, if_dirty)

            if ds_path in paths:
                # the dataset itself is to be uninstalled
                res = _uninstall_dataset(
                    ds,
                    remove_handles=remove_handles,
                    check=check,
                    kill=kill)
                ds2save[ds.path] = True
            else:
                # uninstall content in a dataset, but not the entire dataset
                res = _uninstall_files(
                    ds,
                    paths,
                    remove_handles=remove_handles,
                    check=check)
                ds2save[ds.path] = False
                if remove_handles:  # save removed handles
                    Save.__call__(
                        message='[DATALAD] uninstalled handles',
                        dataset=ds,
                        auto_add_changes=False,
                        recursive=False)
            results.extend(res)

        if dataset and dataset.is_installed() and remove_handles:
            _record_change_in_subdatasets(dataset, ds2save, kill)
            # we have a parent and have removed handles
            Save.__call__(
                message='[DATALAD] uninstalled content',
                dataset=dataset,
                auto_add_changes=False,
                recursive=False)

        return results

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if not res:
            ui.message("Nothing was uninstalled")
            return
        msg = "{n} {obj} uninstalled:\n".format(
            obj='items were' if len(res) > 1 else 'item was',
            n=len(res))
        for item in res:
            if isinstance(item, Dataset):
                msg += "Dataset: %s\n" % item.path
            else:
                msg += "File: %s\n" % item
        ui.message(msg)
