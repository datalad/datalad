# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for uninstalling datasets

"""

__docformat__ = 'restructuredtext'

import os
import logging

from os.path import curdir
from os.path import exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.distribution.dataset import Dataset, datasetmethod
from datalad.distribution.drop import _drop_files
from datalad.distribution.drop import dataset_argument
from datalad.distribution.drop import check_argument
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.base import Interface
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.utils import path_is_under
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.utils import handle_dirty_dataset
from datalad.interface.results import get_status_dict
from datalad.utils import rmtree


lgr = logging.getLogger('datalad.distribution.uninstall')


def _uninstall_dataset(ds, check, has_super, **kwargs):
    if check and ds.is_installed():
        for r in _drop_files(
                ds, curdir, check=True, noannex_iserror=False, **kwargs):
            yield r
    # TODO: uninstall of a subdataset that has a local URL
    #       (e.g. ./anything) implies cannot be undone, decide how, and
    #       if to check for that
    # TODO check that the relevant branched are pushed to a remote
    if ds.subdatasets(fulfilled=True):
        yield get_status_dict(
            status='error',
            ds=ds,
            message=(
                'to be uninstalled dataset %s has present subdatasets, forgot --recursive?',
                ds),
            **kwargs)
        return
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
    yield get_status_dict(status='ok', ds=ds, **kwargs)


@build_doc
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
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            check=True,
            if_dirty='save-before'):

        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='uninstall', logger=lgr, refds=refds_path)
        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = refds_path
        if not dataset and not path:
            raise InsufficientArgumentsError(
                "insufficient information for `uninstall`: requires at least a path or dataset")

        to_uninstall = []
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                action='uninstall',
                # justification for status:
                # content need not be uninstalled where there is none
                unavailable_path_status='notneeded',
                nondataset_path_status='error',
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            # upfront sanity and compliance checks
            # check that we have no top-level datasets and not files to process
            if ap.get('type') == 'dataset' and \
                    not ap.get('state', None) == 'absent' and \
                    path_is_under([ap['path']]):  # wants a sequence!
                ap.update(
                    status='error',
                    message="refusing to uninstall current or parent directory")
                yield ap
                continue
            if not ap.get('type', None) == 'dataset':
                ap.update(
                    status='impossible',
                    message="can only uninstall datasets (consider the `drop` command)")
                yield ap
                continue
            # we only have dataset from here
            if not ap.get('parentds', None):
                ap.update(
                    status='error',
                    message="will not uninstall top-level dataset (consider `remove` command)")
                yield ap
                continue
            if not ap['path'] == refds_path:
                ap['process_content'] = True
            to_uninstall.append(ap)

        # iterate over all datasets, starting at the bottom
        # to deinit contained submodules first
        for ap in sorted(to_uninstall, key=lambda x: x['path'], reverse=True):
            if ap.get('state', None) == 'absent':
                # already gone
                continue
            ds = Dataset(ap['path'])
            # TODO generator
            # this should yield what it did
            handle_dirty_dataset(ds, mode=if_dirty)
            # we confirmed the super dataset presence above
            for r in _uninstall_dataset(ds, check=check, has_super=True,
                                        **res_kwargs):
                yield r
        # there is nothing to save at the end
