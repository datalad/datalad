# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Thin shim around drop to preserve some backward-compatibility

"""

__docformat__ = 'restructuredtext'

import logging

from datalad.core.local.status import get_paths_by_ds
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import (
    if_dirty_opt,
    recursion_flag,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import handle_dirty_dataset
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.param import Parameter
from datalad.utils import ensure_list

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


@build_doc
class Uninstall(Interface):
    """DEPRECATED: use the `drop` command"""
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
            *,
            dataset=None,
            recursive=False,
            check=True,
            if_dirty='save-before'):
        # all this command does is to map legacy call to their replacement
        # with drop()
        import warnings
        warnings.warn(
            "The `uninstall` command is deprecated and will be removed in "
            "a future release. "
            "Use the `drop` command for safer operation instead.",
            DeprecationWarning)

        reckless = None
        if not check:
            # the old uninstall/drop combo had no checks beyond git-annex
            # key copy redundancy
            reckless = 'kill'

        paths_by_ds = None
        if (reckless == 'kill' and not recursive) or if_dirty != 'ignore':
            refds = require_dataset(dataset, check_installed=True,
                                    purpose='uninstall')
            # same path resolution that drop will do
            paths_by_ds, errors = get_paths_by_ds(
                refds, dataset, ensure_list(path),
                subdsroot_mode='sub')

        if reckless == 'kill' and not recursive:
            # drop requires recursive with kill
            # check check of the subdatasets to see if it is safe to enable it
            if all(not len(Dataset(d).subdatasets(
                    state='absent',
                    result_xfm='paths',
                    return_type='list',
                    result_renderer='disabled'))
                    for d in paths_by_ds.keys()):
                # no dataset has any subdatasets, this is fine to set
                recursive = True
        # it has never made sense, but for "compatibility" reasons, and to keep
        # the "old" implementation slower, even it uses the new implementation
        if if_dirty != 'ignore':
            for d in paths_by_ds.keys():
                handle_dirty_dataset(Dataset(d), mode=if_dirty)

        from datalad.api import drop
        lgr.debug(
            "Calling "
            "drop(dataset=%r, path=%r, recursive=%r, what='all', reckless=%r)",
            dataset, path, recursive, reckless)
        for res in drop(
            path=path,
            dataset=dataset,
            recursive=recursive,
            what='all',
            reckless=reckless,
            return_type='generator',
            result_renderer='disabled',
            # we need to delegate the decision making to this uninstall shim
            on_failure='ignore'):
            if res['status'] == 'error':
                msg, *rest = res["message"]
                if isinstance(msg, str) and "--reckless availability" in msg:
                    # Avoid confusing datalad-uninstall callers with the new
                    # drop parametrization while uninstall still exists.
                    msg = msg.replace("--reckless availability", "--nocheck")
                    res["message"] = (msg, *rest)
            yield res
        return
