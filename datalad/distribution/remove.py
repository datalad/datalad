# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for removing dataset content

"""

__docformat__ = 'restructuredtext'

import os
import logging

from os.path import exists
from os.path import relpath
from os.path import join as opj
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import Dataset, \
    datasetmethod, require_dataset
from datalad.interface.base import Interface
from datalad.interface.base import report_result_objects
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.utils import handle_dirty_datasets
from datalad.interface.utils import path_is_under
from datalad.interface.utils import save_dataset_hierarchy
from datalad.interface.utils import _discover_trace_to_known
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.results import results_from_paths
from datalad.utils import get_dataset_root
from datalad.distribution.drop import _drop_files
from datalad.distribution.drop import dataset_argument
from datalad.distribution.drop import check_argument
from datalad.distribution.uninstall import _uninstall_dataset


lgr = logging.getLogger('datalad.distribution.remove')


@build_doc
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
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            check=True,
            if_dirty='save-before'):
        res_kwargs = dict(action='remove', logger=lgr)
        if dataset:
            dataset = require_dataset(
                dataset, check_installed=False, purpose='removal')
            if not dataset.is_installed() and not path:
                # all done already
                yield get_status_dict(
                    status='notneeded',
                    ds=dataset,
                    **res_kwargs)
            if not path:
                # act on the whole dataset if nothing else was specified
                path = dataset.path if isinstance(dataset, Dataset) else dataset
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=recursive)
        refds_path = dataset.path if isinstance(dataset, Dataset) else dataset
        res_kwargs['refds'] = refds_path
        if path_is_under(content_by_ds):
            # behave like `rm` and refuse to remove where we are
            raise ValueError(
                "refusing to uninstall current or parent directory")

        nonexistent_paths = []
        for p in unavailable_paths:
            # we need to check whether any of these correspond
            # to a known subdataset, and add those to the list of
            # things to be removed
            toppath = get_dataset_root(p)
            if not toppath:
                nonexistent_paths.append(p)
                continue
            if p in Dataset(toppath).subdatasets(
                    recursive=False, result_xfm='paths'):
                # this is a known subdataset that needs to be removed
                pl = content_by_ds.get(p, [])
                pl.append(p)
                content_by_ds[p] = pl
        for r in results_from_paths(
                nonexistent_paths, status='notneeded',
                message="path does not exist: %s",
                **res_kwargs):
            yield r

        # TODO generator
        # this should yield what it did
        handle_dirty_datasets(
            content_by_ds, mode=if_dirty, base=dataset)
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
                for r in _uninstall_dataset(ds, check=check, has_super=False,
                                            **res_kwargs):
                    yield r
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
            else:
                if check and hasattr(ds.repo, 'drop'):
                    for r in _drop_files(ds, paths, check=True):
                        yield r
                for r in ds.repo.remove(paths, r=True):
                    yield get_status_dict(
                        status='ok',
                        path=r,
                        **res_kwargs)

        if dataset and dataset.is_installed():
            # forge chain from base dataset to any leaf dataset
            # in order to save state changes all the way up
            _discover_trace_to_known(
                # from here
                dataset.path,
                # to any of
                list(content_by_ds.keys()),
                [],
                content_by_ds)

        for r in save_dataset_hierarchy(
                # pass list of datasets to save that excludes known
                # removed datasets to avoid "impossible" to save messages
                {d: p for d, p in content_by_ds.items()
                 if Dataset(d).is_installed()},
                base=dataset.path if dataset and dataset.is_installed() else None,
                message='[DATALAD] removed content'):
            yield r
