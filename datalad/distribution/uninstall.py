# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Thin shim around drop to preserve some backward-compatibility

"""

__docformat__ = 'restructuredtext'

import os
import logging
import os.path as op

from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
)
from datalad.distribution.dataset import (
    datasetmethod,
    require_dataset,
    Dataset,
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
    ensure_list,
    rmtree,
    Path,
)
from datalad.core.local.status import get_paths_by_ds


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
                    fulfilled=True,
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
        yield from drop(
            path=path,
            dataset=dataset,
            recursive=recursive,
            what='all',
            reckless=reckless,
            return_type='generator',
            result_renderer='disabled',
            # we need to delegate the decision making to this uninstall shim
            on_failure='ignore')
        return
