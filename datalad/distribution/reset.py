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
    """Hard-reset an adjusted branch to TARGET.

    Always discards a dirty tree; ``update`` refuses one before calling.
    A TARGET at the current HEAD only resets the view; any other TARGET resets
    the corresponding branch and regenerates the view.
    """
    strategy = (_reset_adjusted_view if _is_current_head(repo, target)
                else _reset_corresponding_branch)
    yield _try_command(
        {"action": "update.reset", "message": ("Reset to %s", target)},
        strategy, repo, target)


def _is_current_head(repo, target):
    """Whether TARGET is the adjusted HEAD or the corresponding-branch tip."""
    try:
        if repo.get_hexsha(target) == repo.get_hexsha("HEAD"):
            return True
        return corresponding_hexsha(repo, target) == corresponding_hexsha(repo)
    except ValueError:
        return False


def _reset_adjusted_view(repo, target):
    # Reset to the view's own HEAD, not TARGET: a corresponding-branch SHA would
    # strand the view. The checkout re-materialises unlocked files.
    repo.call_git(["reset", "--hard", "HEAD"])
    repo.call_git(["checkout", "--", "."])


def _reset_corresponding_branch(repo, target):
    active_branch = repo.get_active_branch()
    corr_branch = repo.get_corresponding_branch(active_branch)
    adjust_mode = _get_adjust_mode(active_branch)

    # Checkout the corresponding branch, discarding a dirty tree
    repo.call_git(["checkout", "--force", corr_branch])
    try:
        repo.call_git(["reset", "--hard", target])
        repo.call_annex(["adjust", adjust_mode, "--force"])
    except Exception:
        # Try to restore the adjusted branch so the repo isn't stranded
        # on the corresponding branch
        try:
            repo.call_annex(["adjust", adjust_mode, "--force"])
        except Exception:
            lgr.debug("Failed to restore adjusted branch %s after failed reset",
                      active_branch, exc_info=True)
        raise


def _reset_hard(repo, _, target, opts=None):
    yield _try_command(
        {"action": "update.reset", "message": ("Reset to %s", target)},
        repo.call_git,
        ["reset", "--hard", target])


def _is_history_coordinate(repo, target):
    """Whether TARGET is a raw SHA or a relative ref (``HEAD~N``), i.e. has no
    meaning in a subdataset. Plain ``HEAD`` and symbolic refs do."""
    if target in (None, "HEAD"):
        return False
    try:
        # a branch/tag/remote ref has a symbolic full name; a SHA or HEAD~N not
        sym = repo.call_git(
            ["rev-parse", "--symbolic-full-name", target],
            read_only=True).strip()
    except CommandError:
        # unresolvable: reported by the reset itself
        return False
    return not sym


def _reset_ds(ds, target):
    repo = ds.repo
    adjusted = isinstance(repo, AnnexRepo) and repo.is_managed_branch()
    reset_fn = _annex_reset_target if adjusted else _reset_hard
    yield from reset_fn(repo, None, target)


@build_doc
class Reset(Interface):
    """Reset a dataset to a target revision, discarding local divergence.

    Like ``git reset --hard <target>``, but also correct on git-annex
    *adjusted* branches (the default on Windows / crippled filesystems), where
    a plain ``git reset`` only resets the adjusted view and leaves the
    corresponding branch untouched. This command resets the corresponding
    branch and regenerates the adjusted view.

    Tracked modifications are discarded, untracked files are kept. Annexed
    content is not deleted.

    With ``--recursive``, each dataset resets to ``TARGET`` resolved in its own
    repository. With ``--follow=parentds``, the superdataset resets to
    ``TARGET`` and each subdataset to the revision the superdataset records.
    """

    _examples_ = [
        dict(text="Discard modifications of tracked files",
             code_py="reset()",
             code_cmd="datalad reset"),
        dict(text="Reset to a sibling's state, discarding local commits",
             code_py="reset(target='sibling/branch')",
             code_cmd="datalad reset <sibling/branch>"),
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
            doc="""revision to reset to (branch, tag, SHA, remote-tracking ref,
            or relative ref like 'HEAD~1'). Defaults to HEAD. With
            [CMD: --recursive CMD][PY: recursive=True PY], a SHA or relative
            ref requires [CMD: --follow parentds CMD][PY: follow='parentds'
            PY].""",
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
            doc="""with 'parentds', reset each subdataset to the revision its
            (reset) superdataset records, instead of to TARGET."""),
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
        # constraints are only enforced on the command line
        if follow not in (None, "parentds"):
            raise ValueError(
                "follow={!r} is not valid; only 'parentds' is supported".format(
                    follow))

        refds = require_dataset(dataset, check_installed=True, purpose='reset')
        res = dict(action="reset", refds=refds.path, logger=lgr)
        target = target or "HEAD"

        def emit(ds, rec):
            return get_status_dict(
                ds=ds, status=rec.get("status"),
                message=rec.get("message"), **res)

        if not recursive:
            for rec in _reset_ds(refds, target):
                yield emit(refds, rec)
            return

        if follow != "parentds" and _is_history_coordinate(refds.repo, target):
            yield get_status_dict(
                ds=refds, status="impossible",
                message=(
                    "%r has no meaning in subdatasets; pass --follow=parentds "
                    "to reset them to the revisions the superdataset records",
                    target),
                **res)
            return

        if follow == "parentds":
            yield from Reset._reset_tree(
                refds, target, recursion_limit, emit)
        else:
            datasets = [refds] + refds.subdatasets(
                recursive=True, recursion_limit=recursion_limit,
                state='present', result_xfm='datasets',
                result_renderer='disabled')
            for ds in datasets:
                for rec in _reset_ds(ds, target):
                    yield emit(ds, rec)

    @staticmethod
    def _reset_tree(ds, target, recursion_limit, emit):
        """Reset DS to TARGET, then each subdataset to the revision DS records
        for it (parent first)."""
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
