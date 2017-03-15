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

from os.path import curdir
from os.path import exists
from os.path import relpath
from os.path import join as opj
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod, require_dataset
from datalad.interface.base import Interface
from datalad.interface.base import report_result_objects
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.utils import handle_dirty_datasets
from datalad.interface.utils import path_is_under
from datalad.interface.utils import save_dataset_hierarchy
from datalad.interface.utils import _discover_trace_to_known
from datalad.utils import rmtree
from datalad.utils import get_dataset_root


lgr = logging.getLogger('datalad.distribution.uninstall')

dataset_argument = Parameter(
    args=("-d", "--dataset"),
    metavar="DATASET",
    doc="""specify the dataset to perform the operation on.
    If no dataset is given, an attempt is made to identify a dataset
    based on the `path` given""",
    constraints=EnsureDataset() | EnsureNone())


check_argument = Parameter(
    args=("--nocheck",),
    doc="""whether to perform checks to assure the configured minimum
    number (remote) source for data.[CMD:  Give this
    option to skip checks CMD]""",
    action="store_false",
    dest='check')


def _uninstall_dataset(ds, check, has_super):
    results = []
    if check and ds.is_installed():
        results.extend(_drop_files(ds, curdir, check=True))
    # TODO: uninstall of a subdataset that has a local URL
    #       (e.g. ./anything) implies cannot be undone, decide how, and
    #       if to check for that
    # TODO check that the relevant branched are pushed to a remote
    if ds.get_subdatasets(fulfilled=True):
        raise ValueError('to be uninstalled dataset has present subdatasets, forgot --recursive?')
    # Close any possibly associated process etc with underlying repo.
    # Otherwise - rmtree could fail to remove e.g. under NFS which would
    # still have some files opened by them (thus having .nfs00000xxxx
    # files) forbidding rmdir to work in rmtree
    ds.close()
    if ds.is_installed():
        rmtree(ds.path)
    if has_super and not exists(ds.path):
        # recreate an empty mountpoint to make Git happier
        os.makedirs(ds.path)
    # invalidate loaded ConfigManager:
    ds._cfg = None
    results.append(ds)
    return results


def _drop_files(ds, files, check):
    results = []
    if hasattr(ds.repo, 'drop'):
        opts = ['--force'] if not check else []
        # TODO capture for which files it fails and report them properly
        # not embedded in a command error
        dropped = ds.repo.drop(files, options=opts)
        results.extend([opj(ds.path, f) for f in dropped])
    else:
        lgr.info("skip dropping files in %s, no annex", ds)
    return results


class Drop(Interface):
    """Drop file content from datasets

    This command takes any number of paths of files and/or directories. If
    a common (super)dataset is given explicitly, the given paths are
    interpreted relative to this dataset.

    Recursion into subdatasets needs to be explicitly enabled, while recursion
    in subdirectories within a dataset as always done automatically. An
    optional recursion limit is applied relative to each given input path.

    By default, the availability of at least one remote copy is verified,
    before file content is dropped. As these checks could lead to slow
    operation (network latencies, etc), they can be disabled.


    Examples
    --------

    Drop all file content in a dataset::

      ~/some/dataset$ datalad drop

    Drop all file content in a dataset and all its subdatasets::

      ~/some/dataset$ datalad drop --recursive

    """
    _action = 'drop'

    _params_ = dict(
        dataset=dataset_argument,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path/name of the component to be dropped",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        check=check_argument,
        if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name=_action)
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            check=True,
            if_dirty='save-before'):

        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = dataset.path if isinstance(dataset, Dataset) else dataset
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=recursive,
            recursion_limit=recursion_limit)
        handle_dirty_datasets(
            content_by_ds.keys(), mode=if_dirty, base=dataset)

        results = []

        # iterate over all datasets, order doesn't matter
        for ds_path in content_by_ds:
            ds = Dataset(ds_path)
            paths = content_by_ds[ds_path]
            res = _drop_files(ds, paths, check=check)
            results.extend(res)
        # there is nothing to save at the end
        return results

    @classmethod
    def result_renderer_cmdline(cls, res, args):
        report_result_objects(cls, res, args, 'dropped')


class Uninstall(Interface):
    """Uninstall subdatasets

    This command can be used to uninstall any number of installed subdataset.
    If a to-be-uninstalled subdataset contains presently installed subdatasets
    itself, their recursive removal has to be enabled explicitly to avoid the
    command to exit with an error. This command will error if individual files
    or non-dataset directories are given as input (use the drop or remove
    command depending in the desired goal), nor will it uninstall top-level
    datasets (i.e. datasets that or not a subdataset in another dataset; use
    the remove command for this purpose).

    By default, the availability of at least one remote copy for each currently
    available file in any dataset is verified. As these checks could lead to
    slow operation (network latencies, etc), they can be disabled.

    Any number of paths to process can be given as input. Recursion into
    subdatasets needs to be explicitly enabled, while recursion in
    subdirectories within a dataset as always done automatically. An optional
    recursion limit is applied relative to each given input path.

    Examples
    --------

    Uninstall a subdataset (undo installation)::

      ~/some/dataset$ datalad uninstall somesubdataset1

    """
    _action = 'uninstall'

    _params_ = dict(
        dataset=dataset_argument,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path/name of the component to be uninstalled",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        check=check_argument,
        if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name=_action)
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            check=True,
            if_dirty='save-before'):

        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = dataset.path if isinstance(dataset, Dataset) else dataset
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=recursive)
        if unavailable_paths:
            lgr.warning('ignored non-installed paths: %s', unavailable_paths)
        # upfront sanity and compliance checks
        if path_is_under(content_by_ds.keys()):
            # behave like `rm` and refuse to remove where we are
            raise ValueError(
                "refusing to uninstall current or parent directory")
        # check that we have no top-level datasets and not files to process
        args_ok = True
        for ds_path in content_by_ds:
            ds = Dataset(ds_path)
            paths = content_by_ds[ds_path]
            if ds_path not in paths:
                lgr.error(
                    "will not act on files at %s (consider the `drop` command)",
                    paths)
                args_ok = False
            if not ds.get_superdataset(
                    datalad_only=False,
                    topmost=False):
                lgr.error(
                    "will not uninstall top-level dataset at %s (consider the `remove` command)",
                    ds.path)
                args_ok = False
        if not args_ok:
            raise ValueError(
                'inappropriate arguments, see previous error message(s)')

        handle_dirty_datasets(
            content_by_ds, mode=if_dirty, base=dataset)

        results = []

        # iterate over all datasets, starting at the bottom
        # to deinit contained submodules first
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            paths = content_by_ds[ds_path]
            results.extend(
                # we confirmed the super dataset presence above
                _uninstall_dataset(ds, check=check, has_super=True))
        # there is nothing to save at the end
        return results

    @classmethod
    def result_renderer_cmdline(cls, res, args):
        report_result_objects(cls, res, args, 'uninstalled')


class Remove(Interface):
    """Remove components from datasets

    This command can remove any components (subdatasets, and (directories with)
    files) from datasets. Removing a component implies any present content to
    be dropped, and any associated subdatasets to be uninstalled. Subsequently,
    the component is "unregistered" from the respective dataset. This means
    that the respective component is no longer present on the file system.

    By default, the availability of at least one remote copy is verified, by
    default, before file content is dropped. As these checks could lead to slow
    operation (network latencies, etc), they can be disabled.

    Any number of paths to process can be given as input. Recursion into
    subdatasets needs to be explicitly enabled, while recursion in
    subdirectories within a dataset as always done automatically. An optional
    recursion limit is applied relative to each given input path.

    Examples
    --------

    Permanently remove a subdataset from a dataset and wipe out the subdataset
    association too::

      ~/some/dataset$ datalad remove somesubdataset1
    """
    _action = 'remove'

    _params_ = dict(
        dataset=dataset_argument,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path/name of the component to be removed",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        check=check_argument,
        if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name=_action)
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            check=True,
            if_dirty='save-before'):
        if dataset:
            dataset = require_dataset(
                dataset, check_installed=False, purpose='removal')
            if not dataset.is_installed() and not path:
                # all done already
                return []
            if not path:
                # act on the whole dataset if nothing else was specified
                path = dataset.path if isinstance(dataset, Dataset) else dataset
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=recursive)

        nonexistent_paths = []
        for p in unavailable_paths:
            # we need to check whether any of these correspond
            # to a known subdataset, and add those to the list of
            # things to be removed
            toppath = get_dataset_root(p)
            if not toppath:
                nonexistent_paths.append(p)
                continue
            if p in Dataset(toppath).get_subdatasets(
                    recursive=False, absolute=True):
                # this is a known subdataset that needs to be removed
                pl = content_by_ds.get(p, [])
                pl.append(p)
                content_by_ds[p] = pl
        if nonexistent_paths:
            lgr.warning("ignoring non-existent path(s): %s",
                        nonexistent_paths)

        if path_is_under(content_by_ds):
            # behave like `rm` and refuse to remove where we are
            raise ValueError(
                "refusing to uninstall current or parent directory")

        handle_dirty_datasets(
            content_by_ds, mode=if_dirty, base=dataset)
        ds2save = set()
        results = []
        # iterate over all datasets, starting at the bottom
        # to make the removal of dataset content known upstairs
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            paths = content_by_ds[ds_path]
            if ds_path in paths:
                # entire dataset needs to go
                superds = ds.get_superdataset(
                    datalad_only=False,
                    topmost=False)
                res = _uninstall_dataset(ds, check=check, has_super=False)
                results.extend(res)
                if ds.path in ds2save:
                    # we just uninstalled it, no need to save anything
                    ds2save.discard(ds.path)
                if not superds:
                    continue
                subds_relpath = relpath(ds_path, start=superds.path)
                # remove submodule reference
                submodule = [sm for sm in superds.repo.repo.submodules
                             if sm.path == subds_relpath]
                # there can only be one!
                assert len(submodule) == 1, \
                    "Found multiple subdatasets with registered path {}:" \
                    "{}{}{}There should be only one." \
                    "".format(subds_relpath, os.linesep,
                              submodule, os.linesep)
                submodule = submodule[0]
                submodule.remove()
                if exists(ds_path):
                    # could be an empty dir in case an already uninstalled subdataset
                    # got removed
                    os.rmdir(ds_path)
                # need to save changes to .gitmodules later
                content_by_ds[superds.path] = \
                    content_by_ds.get(superds.path, []) \
                    + [opj(superds.path, '.gitmodules'),
                       ds_path]
                ds2save.add(superds.path)
            else:
                if check and hasattr(ds.repo, 'drop'):
                    _drop_files(ds, paths, check=True)
                results.extend(ds.repo.remove(paths, r=True))
                ds2save.add(ds.path)

        if dataset and dataset.is_installed():
            # forge chain from base dataset to any leaf dataset
            # in order to save state changes all the way up
            _discover_trace_to_known(dataset.path, [], content_by_ds)

        save_dataset_hierarchy(
            content_by_ds,
            base=dataset.path if dataset and dataset.is_installed() else None,
            message='[DATALAD] removed content')
        return results

    @classmethod
    def result_renderer_cmdline(cls, res, args):
        report_result_objects(cls, res, args, 'removed')
