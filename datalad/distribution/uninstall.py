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

from os.path import relpath, split as psplit
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod, resolve_path, require_dataset
from datalad.interface.base import Interface
from datalad.interface.save import Save
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.utils import handle_dirty_dataset
from datalad.utils import rmtree
from datalad.utils import getpwd
from datalad.utils import assure_list

lgr = logging.getLogger('datalad.distribution.uninstall')


def _uninstall(ds, paths, check, remove_history, remove_data, remove_handles,
               recursive):
    # all input paths are assumed to belong to the given dataset,
    # and in particular not to any subdataset

    # recode paths to be relative to the root of the dataset
    paths = [relpath(p, start=ds.path) for p in paths]

    if os.curdir in paths:
        # we can take a shortcut if the entire thing goes away
        lgr.debug('uninstall entire content in {}'.format(ds))
        paths = [os.curdir]

    results = []

    # at this point we can only have two things:
    # 1. files and directories in the current dataset
    # 2. the entire dataset

    # alway drop data first
    if remove_data:
        if hasattr(ds.repo, 'drop'):
            opts = ['--force'] if not check else []
            results.extend(ds.repo.drop(paths, options=opts))
        else:
            lgr.warning("cannot uninstall data only, not an annex dataset")

    if not remove_handles:
        # we are done here
        return results, False

    if os.curdir in paths:
        if not remove_history:
            raise ValueError(
                "will not remove the entire dataset (with history) unless forced")
        # special mode that makes everything disappear, including subdatasets
        for subds in ds.get_subdatasets(
                absolute=True,
                fulfilled=True,
                recursive=True,
                recursion_limit=1):
            if not recursive:
                raise ValueError(
                    "will not remove subdatasets without the recursive flag")
            subds = Dataset(subds)
            lgr.warning("removing subdataset {} from {}".format(subds, ds))
            res, gone = _uninstall(
                subds,
                [subds.path],
                check=check,
                remove_history=remove_history,
                remove_data=True,
                # we always want everything to go at this point
                remove_handles=True,
                recursive=recursive)
            results.extend(res)

        results.append(ds)
        return results, True

    # and now make the handles disappear
    # always recurse into directories
    results.extend(ds.repo.remove(paths, r=True))

    return results, False


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
        remove_data=Parameter(
            args=("--dont-remove-data",),
            doc="""whether to drop data associated with matching file handles during
            uninstallation.[CMD:  This option prevents data from being dropped CMD]""",
            action="store_false",
            dest='remove_data'),
        remove_handles=Parameter(
            args=("--remove-handles",),
            doc="""if given, matching file handles are removed. This flag is required
            for deleting entire datasets""",
            action="store_true"),
        recursive=recursion_flag,
        check=Parameter(
            args=("--nocheck",),
            doc="""whether to perform checks to assure the configured minimum number
            (remote) source for data to be uninstalled.[CMD:  Give this option to skip
            checks CMD]""",
            action="store_false",
            dest='check'),
        remove_history=Parameter(
            args=("--remove-history",),
            doc="""whether to permit operations that remove recorded dataset history,
            for example when removing entire datasets completely. Such changes are not
            recoverable, use with care""",
            action="store_true",),
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
            remove_data=True,
            remove_handles=False,
            recursive=False,
            remove_history=False,
            check=True,
            kill=False,
            if_dirty='save-before'):

        # upfront check prior any resolution attempt to avoid disaster
        if dataset is None and not path:
            raise InsufficientArgumentsError(
                "insufficient information for uninstallation (needs at "
                "least a dataset or a path. To uninstall an entire dataset "
                "it needs to be given explicitly.")

        if remove_history and not remove_handles:
            raise ValueError("`remove_history` flag, requires `remove_handles` flag")

        if not remove_data and not remove_handles:
            raise ValueError("instructed to neither drop data, nor remove handles: cannot perform")

        results = []

        ds = require_dataset(
            dataset, check_installed=True, purpose='uninstall')

        # always yields list; empty if None
        path = assure_list(path)
        if not len(path):
            # AKA "everything"
            path.append(ds.path)

        # XXX Important to resolve against `dataset` input argument, and
        # not against the `ds` resolved dataset
        path = [resolve_path(p, dataset) for p in path]

        if kill:
            lgr.warning("Force-removing %d paths", len(path))
            for p in path:
                rmtree(p)
                results.append(p)
            return results

        # make sure we get to an expected state
        handle_dirty_dataset(ds, if_dirty)

        # sort paths into the respective datasets that contain them
        # considering 1st-level subdatasets at most
        # NOTE: little dance with two dicts is necessary, because ATM our
        # Datasets are not hashable enough for PY3
        whocares_paths = {}
        whocares_ds = {}
        pwd = getpwd()
        for p in path:
            if remove_handles:
                # behave like `rm -r` and refuse to remove where we are
                rpath = relpath(p, start=pwd)
                if rpath == os.curdir \
                        or rpath == os.pardir \
                        or set(psplit(rpath)) == {os.pardir}:
                    raise ValueError(
                        "refusing to remove current or parent directory")
            containerds = ds.get_containing_subdataset(p, recursion_limit=1)
            if not recursive and containerds.path != ds.path:
                raise ValueError(
                    "will not uninstall content in subdatasets without the recursive flag")
            ps = whocares_paths.get(containerds.path, [])
            ps.append(p)
            whocares_paths[containerds.path] = ps
            whocares_ds[containerds.path] = containerds

        ds_gonealready = False
        if ds.path in whocares_paths:
            # start with the content of this dataset, as any somewhat
            # total recursive removal here would have most impact
            lgr.debug("Uninstall content in {}".format(ds))
            res, ds_gonealready = _uninstall(
                whocares_ds[ds.path],
                whocares_paths[ds.path],
                check=check,
                remove_history=remove_history,
                remove_data=remove_data,
                remove_handles=remove_handles,
                recursive=recursive)
            results.extend(res)

        if ds_gonealready:
            rmtree(ds.path)
            # the underlying repo is gone, the assert makes sure that the Dataset
            # instance becomes aware of that
            assert(not ds.is_installed())
            return results

        # otherwise deal with any other subdataset
        for subdspath in whocares_paths:
            subds = whocares_ds[subdspath]
            subdsrelpath = relpath(subdspath, start=ds.path)
            if subds == ds:
                continue
            res, subds_gone = _uninstall(
                subds,
                whocares_paths[subdspath],
                check=check,
                remove_history=remove_history,
                remove_data=remove_data,
                remove_handles=remove_handles,
                recursive=recursive)
            results.extend(res)

            if subds_gone:
                # clean divorce, if we lost the subds in the process
                # find the submodule that matches the patch
                # regular access goes by name, but we cannot trust
                # our own consistency, yet
                submodule = [sm for sm in ds.repo.repo.submodules
                             if sm.path == subdsrelpath][0]
                submodule.remove()
            elif remove_handles:
                # we could have removed handles -> save
                Save.__call__(
                    message='[DATALAD] uninstalled content',
                    dataset=subds,
                    auto_add_changes=False,
                    recursive=False)
                # add this change to the parent, but don't save, will do in
                # one go below
                ds.repo.add(subdsrelpath, git=True)

        if remove_handles:
            # something of the original dataset is left at this point
            # and all subdatasets have been saved already
            # -> save changes
            Save.__call__(
                message='[DATALAD] uninstalled content',
                dataset=ds,
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
