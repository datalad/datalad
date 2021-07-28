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
import itertools
import os.path as op

from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
)
from datalad.local.subdatasets import Subdatasets
from datalad.distribution.dataset import (
    datasetmethod,
    require_dataset,
)
from datalad.distribution.drop import (
    _drop_files,
    dataset_argument,
    check_argument,
)
from datalad.interface.base import Interface
from datalad.interface.common_opts import (
    if_dirty_opt,
    recursion_flag,
)
from datalad.interface.utils import (
    eval_results,
    handle_dirty_dataset,
)
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.utils import (
    rmtree,
    Path,
)


lgr = logging.getLogger('datalad.distribution.uninstall')


def _uninstall_dataset(ds, check, has_super, **kwargs):
    cwd = Path.cwd()
    if ds.pathobj == cwd or ds.pathobj in cwd.parents:
        yield get_status_dict(
            status='error',
            ds=ds,
            message='refusing to uninstall a dataset at or above the '
                    'current working directory',
            **kwargs)
        return
    if check and ds.is_installed():
        # if the checks are on we need to make sure to exit this function
        # whenever any drop failed, because we cannot rely on the error
        # to actually cause a stop in upstairs code
        bad_things_happened = False
        for r in _drop_files(
                ds, op.curdir, check=True, noannex_iserror=False, **kwargs):
            yield r
            if r['action'] == 'drop' and \
                    not r.get('status', None) in ('ok', 'notneeded'):
                bad_things_happened = True
        if bad_things_happened:
            # error reporting already happened, we can just stop here
            return

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
    if has_super and not op.exists(ds.path):
        # recreate an empty mountpoint to make Git happier
        os.makedirs(ds.path)
    # invalidate loaded ConfigManager:
    ds._cfg = None
    yield get_status_dict(status='ok', ds=ds, **kwargs)


@build_doc
class Uninstall(Interface):
    """Uninstall subdatasets

    This command can be used to uninstall any number of installed subdatasets.
    This command will error if individual files or non-dataset directories are
    given as input (use the drop or remove command depending on the desired
    goal), nor will it uninstall top-level datasets (i.e. datasets that are not
    a subdataset in another dataset; use the remove command for this purpose).

    By default, the availability of at least one remote copy for each currently
    available file in any dataset is verified. As these checks could lead to
    slow operation (network latencies, etc), they can be disabled.

    Any number of paths to process can be given as input. Recursion into
    subdatasets needs to be explicitly enabled, while recursion into
    subdirectories within a dataset is done automatically. An optional
    recursion limit is applied relative to each given input path.

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

    _examples_ = [
        dict(text="Uninstall a subdataset (undo installation)",
             code_py="uninstall(path='path/to/subds')",
             code_cmd="datalad uninstall <path/to/subds>"),
        dict(text="Uninstall a subdataset and all potential subdatasets",
             code_py="uninstall(path='path/to/subds', recursive=True)",
             code_cmd="datalad uninstall -r <path/to/subds>"),
        dict(text="Skip checks that ensure a minimal number of (remote) sources",
             code_py="uninstall(path='path/to/subds', check=False)",
             code_cmd="datalad uninstall <path/to/subds> --nocheck"),
    ]

    @staticmethod
    @datasetmethod(name=_action)
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            check=True,
            if_dirty='save-before'):
        refds = require_dataset(dataset, check_installed=True,
                                purpose='uninstall')
        res_kwargs = dict(action='uninstall', logger=lgr, refds=refds.path)
        if not path:
            # if no path is given, ie. refds is supposed to be uninstalled
            # check if refds is a subdataset itself, if not die
            # we only need to test that for the refds, everything else
            # will be guaranteed to be a subdataset
            parentds = refds.get_superdataset(
                datalad_only=False,
                topmost=False,
                # unless it is properly registered we have no way of
                # reinstalling it
                registered_only=True)
            if parentds is None:
                yield dict(
                    res_kwargs,
                    path=refds.path,
                    type='dataset',
                    status='error',
                    message="will not uninstall top-level dataset "
                            "(consider `remove` command)",
                )
                return

        saw_subds = False
        for ds in itertools.chain(Subdatasets.__call__(
                # it is critical to pass the dataset arg as-is
                # to not invalidate the path argument semantics
                # in subdatasets()
                dataset=dataset,
                path=path,
                fulfilled=True,
                # makes no sense to ignore subdatasets further down
                recursive=True,
                # important to start at the bottom for proper deinit
                bottomup=True,
                # doesn't make sense for uninstall
                #recursion_limit=recursion_limit,
                return_type='generator',
                result_renderer='disabled',
                result_xfm='datasets') if path or recursive else [],
                [refds] if not path else []):
            if ds != refds:
                saw_subds = True

            # TODO generator
            # this should yield what it did
            handle_dirty_dataset(ds, mode=if_dirty)
            # we confirmed the super dataset presence above
            for r in _uninstall_dataset(ds, check=check, has_super=True,
                                        **res_kwargs):
                yield r
        # there is nothing to save at the end
        if path and not saw_subds:
            lgr.warning(
                'path constraints did not match an installed subdataset: %s',
                path)
