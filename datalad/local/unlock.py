# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""For now just a proxy to git annex unlock

"""

__docformat__ = 'restructuredtext'

import logging
import os.path as op
from collections import defaultdict

from datalad.core.local.status import Status
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
    resolve_path,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.log import log_progress
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.param import Parameter
from datalad.utils import (
    Path,
    ensure_list,
)

lgr = logging.getLogger('datalad.local.unlock')


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
            *,
            dataset=None,
            recursive=False,
            recursion_limit=None):
        refds = require_dataset(dataset, check_installed=True,
                                purpose="unlock")

        # Before passing the results to status()
        #   * record explicitly specified non-directory paths so that we can
        #     decide whether to yield a result for reported paths
        #   * filter out and yield results for paths that don't exist
        res_paths_nondir = set()
        paths_lexist = None
        res_paths = list()
        if path:
            # Note, that we need unresolved versions of the path input to be
            # passed on to status. See gh-5456 for example.
            path = ensure_list(path)
            res_paths = resolve_path(path, ds=dataset)
            paths_lexist = []
            res_paths_lexist = []
            for p, p_r in zip(path, res_paths):
                if p_r.exists() or p_r.is_symlink():
                    paths_lexist.append(p)
                    res_paths_lexist.append(p_r)
                if not p_r.is_dir():
                    res_paths_nondir.add(p_r)

        res_kwargs = dict(action='unlock', logger=lgr, refds=refds.path)
        if res_paths:
            for p in set(res_paths).difference(set(res_paths_lexist)):
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
                untracked="normal" if res_paths_nondir else "no",
                annex="availability",
                recursive=recursive,
                recursion_limit=recursion_limit,
                result_renderer="disabled",
                return_type="generator",
                on_failure="ignore"):
            if res["action"] != "status" or res["status"] != "ok":
                yield res
                continue
            has_content = res.get("has_content")
            if has_content:
                parentds = res["parentds"]
                to_unlock[parentds].append(op.relpath(res["path"], parentds))
            elif res_paths_nondir and Path(res["path"]) in res_paths_nondir:
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
            # register for final orderly take down
            pbar_id = f'unlock-{ds_path}'
            nfiles = len(files)
            log_progress(
                lgr.info, pbar_id,
                'Unlocking files',
                unit=' Files',
                label='Unlocking',
                total=nfiles,
                noninteractive_level=logging.INFO,
            )
            ds = Dataset(ds_path)
            for r in ds.repo._call_annex_records_items_(
                    ["unlock"],
                    files=files,
            ):
                log_progress(
                    lgr.info, pbar_id,
                    "Files to unlock %i", nfiles,
                    update=1, increment=True,
                    noninteractive_level=logging.DEBUG)
                nfiles -= 1
                yield get_status_dict(
                    path=op.join(ds.path, r['file']),
                    status='ok' if r['success'] else 'error',
                    type='file',
                    **res_kwargs)
                if nfiles < 1:
                    # git-annex will spend considerable time after the last
                    # file record to finish things up, let this be known
                    log_progress(
                        lgr.info, pbar_id,
                        "Recording unlocked state in git",
                        update=0, increment=True,
                        noninteractive_level=logging.INFO)

            log_progress(
                lgr.info, pbar_id,
                "Completed unlocking files",
                noninteractive_level=logging.INFO)
