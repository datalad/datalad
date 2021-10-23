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

from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
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
    jobs_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import (
    annexjson2result,
    success_status_map,
    results_from_annex_noinfo,
)
from datalad.interface.utils import (
    eval_results,
)
from datalad.local.subdatasets import Subdatasets
from datalad.utils import ensure_list
from datalad.core.local.status import get_paths_by_ds
from datalad.support.annexrepo import AnnexRepo
from datalad.runner.exception import CommandError

lgr = logging.getLogger('datalad.distributed.drop')


@build_doc
class Drop(Interface):
    """DOCUMENT ME
    """
    _examples_ = [
    ]

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="DATASET",
            doc="""specify the dataset to perform the drop on.
            If no dataset is given, the current working directory is used
            as operation context""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path of the component to be dropped",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        reckless=Parameter(
            args=("--reckless",),
            doc="""""",
            constraints=EnsureChoice(None)),
        what=Parameter(
            args=("--what",),
            doc="""""",
            constraints=EnsureChoice('filecontent', 'allkeys', 'all')),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        jobs=jobs_opt,
        check=Parameter(
            args=("--nocheck",),
            doc="""DEPRECATED: use '--reckless availability'""",
            action="store_false",
            dest='check'),
        if_dirty=Parameter(
            args=("--if-dirty",),
            doc="""DEPRECATED: use --reckless instead""",
            constraints=EnsureChoice('fail', 'save-before', 'ignore', None)),
    )

    @staticmethod
    @datasetmethod(name='drop')
    @eval_results
    def __call__(
            path=None,
            what='filecontent',
            reckless=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            jobs=None,
            # deprecated
            check=None,
            # TODO deal with deprecation
            if_dirty=None):

        # TODO deprecation warning on `check`
        if check is False:
            # TODO check for conflict with new reckless parameter
            reckless = 'availability'

        ds = require_dataset(dataset, check_installed=True, purpose='drop')

        res_props = dict(
            logger=lgr,
            refds=ds.path,
        )
        # if not paths are given, there will still be a single dataset record
        # with paths==None
        paths_by_ds, errors = get_paths_by_ds(ds, dataset, ensure_list(path))
        for e in errors:
            yield dict(
                action='drop',
                path=str(e),
                status='error',
                message=('path not underneath the reference dataset %s', ds),
                **res_props)
            # we are not returning, a caller could decide on failure mode

        lgr.debug('Discovered %i datasets to drop (from)',len(paths_by_ds))

        # a dataset paths are normalized and guaranteed to be under the same
        # root dataset
        # we want to start from the leave datasets, such that all discovered
        # dataset can be processed independently
        for dpath in sorted(paths_by_ds.keys(), reverse=True):
            d = Dataset(dpath)
            lgr.debug('Starting to drop %s at %s', what, d)
            for res in _drop_dataset(
                    d,
                    paths_by_ds[dpath],
                    what=what,
                    reckless=reckless,
                    # recursion from any of the given paths!
                    recursive=recursive,
                    recursion_limit=recursion_limit,
                    jobs=jobs):
                yield dict(res, **res_props)
            lgr.debug('Finished dropping %s at %s', what, d)
        return


def _drop_dataset(ds, paths, what, reckless, recursive, recursion_limit, jobs):
    # we know that any given path is part of `ds` and not any of its
    # subdatasets!
    if recursive:
        # process subdatasets first with recursion
        for sub in ds.subdatasets(
                # must be resolved!
                path=paths or None,
                # nothing to drop with unavailable subdatasets
                fulfilled=True,
                # we can use the full recursion depth, only the first layer
                # of calls to _drop_dataset() must/can have recursive=True
                recursive=recursive,
                recursion_limit=recursion_limit,
                # start reporting with the leaves
                bottomup=True,
                result_xfm='datasets',
                on_failure='ignore',
                result_renderer='disabled'):
            yield from _drop_dataset(
                ds=sub,
                # everything, the entire subdataset is matching a given path
                paths=None,
                what=what,
                reckless=reckless,
                recursive=False,
                recursion_limit=None,
                jobs=jobs)

    if reckless not in ('modification',):
        # do a cheaper status run to discover any kind of modification and
        # generate results based on the `what` mode of operation
        for res in ds.status(
                path=paths,
                # untracked content will not be reported on further down
                # must catch it here
                untracked='normal',
                # downstream code can handle non-annex/annex distinction
                # avoid expensive evaluation here
                annex=False,
                # we only need to inspect a subdataset's state in case
                # we want to drop it completely
                eval_subdataset_state='commit' if what in ('all',) else 'no',
                # recursion is handled outside this function
                recursive=False,
                result_renderer='disabled',
                on_failure='ignore'):
            state = res.get('state')
            if state == 'clean':
                # nothing to worry about, nothing to communicate
                continue
            elif state in ('modified', 'untracked'):
                yield dict(
                    res,
                    status='impossible',
                    action='drop',
                    message=f'cannot drop {state} content, save first',
                )
                # we are not aborting nevetheless. in normal conditions
                # the above result will stop processing, but if desired
                # we could go on
            else:
                lgr.debug(
                    'Status record not considered for drop '
                    'state inspection: %s', res)
    repo = ds.repo
    is_annex = isinstance(repo, AnnexRepo)

    if what == 'filecontent':
        if not is_annex:
            # TODO maybe play save and ensure_list(paths), it could be None
            # or just one 'notneeded' result for the entire dataset with
            # paths=None
            for p in paths:
                yield dict(
                    action='drop',
                    path=str(p),
                    status='notneeded',
                    message="no annex'ed content",
                )
        elif not paths:
            # XXX should we only drop filecontent with particular paths
            # specified? e.g. '.'
            # MIH: right now I don't think so, because running drop without
            # should be safe by default in the end
            pass
        else:
            # we have an annex and paths
            yield from _drop_files(
                ds,
                repo,
                paths=[str(p.relative_to(ds.pathobj)) for p in paths],
                force=reckless in ('availability',)
            )

    # all subdatasets are taken care of. now we have a a single dataset to
    # process
    # first some checks
    if what == 'all':
        # check for installed subdatasets, none should have remained by now
        # or recursive was forgotten

        if reckless == 'noavailability':
            # wipe out dataset
            return
    if what in ('all', 'allkeys'):
        # yield impossible result, with a path constraint
        # either we drop all, or by path, but not both

        # check for configured availability of all present keys (not just
        # for files in branch)
        #drop-all-keys
        pass

    if what == 'all':
        if reckless != 'undead':
            # announce local annex to be dead
            #push-annex-branch-to-remotes
            pass

        # kill repository
    return


def _drop_files(ds, repo, paths, force=False):
    """Helper to drop content in datasets.

    Parameters
    ----------
    repo : AnnexRepo
    paths : list
      for which files to drop content
    check : bool
      whether to instruct annex to perform minimum copy availability
      checks

    Yields
    ------
    dict
    """
    cmd = ['drop']
    if force:
        cmd.append('--force')

    respath_by_status = {}
    try:
        yield from (
            _postproc_annexdrop_result(res, respath_by_status, ds)
            for res in repo._call_annex_records(cmd, files=paths)
        )
    except CommandError as e:
        # pick up the results captured so far and yield them
        # the error will be amongst them
        yield from (
            _postproc_annexdrop_result(res, respath_by_status, ds)
            for res in e.kwargs.get('stdout_json', [])
        )
    # report on things requested that annex was silent about
    for r in results_from_annex_noinfo(
            ds, paths, respath_by_status,
            dir_fail_msg='could not drop some content in %s %s',
            noinfo_dir_msg='nothing to drop from %s',
            noinfo_file_msg="no annex'ed content"):
        r['action'] = 'drop'
        yield r


def _postproc_annexdrop_result(res, respath_by_status, ds, **kwargs):
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
            # Just mention reckless itself, do not go into the details
            # of which mode. This is likely changing over time and
            # adjusting this replacement will be forgotten.
            res["message"] = msg.replace("--force", "--reckless")
    return res


