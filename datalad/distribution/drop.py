# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dropping dataset content

"""

__docformat__ = 'restructuredtext'

import logging

from os.path import (
    join as opj,
    isabs,
    normpath,
)
from datalad.utils import ensure_list
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.exceptions import (
    CommandError,
    InsufficientArgumentsError,
)
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    if_dirty_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import (
    get_status_dict,
    annexjson2result,
    success_status_map,
    results_from_annex_noinfo,
)
from datalad.interface.utils import (
    handle_dirty_dataset,
    eval_results,
)
from datalad.core.local.status import Status

lgr = logging.getLogger('datalad.distribution.drop')

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


def _postproc_result(res, respath_by_status, ds, **kwargs):
    res = annexjson2result(
        # annex reports are always about files
        res, ds, type='file', **kwargs)
    success = success_status_map[res['status']]
    respath_by_status[success] = \
        respath_by_status.get(success, []) + [res['path']]
    if res["status"] == "error" and res["action"] == "drop":
        msg = res["message"]
        if isinstance(msg, str) and "Use --force to" in msg:
            # Avoid confusing datalad-drop callers with git-annex-drop's
            # suggestion to use --force.
            res["message"] = msg.replace("--force", "--nocheck")
    return res


def _drop_files(ds, paths, check, noannex_iserror=False, **kwargs):
    """Helper to drop content in datasets.

    Parameters
    ----------
    ds : Dataset
    paths : path or list(path)
      which content to drop
    check : bool
      whether to instruct annex to perform minimum copy availability
      checks
    noannex_iserror : bool
      whether calling this function on a pure Git repo results in an
      'impossible' or 'notneeded' result.
    **kwargs
      additional payload for the result dicts
    """
    # expensive, access only once
    ds_repo = ds.repo
    if 'action' not in kwargs:
        kwargs['action'] = 'drop'
    # always need to make sure that we pass a list
    # `normalize_paths` decorator will otherwise screw all logic below
    paths = ensure_list(paths)
    if not hasattr(ds_repo, 'drop'):
        for p in paths:
            r = get_status_dict(
                status='impossible' if noannex_iserror else 'notneeded',
                path=p if isabs(p) else normpath(opj(ds.path, p)),
                message="no annex'ed content",
                **kwargs)
            r['action'] = 'drop'
            yield r
        return

    cmd = ['drop']
    if not check:
        cmd.append('--force')

    respath_by_status = {}
    try:
        yield from (
            _postproc_result(res, respath_by_status, ds)
            for res in ds_repo._call_annex_records(cmd, files=paths)
        )
    except CommandError as e:
        # pick up the results captured so far and yield them
        # the error will be amongst them
        yield from (
            _postproc_result(res, respath_by_status, ds)
            for res in e.kwargs.get('stdout_json', [])
        )
    # report on things requested that annex was silent about
    for r in results_from_annex_noinfo(
            ds, paths, respath_by_status,
            dir_fail_msg='could not drop some content in %s %s',
            noinfo_dir_msg='nothing to drop from %s',
            noinfo_file_msg="no annex'ed content",
            **kwargs):
        r['action'] = 'drop'
        yield r


@build_doc
class Drop(Interface):
    """Drop file content from datasets

    This command takes any number of paths of files and/or directories. If
    a common (super)dataset is given explicitly, the given paths are
    interpreted relative to this dataset.

    Recursion into subdatasets needs to be explicitly enabled, while recursion
    into subdirectories within a dataset is done automatically. An optional
    recursion limit is applied relative to each given input path.

    By default, the availability of at least one remote copy is verified before
    file content is dropped. As these checks could lead to slow operation
    (network latencies, etc), they can be disabled.

    """
    _examples_ = [
        dict(text="Drop single file content",
             code_py="drop('path/to/file')",
             code_cmd="datalad drop <path/to/file>"),
        dict(text="Drop all file content in the current dataset",
             code_py="drop('.')",
             code_cmd="datalad drop"),
        dict(text="Drop all file content in a dataset and all its subdatasets",
             code_py="drop(dataset='.', recursive=True)",
             code_cmd="datalad drop -d <path/to/dataset> -r"),
        dict(text="Disable check to ensure the configured minimum number of "
                  "remote sources for dropped data",
             code_py="drop(path='path/to/content', check=False)",
             code_cmd="datalad drop <path/to/content> --nocheck"),
    ]

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
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            check=True,
            if_dirty='save-before'):

        if not dataset and not path:
            raise InsufficientArgumentsError(
                "insufficient information for `drop`: requires at least a path or dataset")
        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='drop', logger=lgr, refds=refds_path)
        # this try-except dance is only to maintain a previous behavior of `drop`
        # where it did not ValueError, but yielded error status
        try:
            ds = require_dataset(
                dataset, check_installed=True, purpose='drop content')
        except ValueError as e:
            yield dict(
                status='error',
                message=str(e),
                **res_kwargs,
            )
            return

        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = refds_path
        content_by_ds = {}
        for st in Status.__call__(
                # do not use `ds` to preserve path semantics
                dataset=dataset,
                path=path,
                annex=None,
                untracked='no',
                recursive=recursive,
                recursion_limit=recursion_limit,
                eval_subdataset_state='no',
                report_filetype='raw',
                return_type='generator',
                result_renderer=None,
                # yield errors and let caller decide
                on_failure='ignore'):
            if st['status'] == 'error':
                # Downstream code can't do anything with these. Let the caller
                # decide their fate.
                yield st
                continue
            # ignore submodule entries
            if st.get('type') == 'dataset':
                if not Dataset(st['path']).is_installed():
                    continue
                parentds = st['path']
            else:
                parentds = st['parentds']
            cbd = content_by_ds.get(parentds, [])
            cbd.append(st['path'])
            content_by_ds[parentds] = cbd

        # iterate over all datasets, order doesn't matter
        for ds_path in content_by_ds:
            ds = Dataset(ds_path)
            # TODO generator
            # this should yield what it did
            handle_dirty_dataset(ds, mode=if_dirty)
            for r in _drop_files(
                    ds,
                    content_by_ds[ds_path],
                    check=check,
                    **res_kwargs):
                yield r
        # there is nothing to save at the end
