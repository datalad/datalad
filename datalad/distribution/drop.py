# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Residual functionality for dropping dataset content

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
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import (
    CommandError,
)
from datalad.distribution.dataset import (
    EnsureDataset,
)
from datalad.interface.results import (
    get_status_dict,
    annexjson2result,
    success_status_map,
    results_from_annex_noinfo,
)

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
