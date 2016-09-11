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

from os.path import relpath, abspath, split as psplit
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod, resolve_path, require_dataset
from datalad.interface.base import Interface
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.utils import handle_dirty_dataset
from datalad.utils import rmtree
from datalad.utils import getpwd

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
        return results

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
            results.extend(
                _uninstall(
                    subds,
                    [subds.path],
                    check=check,
                    remove_history=remove_history,
                    remove_data=True,
                    # we always want everything to go at this point
                    remove_handles=True,
                    recursive=recursive))

        results.append(ds)
        rmtree(ds.path)
        return results

    # and now make the handles disappear
    # always recurse into directories
    results.extend(ds.repo.remove(paths, r=True))

    return results


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
            doc="""""",
            action="store_false",
            dest='remove_data'),
        remove_handles=Parameter(
            args=("--remove-handles",),
            doc="""""",
            action="store_true"),
        recursive=recursion_flag,
        check=Parameter(
            args=("--nocheck",),
            doc="""""",
            action="store_false",
            dest='check'),
        remove_history=Parameter(
            args=("--remove-history",),
            doc="""""",
            action="store_true",),
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
            if_dirty='save-before'):

        # upfront check prior any resolution attempt to avoid disaster
        if dataset is None and not path:
            raise InsufficientArgumentsError(
                "insufficient information for uninstallation (needs at "
                "least a dataset or a path. To uninstall an entire dataset, "
                "it needs to be given explicitly.")

        results = []

        # general RF TODO:
        # - sort files into the respective subdatasets
        # - fail if recursive is needed and not given
        # - start removing from the top (i.e. not individual files
        #   in some subdatasets that might get removed completely
        #   in the end
        # - always drop data-content first (if annexed)
        #   try to have annex do that without expensive check if desired
        # - subsequently delete/unregister as necessary

        ds = require_dataset(
            dataset, check_installed=True, purpose='uninstall')

        if isinstance(path, list):
            if not len(path):
                path = None
        else:
            path = [path]

        if path is None:
            # AKA "everything"
            path = [ds.path]

        # XXX Important to resolve against `dataset` input argument, and
        # not against the `ds` resolved dataset
        path = [resolve_path(p, dataset) for p in path]

        # make sure we get to an expected state
        handle_dirty_dataset(ds, if_dirty)

        # sort paths into the respective datasets that contain them
        # considering 1st-level subdatasets at most
        whocares = {}
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
            ps = whocares.get(containerds, [])
            ps.append(p)
            whocares[containerds] = ps

        if ds in whocares:
            # start with the content of this dataset, as any somewhat
            # total recursive removal here would have most impact
            lgr.debug("Uninstall content in {}".format(ds))
            results.extend(
                _uninstall(
                    ds,
                    whocares[ds],
                    check=check,
                    remove_history=remove_history,
                    remove_data=remove_data,
                    remove_handles=remove_handles,
                    recursive=recursive))
        # now deal with any other subdataset
        for subds in whocares:
            if subds == ds:
                continue
            results.extend(
                _uninstall(
                    subds,
                    whocares[subds],
                    check=check,
                    remove_history=remove_history,
                    remove_data=remove_data,
                    remove_handles=remove_handles,
                    recursive=recursive))

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
