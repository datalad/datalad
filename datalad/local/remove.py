# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for removing dataset content

"""

__docformat__ = 'restructuredtext'

import logging
from os.path import lexists
import warnings

from datalad.core.local.save import Save
from datalad.core.local.status import get_paths_by_ds
from datalad.distributed.drop import Drop
from datalad.distribution.dataset import (
    datasetmethod,
    require_dataset,
    EnsureDataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    jobs_opt,
    save_message_opt,
)
from datalad.interface.utils import eval_results
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.utils import (
    ensure_list,
    rmtree,
)

lgr = logging.getLogger('datalad.local.remove')


@build_doc
class Remove(Interface):
    """Remove components from datasets

    Removing "unlinks" a dataset component, such as a file or subdataset, from
    a dataset. Such a removal advances the state of a dataset, just like adding
    new content. A remove operation can be undone, by restoring a previous
    dataset state, but might require re-obtaining file content and subdatasets
    from remote locations.

    This command relies on the 'drop' command for safe operation. By default,
    only file content from datasets which will be uninstalled as part of
    a removal will be dropped. Otherwise file content is retained, such that
    restoring a previous version also immediately restores file content access,
    just as it is the case for files directly committed to Git. This default
    behavior can be changed to always drop content prior removal, for cases
    where a minimal storage footprint for local datasets installations is
    desirable.

    Removing a dataset component is always a recursive operation. Removing a
    directory, removes all content underneath the directory too. If
    subdatasets are located under a to-be-removed path, they will be
    uninstalled entirely, and all their content dropped. If any subdataset
    can not be uninstalled safely, the remove operation will fail and halt.

    .. versionchanged:: 0.16
       More in-depth and comprehensive safety-checks are now performed by
       default.
       The ``if_dirty||--if-dirty`` argument is ignored, will be removed in
       a future release, and can be removed for a safe-by-default behavior. For
       other cases consider the ``reckless||--reckless`` argument.
       The ``save||--save`` argument is ignored and will be removed in a future
       release, a dataset modification is now always saved. Consider save's
       ``amend||--amend`` argument for post-remove fix-ups.
       The ``recursive||--recursive`` argument is ignored, and will be removed
       in a future release. Removal operations are always recursive, and the
       parameter can be stripped from calls for a safe-by-default behavior.

    .. deprecated:: 0.16
       The ``check||--check`` argument will be removed in a future release.
       It needs to be replaced with ``reckless||--reckless``.
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="DATASET",
            doc="""specify the dataset to perform remove from.
            If no dataset is given, the current working directory is used
            as operation context""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path of a dataset or dataset component to be removed",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        drop=Parameter(
            args=("--drop",),
            doc="""which dataset components to drop prior removal. This
            parameter is passed on to the underlying drop operation as
            its 'what' argument.""",
            # we must not offer a 'nothing' which would bypass
            # the `drop()` call. The implementation completely
            # relies on `drop()` for all safety measures.
            # instead `drop(reckless=kill)` must be used to fast-kill
            # things
            constraints=EnsureChoice('datasets', 'all')),
        jobs=jobs_opt,
        message=save_message_opt,
        # XXX deprecate!
        save=Parameter(
            args=("--nosave",),
            dest='save',
            action="store_false",
            doc="""DEPRECATED and IGNORED; use `save --amend` instead"""),
        recursive=Parameter(
            args=("--recursive", '-r',),
            action='store_const',
            const=None,
            doc="""DEPRECATED and IGNORED: removal is always a recursive
            operation"""),
    )
    # inherit some from Drop
    # if_dirty and check as deprecated
    for p in ('reckless', 'if_dirty', 'check',):
        _params_[p] = Drop._params_[p]

    _examples_ = [
        dict(text="Permanently remove a subdataset (and all further subdatasets contained in it) from a dataset",
             code_py="remove(dataset='path/to/dataset', path='path/to/subds')",
             code_cmd="datalad remove -d <path/to/dataset> <path/to/subds>"),
             dict(text="Permanently remove a superdataset (with all subdatasets) from the filesystem",
             code_py="remove(dataset='path/to/dataset')",
             code_cmd="datalad remove -d <path/to/dataset>"),
             dict(text="DANGER-ZONE: Fast wipe-out a dataset and all its subdataset, bypassing all safety checks",
             code_py="remove(dataset='path/to/dataset', reckless='kill')",
             code_cmd="datalad remove -d <path/to/dataset> --reckless kill"),
    ]

    @staticmethod
    @datasetmethod(name='remove')
    @eval_results
    def __call__(
            path=None,
            *,
            dataset=None,
            drop='datasets',
            reckless=None,
            message=None,
            jobs=None,
            # deprecated below
            recursive=None,
            check=None,
            save=None,
            if_dirty=None):

        # deprecate checks
        if if_dirty is not None:
            warnings.warn(
                "The `if_dirty` argument of `datalad remove` is ignored, "
                "it can be removed for a safe-by-default behavior. For "
                "other cases consider the `reckless` argument.",
                DeprecationWarning)

        if save is not None:
            warnings.warn(
                "The `save` argument of `datalad remove` is ignored. "
                "A dataset modification is always saved. Consider "
                "`save --amend` if post-remove fix-ups are needed.",
                DeprecationWarning)

        if recursive is not None:
            warnings.warn(
                "The `recursive` argument of `datalad remove` is ignored. "
                "Removal operations are always recursive, and the parameter "
                "can be stripped from calls for a safe-by-default behavior. ",
                DeprecationWarning)

        if check is not None:
            warnings.warn(
                "The `check` argument of `datalad remove` is deprecated, "
                "use the `reckless` argument instead.",
                DeprecationWarning)

        if check is False:
            if reckless is not None:
                raise ValueError(
                    'Must not use deprecated `check` argument, and new '
                    '`reckless` argument together with `datalad remove`.')
            reckless = 'availability'

        refds = require_dataset(dataset, check_installed=True,
                                purpose='remove')
        # same path resolution that drop will do
        paths_by_ds, errors = get_paths_by_ds(
            refds, dataset, ensure_list(path),
            # super-mode will readily tell us which datasets to
            # save as the end
            subdsroot_mode='super')

        drop_success = True
        for res in Drop.__call__(
                dataset=dataset,
                path=path,
                what=drop,
                reckless=reckless,
                recursive=True,
                recursion_limit=None,
                jobs=jobs,
                result_xfm=None,
                return_type='generator',
                result_renderer='disabled',
                # delegate error handling here
                on_failure='ignore'):
            if res.get('status') not in ('ok', 'notneeded'):
                drop_success = False
            yield res

        if not drop_success:
            # there will be 'rm -rf' below, so play safe
            lgr.debug('Observed drop failure, will not attempt remove')
            return

        for dpath, paths in paths_by_ds.items():
            for delpath in ([dpath] if paths is None else paths):
                if lexists(str(delpath)):
                    # here we still have something around on the
                    # filesystem. There is no need to fiddle with
                    # Git, just wipe it out. A later save() will
                    # act on it properly
                    if delpath.is_dir():
                        lgr.debug('Remove directory: %s', delpath)
                        rmtree(delpath)
                    # cannot use .exists() must forsee dead symlinks
                    else:
                        lgr.debug('Remove file: %s', delpath)
                        delpath.unlink()
                    continue
                # if we get here, there is nothing on the file system
                # anymore at this path. Either because the parent
                # dataset vanished already, or because we dropped a
                # dataset, and it still needs to be unregistered
                # from its parent -> `git rm`
                if dpath.exists():
                    GitRepo(dpath).call_git(
                        # no need for recursion, we know that even the root
                        # path not longer exists
                        ['rm', '-q'],
                        files=[str(delpath.relative_to(dpath))]
                    )
                    # this path was already being removed by drop
                    # so it must belong to a dropped dataset
                    # save won't report about this, let's do it
                    yield dict(
                        action='remove',
                        status='ok',
                        path=str(delpath),
                        type='dataset',
                    )

        if not refds.is_installed():
            # we already dropped the whole thing
            return

        for res in Save.__call__(
                dataset=dataset,
                path=path,
                # we might have removed the reference dataset by now, recheck
                message=message if message else '[DATALAD] removed content',
                return_type='generator',
                result_renderer='disabled',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            if res.get('action') == 'delete':
                # normalize to previous remove results
                res['action'] = 'remove'
            yield res
