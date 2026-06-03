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
from datalad.distribution.utils import _try_command

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
    """Reset an adjusted branch to a specific target revision.

    Performs a hard reset on the corresponding branch, reconciles git-annex's
    ``synced/<branch>`` ref, and re-adjusts the branch to maintain the adjusted
    state.

    This is a *pure* reset helper: it always discards (like ``git reset
    --hard``) and does not inspect the working tree, so ``datalad
    reset`` can reuse it.  Its only caller here, ``update --how=reset``,
    enforces its stricter refuse-if-dirty contract before delegating.
    """
    active_branch = repo.get_active_branch()
    corr_branch = repo.get_corresponding_branch(active_branch)
    adjust_mode = _get_adjust_mode(active_branch)

    def do_reset():
        # Checkout the corresponding branch, force-discarding any dirty tree
        # (git-parity for `datalad reset`; a no-op for `update`, which refuses
        # a dirty tree before reaching here).
        repo.call_git(['checkout', '--force', corr_branch])
        try:
            # Reset to target
            repo.call_git(['reset', '--hard', target])
            # Also reset synced/<branch> so git-annex-sync won't
            # resurrect the discarded commits (#7772).
            synced_branch = 'synced/{}'.format(corr_branch)
            if synced_branch in repo.get_branches():
                repo.call_git(['branch', '-f', synced_branch, corr_branch])
            # Re-adjust with --force to overwrite existing adjusted branch
            repo.call_annex(['adjust', adjust_mode, '--force'])
        except Exception:
            # Try to restore the adjusted branch so the repo isn't stranded
            # on the corresponding branch
            try:
                repo.call_annex(['adjust', adjust_mode, '--force'])
            except Exception:
                lgr.debug(
                    "Failed to restore adjusted branch %s after "
                    "failed reset", active_branch, exc_info=True)
            raise

    yield _try_command(
        {"action": "update.reset", "message": ("Reset to %s", target)},
        do_reset)


def _reset_hard(repo, _, target, opts=None):
    """Pure hard-reset helper (see `_annex_reset_target` for the dirty-tree
    contract).  Called by ``update --how=reset``; pure so ``datalad reset`` can
    reuse it."""
    yield _try_command(
        {"action": "update.reset", "message": ("Reset to %s", target)},
        repo.call_git,
        ["reset", "--hard", target])
