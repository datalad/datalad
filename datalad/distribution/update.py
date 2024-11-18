# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for updating a dataset

"""

__docformat__ = 'restructuredtext'


import itertools
import logging
from os.path import lexists

from datalad.distribution.dataset import require_dataset
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import (
    YieldDatasets,
    get_status_dict,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureBool,
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
)
from datalad.support.param import Parameter

from .dataset import (
    EnsureDataset,
    datasetmethod,
)

lgr = logging.getLogger('datalad.distribution.update')


class YieldDatasetAndRevision(YieldDatasets):
    """Like YieldDatasets, but also provide "gitshasum" value, if any.
    """
    def __call__(self, res):
        ds = super(YieldDatasetAndRevision, self).__call__(res)
        return ds, res.get("gitshasum")


def _process_how_args(merge, how, how_subds):
    """Resolve how-related arguments into `how` and `how_subds` values.
    """
    # Translate old --merge value onto --how
    if merge and (how or how_subds):
        raise ValueError("`merge` is incompatible with `how` and `how_subds`")
    elif merge == "ff-only":
        how = merge
    elif merge:
        how = "merge"

    if how == "fetch":
        how = None

    # Map "fetch" to None for easier conditions.
    if how_subds == "fetch":
        how_subds = None
    elif how_subds is None:
        # Subdatasets are updated according to --how unless --how-subds is
        # given.
        how_subds = how
    return how, how_subds


_how_constraints = EnsureChoice(
    "fetch", "merge", "ff-only", "reset", "checkout", None)


@build_doc
class Update(Interface):
    """Update a dataset from a sibling.

    """
    # TODO: adjust docs to say:
    # - update from just one sibling at a time

    _examples_ = [
        dict(text="Update from a particular sibling",
             code_py="update(sibling='siblingname')",
             code_cmd="datalad update -s <siblingname>"),
        dict(text="Update from a particular sibling and merge the changes "
                  "from a configured or matching branch from the sibling "
                  "(see [CMD: --follow CMD][PY: `follow` PY] for details)",
             code_py="update(sibling='siblingname', how='merge')",
             code_cmd="datalad update --how=merge -s <siblingname>"),
        dict(text="Update from the sibling 'origin', traversing into "
                  "subdatasets. For subdatasets, merge the revision "
                  "registered in the parent dataset into the current branch",
             code_py="update(sibling='origin', how='merge', "
                     "follow='parentds', recursive=True)",
             code_cmd="datalad update -s origin --how=merge "
                      "--follow=parentds -r"),
        dict(text="Fetch and merge the remote tracking branch "
                  "into the current dataset. Then update each subdataset "
                  "by resetting its current branch to the revision "
                  "registered in the parent dataset, fetching only if "
                  "the revision isn't already present",
             code_py="update(how='merge', how_subds='reset', "
                     "follow='parentds-lazy', recursive=True)",
             code_cmd="datalad update --how=merge --how-subds=reset "
                      "--follow=parentds-lazy -r"),
    ]

    _params_ = dict(
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""constrain to-be-updated subdatasets to the given path for recursive
            operation.""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        sibling=Parameter(
            args=("-s", "--sibling",),
            doc="""name of the sibling to update from. When unspecified,
            updates from all siblings are fetched. If there is more than one
            sibling and changes will be brought into the working tree (as
            requested via [CMD: --merge, --how, or --how-subds CMD][PY:
            `merge`, `how`, or `how_subds` PY]), a sibling will be chosen based
            on the configured remote for the current branch.""",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to update.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        merge=Parameter(
            args=("--merge",),
            metavar="ALLOWED",
            # const and nargs are set to map --merge to --merge=any.
            const="any",
            nargs="?",
            constraints=EnsureBool() | EnsureChoice("any", "ff-only"),
            # TODO: Decide whether this should be removed eventually.
            doc="""merge obtained changes from the sibling. This is a subset of
            the functionality that can be achieved via the newer [CMD: --how
            CMD][PY: `how` PY]. [CMD: --merge or --merge=any CMD][PY:
            merge=True or merge="any" PY] is equivalent to [CMD: --how=merge
            CMD][PY: how="merge" PY]. [CMD: --merge=ff-only CMD][PY:
            merge="ff-only" PY] is equivalent to [CMD: --how=ff-only CMD][PY:
            how="ff-only" PY]."""),
        how=Parameter(
            args=("--how",),
            nargs="?",
            constraints=_how_constraints,
            doc="""how to update the dataset. The default ("fetch") simply
            fetches the changes from the sibling but doesn't incorporate them
            into the working tree. A value of "merge" or "ff-only" merges in
            changes, with the latter restricting the allowed merges to
            fast-forwards. "reset" incorporates the changes with 'git reset
            --hard <target>', staying on the current branch but discarding any
            changes that aren't shared with the target. "checkout", on the
            other hand, runs 'git checkout <target>', switching from the
            current branch to a detached state. When [CMD: --recursive CMD][PY:
            recursive=True PY] is specified, this action will also apply to
            subdatasets unless overridden by [CMD: --how-subds CMD][PY:
            `how_subds` PY]."""),
        how_subds=Parameter(
            args=("--how-subds",),
            nargs="?",
            constraints=_how_constraints,
            doc="""Override the behavior of [CMD: --how CMD][PY: `how` PY] in
            subdatasets."""),
        follow=Parameter(
            args=("--follow",),
            constraints=EnsureChoice("sibling", "parentds", "parentds-lazy"),
            doc="""source of updates for subdatasets. For 'sibling', the update
            will be done by merging in a branch from the (specified or
            inferred) sibling. The branch brought in will either be the current
            branch's configured branch, if it points to a branch that belongs
            to the sibling, or a sibling branch with a name that matches the
            current branch. For 'parentds', the revision registered in the
            parent dataset of the subdataset is merged in. 'parentds-lazy' is
            like 'parentds', but prevents fetching from a subdataset's sibling
            if the registered revision is present in the subdataset. Note that
            the current dataset is always updated according to 'sibling'. This
            option has no effect unless a merge is requested and [CMD:
            --recursive CMD][PY: recursive=True PY] is specified.""", ),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        fetch_all=Parameter(
            args=("--fetch-all",),
            action="store_true",
            doc="""this option has no effect and will be removed in a future version.
            When no siblings are given, an all-sibling update will be performed.""", ),
        reobtain_data=Parameter(
            args=("--reobtain-data",),
            action="store_true",
            doc="""if enabled, file content that was present before an update
            will be re-obtained in case a file was changed by the update."""), )

    @staticmethod
    @datasetmethod(name='update')
    @eval_results
    def __call__(
            path=None,
            *,
            sibling=None,
            merge=False,
            how=None,
            how_subds=None,
            follow="sibling",
            dataset=None,
            recursive=False,
            recursion_limit=None,
            fetch_all=None,
            reobtain_data=False):
        if fetch_all is not None:
            lgr.warning('update(fetch_all=...) called. Option has no effect, and will be removed')
        if path and not recursive:
            lgr.warning('path constraints for subdataset updates ignored, '
                        'because `recursive` option was not given')

        how, how_subds = _process_how_args(merge, how, how_subds)
        # `merge` should be considered through `how` and `how_subds` only.
        # Unbind `merge` to ensure that downstream code doesn't look at it.
        del merge

        refds = require_dataset(dataset, check_installed=True, purpose='update')

        save_paths = []
        update_failures = set()
        saw_subds = False
        for ds, revision in itertools.chain([(refds, None)], refds.subdatasets(
                path=path,
                state='present',
                recursive=recursive,
                recursion_limit=recursion_limit,
                return_type='generator',
                result_renderer='disabled',
                result_xfm=YieldDatasetAndRevision()) if recursive else []):
            if ds != refds:
                saw_subds = True
            repo = ds.repo
            is_annex = isinstance(repo, AnnexRepo)
            # prepare return value
            res = get_status_dict('update', ds=ds, logger=lgr, refds=refds.path)

            follow_parent = revision and follow.startswith("parentds")
            follow_parent_lazy = revision and follow == "parentds-lazy"
            if follow_parent_lazy and \
               repo.get_hexsha(repo.get_corresponding_branch()) == revision:
                res["message"] = (
                    "Dataset already at commit registered in parent: %s",
                    repo.path)
                res["status"] = "notneeded"
                yield res
                continue

            how_curr = how_subds if revision else how
            # get all remotes which have references (would exclude
            # special remotes)
            remotes = repo.get_remotes(
                **({'exclude_special_remotes': True} if is_annex else {}))
            if not remotes and not sibling:
                res['message'] = ("No siblings known to dataset at %s\nSkipping",
                                  repo.path)
                res['status'] = 'notneeded'
                yield res
                continue
            curr_branch = repo.get_active_branch()
            tracking_remote = None
            if not sibling and len(remotes) == 1:
                # there is only one remote, must be this one
                sibling_ = remotes[0]
            elif not sibling:
                # nothing given, look for tracking branch
                tracking_remote = repo.get_tracking_branch(
                    branch=curr_branch, remote_only=True)[0]
                sibling_ = tracking_remote
            else:
                sibling_ = sibling
            if sibling_ and sibling_ not in remotes:
                res['message'] = ("'%s' not known to dataset %s\nSkipping",
                                  sibling_, repo.path)
                res['status'] = 'impossible'
                yield res
                continue
            if not sibling_ and len(remotes) > 1 and how_curr:
                lgr.debug("Found multiple siblings:\n%s", remotes)
                res['status'] = 'impossible'
                res['message'] = "Multiple siblings, please specify from which to update."
                yield res
                continue
            lgr.info("Fetching updates for %s", ds)
            # fetch remote
            fetch_kwargs = dict(
                # test against user-provided value!
                remote=None if sibling is None else sibling_,
                all_=sibling is None,
                git_options=[
                    # required to not trip over submodules that were removed in
                    # the origin clone
                    "--no-recurse-submodules",
                    # prune to not accumulate a mess over time
                    "--prune"]
            )
            if not (follow_parent_lazy and repo.commit_exists(revision)):
                try:
                    repo.fetch(**fetch_kwargs)
                except CommandError as exc:
                    ce = CapturedException(exc)
                    yield get_status_dict(status="error",
                                          message=("Fetch failed: %s", ce),
                                          exception=ce,
                                          **res,)
                    continue

            # NOTE reevaluate ds.repo again, as it might have be converted from
            # a GitRepo to an AnnexRepo
            repo = ds.repo

            if follow_parent and not repo.commit_exists(revision):
                if sibling_:
                    try:
                        lgr.debug("Fetching revision %s directly for %s",
                                  revision, repo)
                        repo.fetch(remote=sibling_, refspec=revision,
                                   git_options=["--recurse-submodules=no"])
                    except CommandError as exc:
                        ce = CapturedException(exc)
                        yield dict(
                            res,
                            status="impossible",
                            message=(
                                "Attempt to fetch %s from %s failed: %s",
                                revision, sibling_, ce),
                            exception=ce
                        )
                        continue
                else:
                    yield dict(res,
                               status="impossible",
                               message=("Need to fetch %s directly "
                                        "but single sibling not resolved",
                                        revision))
                    continue

            saw_update_failure = False
            if how_curr:
                if follow_parent:
                    target = revision
                else:
                    target = _choose_update_target(
                        repo, curr_branch,
                        sibling_, tracking_remote)

                adjusted = is_annex and repo.is_managed_branch(curr_branch)
                if adjusted:
                    if follow_parent:
                        yield dict(
                            res, status="impossible",
                            message=("follow='parentds' is incompatible "
                                     "with adjusted branches"))
                        continue
                    if how_curr != "merge":
                        yield dict(
                            res, status="impossible",
                            message=("Updating via '%s' is incompatible "
                                     "with adjusted branches",
                                     how_curr))
                        continue

                update_fn = _choose_update_fn(
                    repo,
                    how_curr,
                    is_annex=is_annex,
                    adjusted=adjusted)

                fn_opts = ["--ff-only"] if how_curr == "ff-only" else None
                if update_fn is not _annex_sync:
                    if target is None:
                        yield dict(res,
                                   status="impossible",
                                   message="Could not determine update target")
                        continue

                if is_annex and reobtain_data:
                    update_fn = _reobtain(ds, update_fn)

                for ures in update_fn(repo, sibling_, target, opts=fn_opts):
                    # NOTE: Ideally the "merge" action would also be prefixed
                    # with "update.", but a plain "merge" is used for backward
                    # compatibility.
                    if ures["status"] != "ok" and (
                            ures["action"] == "merge" or
                            ures["action"].startswith("update.")):
                        saw_update_failure = True
                    yield dict(res, **ures)

            if saw_update_failure:
                update_failures.add(ds)
                res['status'] = 'error'
                res['message'] = ("Update of %s failed", target)
            else:
                res['status'] = 'ok'
                save_paths.append(ds.path)
            yield res
        # we need to save updated states only if merge was requested -- otherwise
        # it was a pure fetch
        if how_curr and recursive:
            yield from _save_after_update(
                refds, save_paths, update_failures, path, saw_subds)


def _save_after_update(refds, tosave, update_failures, path_arg, saw_subds):
    if path_arg and not saw_subds:
        lgr.warning(
            'path constraints did not match an installed subdataset: %s',
            path_arg)
    if refds in update_failures:
        lgr.warning("Not saving because top-level dataset %s "
                    "had an update failure in subdataset",
                    refds.path)
    else:
        save_paths = [p for p in tosave if p != refds.path]
        if not save_paths:
            return
        lgr.debug(
            'Subdatasets where updated state may need to be '
            'saved in the parent dataset: %s', save_paths)
        for r in refds.save(
                path=save_paths,
                recursive=False,
                message='[DATALAD] Save updated subdatasets',
                return_type='generator',
                result_renderer='disabled'):
            yield r


def _choose_update_target(repo, branch, remote, cfg_remote):
    """Select a target to update `repo` from.

    Note: This function is not concerned with _how_ the update is done (e.g.,
    merge, reset, ...).

    Parameters
    ----------
    repo : Repo instance
    branch : str
        The current branch.
    remote : str
        The remote which updates are coming from.
    cfg_remote : str
        The configured upstream remote.

    Returns
    -------
    str (the target) or None if a choice wasn't made.
    """
    target = None
    if cfg_remote and remote == cfg_remote:
        # Use the configured cfg_remote branch as the target.
        #
        # In this scenario, it's tempting to use FETCH_HEAD as the target. For
        # a merge, that would be the equivalent of 'git pull REMOTE'. But doing
        # so would be problematic when the GitRepo.fetch() call was passed
        # all_=True. Given we can't use FETCH_HEAD, it's tempting to use the
        # branch.*.merge value, but that assumes a value for remote.*.fetch.
        target = repo.call_git_oneline(
            ["rev-parse", "--symbolic-full-name", "--abbrev-ref=strict",
             f"{repo.get_corresponding_branch(branch) or ''}" "@{upstream}"],
            read_only=True)
    elif branch:
        remote_branch = "{}/{}".format(remote, branch)
        if repo.commit_exists(remote_branch):
            target = remote_branch
    return target


#  Update functions


def _choose_update_fn(repo, how, is_annex=False, adjusted=False):
    if adjusted and how != "merge":
        raise RuntimeError(
            "bug: Upstream checks should abort if adjusted is used "
            "with action other than 'merge'")
    elif how in ["merge", "ff-only"]:
        if adjusted and is_annex:
            # For adjusted repos, blindly sync.
            fn = _annex_sync
        elif is_annex:
            fn = _annex_plain_merge
        elif adjusted:
            raise RuntimeError(
                "bug: Upstream checks should make it impossible for "
                "adjusted=True, is_annex=False")
        else:
            fn = _plain_merge
    elif how == "reset":
        fn = _reset_hard
    elif how == "checkout":
        fn = _checkout
    else:
        raise ValueError(f"Unrecognized value for `how`: {how}")
    return fn


def _try_command(record, fn, *args, **kwargs):
    """Call `fn`, catching a `CommandError`.

    Parameters
    ----------
    record : dict
        A partial result record. It should at least have 'action' and 'message'
        fields. A 'status' value of 'ok' or 'error' will be added based on
        whether calling `fn` raises a `CommandError`.

    Returns
    -------
    A new record with a 'status' field.
    """
    try:
        fn(*args, **kwargs)
    except CommandError as exc:
        ce = CapturedException(exc)
        return dict(record, status="error", message=str(ce))
    else:
        return dict(record, status="ok")


def _plain_merge(repo, _, target, opts=None):
    yield _try_command(
        {"action": "merge", "message": ("Merged %s", target)},
        repo.merge,
        name=target, options=opts,
        expect_fail=True, expect_stderr=True)


def _annex_plain_merge(repo, _, target, opts=None):
    yield from _plain_merge(repo, _, target, opts=opts)
    # Note: Avoid repo.merge_annex() so we don't needlessly create synced/
    # branches.
    yield _try_command(
        {"action": "update.annex_merge", "message": "Merged annex branch"},
        repo.call_annex, ["merge"])


def _annex_sync(repo, remote, _target, opts=None):
    yield _try_command(
        {"action": "update.annex_sync", "message": "Ran git-annex-sync"},
        repo.call_annex,
        ['sync', '--no-push', '--pull', '--no-commit', '--no-content', remote])


def _reset_hard(repo, _, target, opts=None):
    if repo.dirty:
        yield {"action": "update.reset",
               "status": "error",
               "message": "Refusing to reset dirty working tree"}
    else:
        yield _try_command(
            {"action": "update.reset", "message": ("Reset to %s", target)},
            repo.call_git,
            ["reset", "--hard", target])


def _checkout(repo, _, target, opts=None):
    yield _try_command(
        {"action": "update.checkout", "message": ("Checkout %s", target)},
        repo.call_git,
        ["checkout", target])


def _reobtain(ds, update_fn):
    def wrapped(*args, **kwargs):
        repo = ds.repo
        repo_pathobj = repo.pathobj

        lgr.info("Applying updates to %s", ds)
        # get all annexed files that have data present
        lgr.info('Recording file content availability '
                 'to re-obtain updated files later on')
        ainfo = repo.get_content_annexinfo(
            init=None, eval_availability=True)
        # Recode paths for ds.get() call.
        present_files = [str(ds.pathobj / f.relative_to(repo_pathobj))
                         for f, st in ainfo.items() if st["has_content"]]

        yield from update_fn(*args, **kwargs)

        present_files = [p for p in present_files if lexists(p)]
        if present_files:
            lgr.info('Ensuring content availability for %i '
                     'previously available files',
                     len(present_files))
            yield from ds.get(present_files, recursive=False,
                              return_type='generator')
    return wrapped
