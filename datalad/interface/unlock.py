# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""For now just a proxy to git annex unlock

"""

__docformat__ = 'restructuredtext'

from collections import defaultdict
import logging

import os.path as op


from datalad.core.local.status import Status
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import resolve_path
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.utils import ensure_list
from datalad.utils import Path

from .base import Interface

lgr = logging.getLogger('datalad.interface.unlock')


@build_doc
class Unlock(Interface):
    """Unlock file(s) of a dataset

    Unlock files of a dataset in order to be able to edit the actual content
    """

    _params_ = dict(
        path=Parameter(
            args=("path",),
            doc="""file(s) to unlock""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to unlock files in. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    _examples_ = [
        dict(text="Unlock a single file",
             code_py="unlock(path='path/to/file')",
             code_cmd="datalad unlock <path/to/file>"),
        dict(text="Unlock all contents in the dataset",
             code_py="unlock('.')",
             code_cmd="datalad unlock ."),
    ]


    @staticmethod
    @datasetmethod(name='unlock')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            recursion_limit=None):
        refds = require_dataset(dataset, check_installed=True,
                                purpose="unlocking")

        # Before passing the results to status()
        #   * record explicitly specified non-directory paths so that we can
        #     decide whether to yield a result for reported paths
        #   * filter out and yield results for paths that don't exist
        paths_nondir = set()
        paths_lexist = None
        if path:
            path = resolve_path(ensure_list(path), ds=dataset)
            paths_lexist = []
            for p in path:
                if p.exists() or p.is_symlink():
                    paths_lexist.append(p)
                if not p.is_dir():
                    paths_nondir.add(p)

        res_kwargs = dict(action='unlock', logger=lgr, refds=refds.path)
        if path:
            for p in set(path).difference(set(paths_lexist)):
                yield get_status_dict(
                    status="impossible",
                    path=str(p),
                    type="file",
                    message="path does not exist",
                    **res_kwargs)
        if not (paths_lexist or paths_lexist is None):
            return

        # Collect information on the paths to unlock.
        to_unlock = defaultdict(list)  # ds => paths (relative to ds)
        for res in Status()(
                # ATTN: it is vital to pass the `dataset` argument as it,
                # and not a dataset instance in order to maintain the path
                # semantics between here and the status() call
                dataset=dataset,
                path=paths_lexist,
                untracked="normal" if paths_nondir else "no",
                report_filetype=False,
                annex="availability",
                recursive=recursive,
                recursion_limit=recursion_limit,
                result_renderer='disabled',
                on_failure="ignore"):
            if res["action"] != "status" or res["status"] != "ok":
                yield res
                continue
            has_content = res.get("has_content")
            if has_content:
                parentds = res["parentds"]
                to_unlock[parentds].append(op.relpath(res["path"], parentds))
            elif paths_nondir and Path(res["path"]) in paths_nondir:
                if has_content is False:
                    msg = "no content present"
                    status = "impossible"
                elif res["state"] == "untracked":
                    msg = "untracked"
                    status = "impossible"
                else:
                    # This is either a regular git file or an unlocked annex
                    # file.
                    msg = "non-annex file"
                    status = "notneeded"
                yield get_status_dict(
                    status=status,
                    path=res["path"],
                    type="file",
                    message="{}; cannot unlock".format(msg),
                    **res_kwargs)

        # Do the actual unlocking.
        for ds_path, files in to_unlock.items():
            ds = Dataset(ds_path)
            for r in ds.repo._call_annex_records(
                    ["unlock"],
                    files=files):
                yield get_status_dict(
                    path=op.join(ds.path, r['file']),
                    status='ok' if r['success'] else 'error',
                    type='file',
                    **res_kwargs)
