# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for updating a dataset

"""

__docformat__ = 'restructuredtext'


import logging
from os.path import lexists, join as opj
import itertools

from datalad.dochelpers import exc_str
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import (
    get_status_dict,
    YieldDatasets
)
from datalad.support.constraints import (
    EnsureBool,
    EnsureChoice,
    EnsureStr,
    EnsureNone,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CommandError
from datalad.support.param import Parameter
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.distribution.dataset import require_dataset

from .dataset import (
    EnsureDataset,
    datasetmethod,
)

lgr = logging.getLogger('datalad.distribution.update')


class YieldDatasetAndRevision(YieldDatasets):
    """Like YieldDatasets, but also provide "revision" value, if any.
    """
    def __call__(self, res):
        ds = super(YieldDatasetAndRevision, self).__call__(res)
        return ds, res.get("revision")


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
             code_py="update(sibling='siblingname', merge=True)",
             code_cmd="datalad update --merge -s <siblingname>"),
        dict(text="Update from the sibling 'origin', traversing into "
                  "subdatasets. For subdatasets, merge the revision "
                  "registered in the parent dataset into the current branch",
             code_py="update(sibling='origin', merge=True, "
                     "follow='parentds', recursive=True)",
             code_cmd="datalad update -s origin --merge "
                      "--follow=parentds -r"),
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
            doc="""name of the sibling to update from. If no sibling
            is given, updates from all siblings are obtained.""",
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
            doc="""merge obtained changes from the sibling. If a sibling is not
            explicitly given and there is only a single known sibling, that
            sibling is used. Otherwise, an unspecified sibling defaults to the
            configured remote for the current branch. By default, changes are
            fetched from the sibling but not merged into the current branch.
            With [CMD: --merge or --merge=any CMD][PY: merge=True or
            merge="any" PY], the changes will be merged into the current
            branch. A value of 'ff-only' restricts the allowed merges to
            fast-forwards."""),
        follow=Parameter(
            args=("--follow",),
            constraints=EnsureChoice("sibling", "parentds"),
            doc="""source of updates for subdatasets. For 'sibling', the update
            will be done by merging in a branch from the (specified or
            inferred) sibling. The branch brought in will either be the current
            branch's configured branch, if it points to a branch that belongs
            to the sibling, or a sibling branch with a name that matches the
            current branch. For 'parentds', the revision registered in the
            parent dataset of the subdataset is merged in. Note that the
            current dataset is always updated according to 'sibling'. This
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
            sibling=None,
            merge=False,
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

        refds = require_dataset(dataset, check_installed=True, purpose='updating')

        save_paths = []
        merge_failures = set()
        saw_subds = False
        for ds, revision in itertools.chain([(refds, None)], refds.subdatasets(
                path=path,
                fulfilled=True,
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
            if not sibling_ and len(remotes) > 1 and merge:
                lgr.debug("Found multiple siblings:\n%s" % remotes)
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
                # required to not trip over submodules that
                # were removed in the origin clone
                recurse_submodules="no",
                prune=True)  # prune to not accumulate a mess over time
            repo.fetch(**fetch_kwargs)
            # NOTE reevaluate ds.repo again, as it might have be converted from
            # a GitRepo to an AnnexRepo
            repo = ds.repo

            follow_parent = revision and follow == "parentds"
            if follow_parent and not repo.commit_exists(revision):
                if sibling_:
                    try:
                        lgr.debug("Fetching revision %s directly for %s",
                                  revision, repo)
                        repo.fetch(remote=sibling_, refspec=revision,
                                   git_options=["--recurse-submodules=no"])
                    except CommandError as exc:
                        yield dict(
                            res,
                            status="impossible",
                            message=(
                                "Attempt to fetch %s from %s failed: %s",
                                revision, sibling_, exc_str(exc)))
                        continue
                else:
                    yield dict(res,
                               status="impossible",
                               message=("Need to fetch %s directly "
                                        "but single sibling not resolved",
                                        revision))
                    continue

            saw_merge_failure = False
            if merge:
                if follow_parent:
                    merge_target = revision
                else:
                    merge_target = _choose_merge_target(
                        repo, curr_branch,
                        sibling_, tracking_remote)

                merge_fn = _choose_merge_fn(
                    repo,
                    is_annex=is_annex,
                    adjusted=is_annex and repo.is_managed_branch(curr_branch))

                merge_opts = None
                if merge_fn is _annex_sync:
                    if follow_parent:
                        yield dict(
                            res, status="impossible",
                            message=("follow='parentds' is incompatible "
                                     "with adjusted branches"))
                        continue
                elif merge_target is None:
                    yield dict(res,
                               status="impossible",
                               message="Could not determine merge target")
                    continue
                elif merge == "ff-only":
                    merge_opts = ["--ff-only"]

                if is_annex and reobtain_data:
                    merge_fn = _reobtain(ds, merge_fn)

                for mres in merge_fn(repo, sibling_, merge_target,
                                     merge_opts=merge_opts):
                    if mres["action"] == "merge" and mres["status"] != "ok":
                        saw_merge_failure = True
                    yield dict(res, **mres)

            if saw_merge_failure:
                merge_failures.add(ds)
                res['status'] = 'error'
                res['message'] = ("Merge of %s failed", merge_target)
            else:
                res['status'] = 'ok'
                save_paths.append(ds.path)
            yield res
        # we need to save updated states only if merge was requested -- otherwise
        # it was a pure fetch
        if merge and recursive:
            if path and not saw_subds:
                lgr.warning(
                    'path constraints did not match an installed subdataset: %s',
                    path)
            if refds in merge_failures:
                lgr.warning("Not saving because top-level dataset %s "
                            "had a merge failure",
                            refds.path)
            else:
                save_paths = [p for p in save_paths if p != refds.path]
                if not save_paths:
                    return
                lgr.debug(
                    'Subdatasets where updated state may need to be '
                    'saved in the parent dataset: %s', save_paths)
                for r in refds.save(
                        path=save_paths,
                        recursive=False,
                        message='[DATALAD] Save updated subdatasets'):
                    yield r


def _choose_merge_target(repo, branch, remote, cfg_remote):
    """Select a merge target for the update to `repo`.

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
    str (the merge target) or None if a choice wasn't made.
    """
    merge_target = None
    if cfg_remote and remote == cfg_remote:
        # Use the configured cfg_remote branch as the merge target.
        #
        # In this scenario, it's tempting to use FETCH_HEAD as the merge
        # target. That would be the equivalent of 'git pull REMOTE'. But doing
        # so would be problematic when the GitRepo.fetch() call was passed
        # all_=True. Given we can't use FETCH_HEAD, it's tempting to use the
        # branch.*.merge value, but that assumes a value for remote.*.fetch.
        merge_target = repo.call_git_oneline(
            ["rev-parse", "--symbolic-full-name", "--abbrev-ref=strict",
             "@{upstream}"])
    elif branch:
        remote_branch = "{}/{}".format(remote, branch)
        if repo.commit_exists(remote_branch):
            merge_target = remote_branch
    return merge_target


#  Merge functions


def _choose_merge_fn(repo, is_annex=False, adjusted=False):
    if adjusted and is_annex:
        # For adjusted repos, blindly sync.
        merge_fn = _annex_sync
    elif is_annex:
        merge_fn = _annex_plain_merge
    elif adjusted:
        raise RuntimeError(
            "bug: Upstream checks should make it impossible for "
            "adjusted=True, is_annex=False")
    else:
        merge_fn = _plain_merge
    return merge_fn


def _plain_merge(repo, _, target, merge_opts=None):
    try:
        repo.merge(name=target, options=merge_opts,
                   expect_fail=True, expect_stderr=True)
    except CommandError as exc:
        yield {"action": "merge", "status": "error",
               "message": exc_str(exc)}
    else:
        yield {"action": "merge", "status": "ok",
               "message": ("Merged %s", target)}


def _annex_plain_merge(repo, _, target, merge_opts=None):
    yield from _plain_merge(repo, _, target, merge_opts=merge_opts)
    # Note: Avoid repo.merge_annex() so we don't needlessly create synced/
    # branches.
    repo.call_git(["annex", "merge"])


def _annex_sync(repo, remote, _target, merge_opts=None):
    repo.sync(remotes=remote, push=False, pull=True, commit=False)
    return []


def _reobtain(ds, merge_fn):
    def wrapped(*args, **kwargs):
        repo = ds.repo

        lgr.info("Applying updates to %s", ds)
        # get all annexed files that have data present
        lgr.info('Recording file content availability '
                 'to re-obtain updated files later on')
        ds_path = ds.path
        present_files = [
            opj(ds_path, p)
            for p in repo.get_annexed_files(with_content_only=True)]

        yield from merge_fn(*args, **kwargs)

        present_files = [p for p in present_files if lexists(p)]
        if present_files:
            lgr.info('Ensuring content availability for %i '
                     'previously available files',
                     len(present_files))
            yield from ds.get(present_files, recursive=False,
                              return_type='generator')
    return wrapped
