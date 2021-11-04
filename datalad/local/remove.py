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

import logging
from itertools import chain

from os.path import (
    lexists,
)
from datalad.utils import (
    ensure_list,
    rmtree,
)
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.gitrepo import GitRepo
from datalad.distribution.dataset import (
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import Interface
from datalad.interface.common_opts import (
    jobs_opt,
    nosave_opt,
    save_message_opt,
)
from datalad.interface.utils import (
    eval_results,
)
from datalad.interface.base import build_doc
from datalad.distribution.uninstall import (
    dataset_argument,
)
from datalad.distributed.drop import (
    Drop,
)
from datalad.core.local.status import get_paths_by_ds
from datalad.core.local.save import Save


lgr = logging.getLogger('datalad.distribution.remove')


@build_doc
class Remove(Interface):
    """Remove components from datasets

    This command can remove subdatasets and paths, including non-empty
    directories, from datasets. Removing a component implies dropping present
    content and uninstalling associated subdatasets. Subsequently, the
    component is "unregistered" from the respective dataset. This means that
    the component is no longer present on the file system.

    By default, the availability of at least one remote copy is verified before
    file content is dropped. As these checks could lead to slow operation
    (network latencies, etc), they can be disabled.

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
        drop=Parameter(
            args=("--drop",),
            doc="""""",
            # we must not offer a 'nothing' which would bypass
            # the `drop()` call. The implementation completely
            # relies ob `drop()` for all safety measures.
            # instead `drop(reckless=kill)` must be used to fast-kill
            # things
            constraints=EnsureChoice('datasets', 'all')),
        recursive=Parameter(
            args=("--recursive", '-r',),
            doc="""DPERECATED and IGNORED"""),
        jobs=jobs_opt,
        message=save_message_opt,
        # XXX deprecate!
        save=nosave_opt,
    )
    # inherit some from Drop
    # if_dirty and check as deprecated
    for p in ('reckless', 'if_dirty', 'check',):
        _params_[p] = Drop._params_[p]

    _examples_ = [
        dict(text="Permanently remove a subdataset from a dataset and wipe out "
                  "the subdataset association too",
             code_py="remove(dataset='path/to/dataset', path='path/to/subds')",
             code_cmd="datalad remove -d <path/to/dataset> <path/to/subds>"),
        dict(text="Permanently remove a dataset and all subdatasets",
             code_py="remove(dataset='path/to/dataset', recursive=True)",
             code_cmd="datalad remove -d <path/to/dataset/> -r"),
        dict(text="Permanently remove a dataset and all subdatasets even if there "
                  "are fewer than the configured minimum number of (remote) sources "
                  "for data",
             code_py="remove(dataset='path/to/dataset', recursive=True, check=False)",
             code_cmd="datalad remove -d <path/to/dataset/> -r --nocheck"),
    ]

    @staticmethod
    @datasetmethod(name=_action)
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            drop='datasets',
            reckless=None,
            message=None,
            jobs=None,
            # deprecated below
            recursive=None,
            check=None,
            save=None,
            if_dirty='save-before'):

        # deprecate checks
        if check is False:
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
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            if res.get('action') == 'delete':
                # normalize to previous remove results
                res['action'] = 'remove'
            yield res
