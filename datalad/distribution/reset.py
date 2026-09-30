# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for resetting a dataset to a revision."""

__docformat__ = 'restructuredtext'

import logging

from datalad.consts import ADJUSTED_BRANCH_EXPR
from datalad.distribution.utils import (
    _try_command,
    corresponding_hexsha,
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
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import CommandError
from datalad.support.param import Parameter

from .dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)

lgr = logging.getLogger('datalad.distribution.reset')


def _get_adjust_mode(branch_name):
    """Extract the adjustment mode from an adjusted branch name.

    E.g., 'adjusted/master(unlocked)' -> '--unlock'
    """
    match = ADJUSTED_BRANCH_EXPR.match(branch_name or '')
    if not match:
        # Default to unlocked mode as it is the most common adjustment,
        # especially on crippled filesystems where unlocked behavior is expected.
        return '--unlock'
    mode = match.group('mode')
    mode_to_option = {
        'unlocked': '--unlock',
        'locked': '--lock',
        'fix': '--fix',
        'fixed': '--fix',
        'hidemissing': '--hide-missing',
    }
    return mode_to_option.get(mode, '--unlock')


def _annex_reset_target(repo, _remote, target, opts=None):
    """Hard-reset an adjusted branch to TARGET (pure: always discards).

    Dispatches on whether TARGET moves history:

    - it does not (e.g. plain ``HEAD``): reset the adjusted *view* only -- the
      corresponding branch and ``synced/`` are left untouched
      (`_reset_adjusted_view`).
    - it does (a SHA, ``HEAD~N``, a sibling ref): reset the *corresponding*
      branch, reconcile git-annex's ``synced/<branch>`` ref, and regenerate the
      adjusted view (`_reset_corresponding_branch`).
    """
    strategy = (_reset_adjusted_view if _is_current_head(repo, target)
                else _reset_corresponding_branch)
    yield _try_command(
        {"action": "update.reset", "message": ("Reset to %s", target)},
        strategy, repo, target)


def _is_current_head(repo, target):
    """Whether TARGET denotes the current real-history HEAD -- so resetting to
    it moves no real history and can take the cheap `_reset_adjusted_view` path.

    Compared *corr-aware*: on an adjusted branch the literal HEAD is the
    adjusting commit, one above the real-history tip (the corresponding-branch
    tip). A user typically means that real tip -- via plain ``HEAD``, the SHA
    read from ``git log`` (= corr-tip), or a sibling ref already at it -- and
    all of those should reset the view in place. The literal-HEAD check also
    accepts the adjusting commit's own SHA (the top of ``git log`` on the
    adjusted branch), so pasting it does not fall through to the
    corresponding-branch reset (which would stamp it onto real history).
    Relative refs (``HEAD~N`` -> a real move) and a diverged sibling resolve
    off the tip, so they return False.
    """
    try:
        # literal adjusted HEAD (covers `target` == the adjusting-commit SHA)
        if repo.get_hexsha(target) == repo.get_hexsha("HEAD"):
            return True
        # corr-aware: does TARGET resolve to the corresponding-branch tip?
        return corresponding_hexsha(repo, target) == corresponding_hexsha(repo)
    except ValueError:
        return False


def _reset_adjusted_view(repo, target):
    """Hard-reset the adjusted view in place -- TARGET moves no real history.

    Resets to the adjusted HEAD (the adjusting commit), NOT to ``target``:
    ``target`` may be the corresponding-branch tip or a sibling SHA, and a bare
    ``git reset --hard <corr-tip>`` on the adjusted branch would strand the view
    on a non-adjusted commit. The view stays put; we only discard the working
    tree and re-materialise.

    A bare reset writes back pointer files but does not smudge content into
    the worktree, leaving unlocked files unmaterialised (content present, but
    the file holds the pointer). Re-checkout re-runs the smudge filter to
    materialise them -- crucially without a re-adjust, so it works even under
    the crippled-fs *simulation*, where `git annex fix`/`adjust` leave the
    pointer in place (or abort on retained content).
    """
    repo.call_git(["reset", "--hard", "HEAD"])
    repo.call_git(["checkout", "--", "."])


def _reset_corresponding_branch(repo, target):
    """Hard-reset the corresponding branch to TARGET, reconcile ``synced/`` and
    regenerate the adjusted view -- TARGET moves history."""
    active_branch = repo.get_active_branch()
    corr_branch = repo.get_corresponding_branch(active_branch)
    adjust_mode = _get_adjust_mode(active_branch)
    synced_branch = "synced/{}".format(corr_branch)

    # Check out the corresponding branch, force-discarding any dirty tree
    # (git-parity for ``datalad reset``; a no-op for ``update``, which refuses a
    # dirty tree before reaching here).
    repo.call_git(["checkout", "--force", corr_branch])
    try:
        repo.call_git(["reset", "--hard", target])
        # Reconcile synced/<corr> so a discarded commit cannot be resurrected by
        # the next sync/save (gh-7772): it records the last-synced state, and
        # left at the old tip the next sync would merge it back in.
        if synced_branch in repo.get_branches():
            repo.call_git(["branch", "-f", synced_branch, corr_branch])
        # regenerate the adjusted view on top of the reset corresponding branch
        repo.call_annex(["adjust", adjust_mode, "--force"])
    except Exception:
        # never strand the repo on the corresponding branch: restore the
        # adjusted view (best effort -- don't let a rescue failure mask the
        # original error)
        try:
            repo.call_annex(["adjust", adjust_mode, "--force"])
        except Exception:
            lgr.debug("Failed to restore adjusted branch %s after failed reset",
                      active_branch, exc_info=True)
        raise


def _reset_hard(repo, _, target, opts=None):
    """Pure hard-reset helper (see `_annex_reset_target` for the dirty-tree
    contract).  Called by ``update --how=reset``; pure so ``datalad reset`` can
    reuse it."""
    yield _try_command(
        {"action": "update.reset", "message": ("Reset to %s", target)},
        repo.call_git,
        ["reset", "--hard", target])


def _is_history_coordinate(repo, target):
    """Whether TARGET is a parent-history coordinate.

    A raw commit SHA or a relative ref (``HEAD~N``, ``...^``) is a coordinate in
    the parent's history with no per-subdataset meaning; a symbolic ref
    (branch / tag / remote-tracking ref) resolves locally in every dataset.
    Plain ``HEAD`` (no offset) is exempt.
    """
    if target in (None, "HEAD"):
        return False
    if "~" in target or "^" in target:
        return True
    # "SHA-like" := resolves to a commit but has no symbolic-full-name. A
    # branch/tag/remote-tracking ref has one; a raw SHA does not. Robust against
    # a branch literally named like a hex string.
    try:
        sym = repo.call_git(
            ["rev-parse", "--symbolic-full-name", target],
            read_only=True).strip()
    except CommandError:
        # Not resolvable as a ref expression -- not this guard's concern; the
        # engine reports the error per dataset.
        return False
    return not sym


def _reset_ds(ds, target):
    """Reset a single dataset to TARGET, dispatching on branch type.

    Yields the raw engine records (with ``status``/``message``). The shared
    engine is pure -- it always discards like ``git reset --hard`` (discard
    tracked, keep untracked); reset never refuses a dirty tree.
    """
    repo = ds.repo
    adjusted = isinstance(repo, AnnexRepo) and repo.is_managed_branch()
    reset_fn = _annex_reset_target if adjusted else _reset_hard
    yield from reset_fn(repo, None, target)


@build_doc
class Reset(Interface):
    """Reset a dataset to a target revision, discarding local divergence.

    Like ``git reset --hard``, but correct on git-annex *adjusted* branches (the
    default on Windows / crippled filesystems).  A plain ``git reset`` there
    operates on the disposable adjusted *view* rather than the corresponding
    branch, so the real history is left untouched and the discarded commits can
    be resurrected by the next `git annex sync`. This command instead resets the
    corresponding branch, reconciles git-annex's ``synced/<branch>`` ref, and
    regenerates the adjusted view.

    On a normal branch this runs ``git reset --hard <target>``.

    A dirty working tree is handled like ``git reset --hard``: tracked
    modifications are discarded, untracked files are kept (this is not
    ``git clean``).

    Annexed content is not deleted: ``git reset`` never touches the annex object
    store, so content stays recoverable until ``git annex unused``/gc.

    With ``--recursive``, every dataset in the hierarchy is reset.  By default
    each dataset resets to ``TARGET`` resolved in its own repository (a local
    operation).  With ``--follow=parentds`` the superdataset is reset to
    ``TARGET`` and each subdataset is reset to the revision the (reset)
    superdataset records for it, reconciling the hierarchy to the super's pins.
    """

    _examples_ = [
        dict(text="Reset the current branch to its HEAD, discarding "
                  "modifications of tracked files",
             code_py="reset()",
             code_cmd="datalad reset"),
        dict(text="Reset the current branch to a sibling's state, discarding "
                  "local commits",
             code_py="reset(target='sibling/branch')",
             code_cmd="datalad reset <sibling/branch>"),
        dict(text="Reset the current branch to a specific commit",
             code_py="reset(target='commit')",
             code_cmd="datalad reset <commit>"),
        dict(text="Reset a whole hierarchy to the revisions the superdataset "
                  "records",
             code_py="reset(recursive=True, follow='parentds')",
             code_cmd="datalad reset -r --follow parentds"),
    ]

    _params_ = dict(
        target=Parameter(
            args=("target",),
            metavar="COMMIT",
            nargs="?",
            doc="""revision to reset to: a commit-ish such as a branch, tag,
            SHA, or a remote-tracking ref like 'origin/main'. Defaults to HEAD.
            On an adjusted branch the reset is applied to the corresponding
            branch. A relative ref such as 'HEAD~1' discards exactly that many
            real commits (also on adjusted branches), but is only supported
            without recursion (or with [CMD: --follow parentds CMD][PY:
            follow='parentds' PY]).""",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to reset. If no dataset is given, an
            attempt is made to identify it based on the current working
            directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        follow=Parameter(
            args=("--follow",),
            constraints=EnsureChoice("parentds") | EnsureNone(),
            doc="""how to interpret TARGET for subdatasets (only meaningful with
            [CMD: --recursive CMD][PY: recursive=True PY]). By default every
            dataset resets to TARGET resolved in its own repository. With
            'parentds' the superdataset is reset to TARGET and each subdataset
            is reset to the revision the (reset) superdataset records for it."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='reset')
    @eval_results
    def __call__(
            target=None,
            *,
            dataset=None,
            follow=None,
            recursive=False,
            recursion_limit=None,
    ):
        # The classic Interface only enforces constraints via the command line;
        # validate explicitly so the Python API rejects bad values too.
        if follow not in (None, "parentds"):
            raise ValueError(
                "follow={!r} is not valid; only 'parentds' is supported "
                "(reset is a local operation -- there is no 'sibling')".format(
                    follow))

        refds = require_dataset(dataset, check_installed=True, purpose='reset')
        res = dict(action="reset", refds=refds.path, logger=lgr)
        target = target or "HEAD"

        def emit(ds, rec):
            return get_status_dict(
                ds=ds, status=rec.get("status"),
                message=rec.get("message"), **res)

        # NOTE/open-question: the shared `_try_command` contract stringifies a
        # CommandError into `message` and does not set `exception`, so error
        # records read as a nested "CommandError(CommandError: ...)". Worth
        # upgrading that shared contract (benefits `update` too) rather than
        # papering over it here.

        if not recursive:
            for rec in _reset_ds(refds, target):
                yield emit(refds, rec)
            return

        # --- recursive ---
        # A parent-history coordinate (raw SHA or relative ref) has no
        # per-subdataset meaning under the default each-dataset-resolves-locally
        # mode; require an explicit --follow=parentds.
        if follow != "parentds" and _is_history_coordinate(refds.repo, target):
            yield get_status_dict(
                ds=refds, status="impossible",
                message=(
                    "%r is a parent-history coordinate with no per-subdataset "
                    "meaning; pass --follow=parentds to reset subdatasets to "
                    "the revisions the superdataset records", target),
                **res)
            return

        if follow == "parentds":
            # super first, then descend resetting each subds to the revision
            # its (reset) parent records.
            yield from Reset._reset_tree(
                refds, target, recursion_limit, emit)
        else:
            # default or `--follow=None`: every dataset resets to TARGET resolved in its own repo.
            datasets = [refds] + refds.subdatasets(
                recursive=True, recursion_limit=recursion_limit,
                state='present', result_xfm='datasets',
                result_renderer='disabled')
            for ds in datasets:
                for rec in _reset_ds(ds, target):
                    yield emit(ds, rec)

    @staticmethod
    def _reset_tree(ds, target, recursion_limit, emit):
        """Recursively reset DS to TARGET, then each subdataset to the revision
        DS records for it (--follow=parentds). Parent before children."""
        for rec in _reset_ds(ds, target):
            yield emit(ds, rec)
        if recursion_limit is not None and recursion_limit <= 0:
            return
        sub_limit = (recursion_limit - 1) \
            if isinstance(recursion_limit, int) else None
        for sub in ds.subdatasets(recursive=False, state='present',
                                  result_renderer='disabled'):
            yield from Reset._reset_tree(
                Dataset(sub['path']), sub['gitshasum'], sub_limit, emit)
