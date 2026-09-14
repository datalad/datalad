# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
"""Tests for `datalad reset` (adjusted-branch-safe hard reset).

Behavior is parametrized over the ``fs_mode`` fixture, which runs every test
across the three natural (filesystem, branch) modes -- ``normal``, ``adjusted``
and ``crippled`` (see the fixture's docstring). The ``crippled`` mode is
*simulated* on a normal filesystem, so a single Linux run exercises the
adjusted-branch-on-crippled-fs code path rather than leaving it to Windows CI
alone. The only per-leg skip is the genuinely impossible combination -- a normal
branch on a crippled filesystem (see `_skip_normal_leg_on_crippled`).

Histories are read with ``corresponding_hexsha`` (corr-aware) and compared
relationally, never against a hardcoded value.

The command's design and intended behavior are documented in
``docs/source/design/reset.rst``.
"""

import os
from pathlib import Path

import pytest

from datalad.api import install
from datalad.distribution.dataset import Dataset
from datalad.distribution.reset import _is_current_head
from datalad.distribution.utils import corresponding_hexsha
from datalad.tests.utils_pytest import (
    assert_false,
    assert_in_results,
    assert_result_count,
    eq_,
    has_symlink_capability,
    maybe_adjust_repo,
    maybe_unadjust_repo,
    neq_,
    ok_,
    skip_if_adjusted_branch,
    slow,
    with_tempfile,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers: adjusted branch
# ---------------------------------------------------------------------------
FS_MODES = ("normal", "adjusted", "crippled")


@pytest.fixture(params=FS_MODES)
def fs_mode(request, monkeypatch):
    """Parametrize a test over three (filesystem, branch) modes: ``normal``,
    ``adjusted`` and ``crippled``.

    This fixture's own job is deliberately small: it yields the mode name and,
    for the ``crippled`` mode, sets ``annex.crippledfilesystem=true`` in git's
    config environment. That must happen here -- before any ``create()`` /
    ``clone()`` -- because git-annex decides crippledness at init time; with it
    set, every repository the test creates comes up on an adjusted branch, as a
    real crippled filesystem (e.g. Windows) forces.

    The other two modes are realised *after* a repo exists, by the dataset
    helpers rather than by this fixture:

    - ``adjusted`` -- `_adjust_for_mode` runs ``git annex adjust`` on the new
      repo, simulating an adjusted branch on a normal filesystem.
    - ``normal``   -- nothing is adjusted; where a normal branch cannot exist (a
      crippled filesystem) `_skip_normal_leg_on_crippled` skips the leg.
    """
    mode = request.param
    if mode == "crippled":
        # git reads GIT_CONFIG_KEY_<n>/VALUE_<n> on every invocation; compose
        # with any pre-existing GIT_CONFIG_* entries rather than clobbering them.
        n = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
        monkeypatch.setenv("GIT_CONFIG_KEY_{}".format(n), "annex.crippledfilesystem")
        monkeypatch.setenv("GIT_CONFIG_VALUE_{}".format(n), "true")
        monkeypatch.setenv("GIT_CONFIG_COUNT", str(n + 1))
    return mode


def _xfail_simulated_crippled(request, repo):
    """xfail a test *only* when it runs against a SIMULATED crippled filesystem.

    We fake a crippled fs by setting ``annex.crippledfilesystem=true`` (see the
    `fs_mode` fixture). That is faithful enough to force adjusted branches, but
    NOT to reproduce a history-moving reset whose target retains annexed
    content: the simulation runs on a symlink-*capable* filesystem, so the
    corresponding branch's locked symlink lands in the worktree as a phantom
    modification that a genuinely symlink-less filesystem never produces, and
    `git annex adjust`'s checkout then aborts
    (see `test_reset_keeps_annexed_content_in_target`).

    This is an artefact of the simulation, NOT a bug in `_annex_reset_target`:
    on a genuinely symlink-less filesystem these legs PASS (verified on real
    Windows). Marking xfail(strict=False) keeps the leg visible on Linux without
    contorting production code to satisfy the simulation.

    Why no setting can make the simulation faithful: the sim-vs-real-Windows
    divergence traces, in git-annex's source, to a *compile-time*
    ``#ifdef mingw32_HOST_OS`` on its inode-sentinel / restage path
    (``Annex/InodeSentinal.hs`` ``getTSDelta``), not to any runtime config or
    filesystem probe. A Linux-built git-annex cannot run the Windows code paths,
    so no git/git-annex setting bridges the gap (and even a genuinely
    symlink-less filesystem -- e.g. a vfat loopback mount -- would likely not
    bridge it, since it would still be the Linux binary). Real Windows is the
    only faithful check, which is exactly what this xfail defers to.
    """
    if repo.is_crippled_fs() and has_symlink_capability():
        request.applymarker(pytest.mark.xfail(
            strict=False,
            reason="crippled-FS simulation on a symlink-capable filesystem "
                   "cannot reproduce reset-to-retained-annex; only real Windows "
                   "CI can validate this scenario"))


def _skip_normal_leg_on_crippled(repo, mode):
    """Honestly skip the ``normal`` leg where a normal branch cannot exist.

    A crippled filesystem (e.g. real Windows) forces every repo onto an adjusted
    branch, so ``create()``/``clone()`` come up managed no matter what -- there
    is no normal-branch behaviour to test, and running the leg anyway would just
    re-exercise the adjusted path under a misleading ``normal`` label. On a
    normal filesystem this never triggers (the repo is genuinely unmanaged).

    Called from the three constructors that build the *dataset-under-test*
    (`_ds`, `_ds_with_subds`, `_clone`) -- never from the source helpers
    (`_src_with_base_commit`, `_src_with_one_subds`), whose branch state is
    irrelevant (it is only ever read corr-aware).

    Unlike ``@skip_if_adjusted_branch``, which skips an *entire* test wherever
    the filesystem forces adjusted branches -- hiding that behaviour from
    crippled-FS CI -- this skips only the one impossible leg and keeps the
    ``adjusted``/``crippled`` legs running.
    """
    if mode == "normal" and repo.is_managed_branch():
        pytest.skip("normal branch N/A on a crippled filesystem")


def _adjust_for_mode(ds, mode):
    """Put DS on an adjusted branch when the mode needs a *simulated* one --
    including any subdatasets, children before the parent, to dodge the
    git-annex submodule/adjust crash fixed in 7.20191024. In ``crippled`` mode
    the filesystem already forced it; in ``normal`` mode the repo stays on its
    normal branch.
    """
    if mode != "adjusted":
        return
    for sub in ds.subdatasets(recursive=True, result_xfm="datasets",
                              result_renderer="disabled"):
        maybe_adjust_repo(sub.repo)
    maybe_adjust_repo(ds.repo)


def _is_adjusted_mode(mode):
    """True for the modes whose repos live on an adjusted (managed) branch."""
    return mode in ("adjusted", "crippled")


def _corr(repo):
    """The underlying real branch name regardless of whether it is adjusted."""
    return repo.get_corresponding_branch() or repo.get_active_branch()


def _assert_adjusted(repo, fs_mode):
    """On an adjusted leg the repo must still be on its adjusted
    branch after a reset (the re-adjust did not strand it on the corresponding
    branch). A no-op on the normal leg.
    """
    if _is_adjusted_mode(fs_mode):
        ok_(repo.is_managed_branch())


def _assert_reset_ok(res, repo, fs_mode, target_sha):
    """The three universal invariants of a successful reset (see section B):
    the call is ok, the corresponding branch tip is at the target, and -- on an
    adjusted leg -- the repo is still adjusted (`_assert_adjusted`). Scenario-
    specific assertions (e.g. a discarded file is gone) stay inline in the test.
    """
    assert_in_results(res, action="reset", status="ok")
    eq_(corresponding_hexsha(repo), target_sha)
    _assert_adjusted(repo, fs_mode)


# ---------------------------------------------------------------------------
# Fixtures / helpers: dataset
# ---------------------------------------------------------------------------

# Construct dataset under control
def _ds(path, mode, name="ds"):
    """A single dataset in the given fs/branch mode."""
    ds = Dataset(path / name).create()
    _adjust_for_mode(ds, mode)
    _skip_normal_leg_on_crippled(ds.repo, mode)
    return ds


def _ds_with_subds(path, mode, name="ds"):
    """A dataset under control with one subdataset `sub`, created directly
    (no clone) -- the recursive analogue of `_ds`.

    Use this whenever a recursive test only needs a super+sub to operate on
    locally. Only tests that resolve a target against a *sibling* clone a source
    (`_src_with_subds` + `_clone(..., recursive=True)`), where the source IS the
    sibling.
    """
    ds = Dataset(path / name).create()
    ds_sub = ds.create("sub")
    ds.save()
    (ds.pathobj / "base.txt").write_text("BASE")
    (ds_sub.pathobj / "subbase.txt").write_text("BASE")
    ds.save(recursive=True)
    _adjust_for_mode(ds, mode)
    _skip_normal_leg_on_crippled(ds.repo, mode)
    return ds


def _clone(ds_src, path, mode, recursive=False, name="clone"):
    """Install a clone of DS_SRC (optionally recursive); the source becomes the
    clone's sibling. For tests that resolve a target against a sibling.
    """
    ds_clone = install(source=ds_src.path, path=path / name,
                       recursive=recursive, result_xfm="datasets")
    _adjust_for_mode(ds_clone, mode)
    _skip_normal_leg_on_crippled(ds_clone.repo, mode)
    return ds_clone


# Construct source dataset
def _src_with_base_commit(path):
    """A source dataset with one base commit, in whatever branch state the
    filesystem gives: a normal branch on a normal fs, an adjusted branch on a
    crippled one (Windows CI).

    Callers must read its history via `corresponding_hexsha`, never plain HEAD.
    """
    ds_src = Dataset(path / "source").create()
    (ds_src.pathobj / "base.txt").write_text("BASE")
    ds_src.save("")
    return ds_src


def _src_with_subds(path):
    """Source superdataset with one subdataset `sub`, saved recursively.

    For recursive tests that resolve a target against a *sibling* (the source
    becomes the clone's origin, via `_clone(..., recursive=True)`). Tests that
    only need a local super+sub should use `_ds_with_subds` instead.
    """
    ds_src = Dataset(path / "source").create()
    ds_sub = ds_src.create("sub")
    ds_src.save()

    (ds_src.pathobj / "base.txt").write_text("BASE")
    (ds_sub.pathobj / "subbase.txt").write_text("BASE")
    ds_src.save(recursive=True)
    return ds_src


# Get sibling and subdataset
def _sibling(repo):
    # harness-independent: use the repo's actual remote, not DEFAULT_REMOTE
    return repo.get_remotes()[0]


def _subds(ds):
    return ds.subdatasets(result_xfm="datasets", result_renderer="disabled")[0]


# ---------------------------------------------------------------------------
# A. Contract / guard (non-recursive)
# ---------------------------------------------------------------------------

@with_tempfile(mkdir=True)
def test_reset_unsupported_follow_rejected(path=None):
    """An unsupported `follow` value must yield a clean ValueError, not silently
    fall through. The `EnsureChoice` constraint only guards the CLI path; this
    exercises the Python API, where the hand-rolled check in __call__ is the
    only thing rejecting bad values.
    """
    path = Path(path)
    ds = Dataset(path / "ds").create()
    with pytest.raises(ValueError):
        ds.reset(follow="bogus", on_failure="ignore")


# ---------------------------------------------------------------------------
# B. Core hard-reset (non-recursive)
# ---------------------------------------------------------------------------

@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_to_explicit_commit(path=None, *, fs_mode):
    path = Path(path)
    ds = _ds(path, fs_mode)

    parent = corresponding_hexsha(ds.repo)
    (ds.pathobj / "discard.txt").write_text("DISCARD")
    ds.save()
    neq_(corresponding_hexsha(ds.repo), parent)

    res = ds.reset(target=parent)
    _assert_reset_ok(res, ds.repo, fs_mode, parent)
    assert_false((ds.pathobj / "discard.txt").exists())


@slow  # ~10s
# @skip_if_adjusted_branch  # need a normal source + a deliberately-adjusted clone
@with_tempfile(mkdir=True)
def test_is_current_head_routing(path=None, *, fs_mode):
    """Unit test for the strategy dispatch `_is_current_head`: True exactly when
    TARGET denotes the current real-history HEAD (reset takes the cheap
    `_reset_adjusted_view` path), False when real history moves (the
    corresponding-branch path). `_is_current_head` is only called on adjusted/crippled,
    and no-op otherwise.

    The comparison is corr-aware: on an adjusted branch the literal HEAD is the
    adjusting commit, one *above* the real-history tip (the corresponding-branch
    tip). Resetting to either the literal HEAD or the real-history HEAD should yield
    the same result.

    Reset-the-view-in-place cases: plain ``HEAD``, the corr-tip SHA (the
    "real HEAD" a user copies out of ``git log``), the adjusting-commit SHA (the
    top of ``git log``), and a sibling ref already at the corr-tip.

    Real-history moves: ``HEAD~1`` (drops a real commit), an older SHA, and a diverged
    sibling. (Unresolvable targets are rejected before this function, so they
    are not exercised here.)
    """
    if fs_mode == "normal":
        pytest.skip("branch needs to be adjusted")

    path = Path(path)
    ds_src = _src_with_base_commit(path)
    # on crippled FS, also source ds is forced into adjusted mode
    # unadjust so that the call targets the corresponding branch underneath
    maybe_unadjust_repo(ds_src.repo)

    ds = _clone(ds_src, path, fs_mode)

    corr_tip = corresponding_hexsha(ds.repo)          # real-history HEAD (base commit)
    view_tip = ds.repo.get_hexsha("HEAD")             # adjusting commit (top of git log)
    older = corresponding_hexsha(ds.repo, "HEAD~1")   # one real commit back (dataset creation)
    neq_(corr_tip, view_tip)  # the dispatch only bites because HEAD sits above corr-tip; does not apply to normal

    # no real move -> view reset
    ok_(_is_current_head(ds.repo, "HEAD"))
    ok_(_is_current_head(ds.repo, corr_tip))                # corr-tip SHA
    ok_(_is_current_head(ds.repo, view_tip))                # adjusting-commit SHA
    ok_(_is_current_head(ds.repo, f"{_sibling(ds.repo)}/{_corr(ds.repo)}"))  # sibling already at corr-tip

    # real move -> corresponding-branch reset
    assert_false(_is_current_head(ds.repo, "HEAD~1"))       # drops a real commit
    assert_false(_is_current_head(ds.repo, older))          # non-corr-tip SHA

    # diverged sibling: advance the source, fetch -> remote ref no longer at corr-tip
    (ds_src.pathobj / "advance_src.txt").write_text("ADVANCED")
    ds_src.save()
    ds.repo.fetch(remote=_sibling(ds.repo))
    assert_false(_is_current_head(ds.repo, f"{_sibling(ds.repo)}/{_corr(ds.repo)}"))


@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_annexed_content_recoverable(path=None, *, fs_mode):
    """git reset never touches .git/annex/objects -> content survives (parity)."""
    path = Path(path)
    ds = _ds(path, fs_mode)

    parent = corresponding_hexsha(ds.repo)
    (ds.pathobj / "data.bin").write_text("PRECIOUS")
    ds.save()
    # ensure file is annexed -> has key and content
    key = ds.repo.get_file_annexinfo("data.bin").get("key")
    ok_(key)  # fail loudly, not a silent skip
    ok_(ds.repo.file_has_content("data.bin"))

    res = ds.reset(target=parent)
    _assert_reset_ok(res, ds.repo, fs_mode, parent)
    assert_false((ds.pathobj / "data.bin").exists())  # removed file from worktree
    ok_(ds.repo.get_contentlocation(key))             # left content intact in annex store


@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_keeps_annexed_content_in_target(path=None, *, fs_mode, request):
    """The raison d'etre of `datalad reset` on an adjusted branch: a history-moving
    reset whose TARGET still RETAINS annexed content (the common case -- you
    reset to keep some history, not to wipe it). The corresponding branch
    *records* such a file as locked (a git mode-120000 symlink entry); a crippled
    fs cannot render a real symlink, so it materialises that locked entry as a
    stand-in regular file holding the object path, while the adjusted worktree
    carries a copy of the actual unlocked content. The re-adjust must bridge that
    locked-record / unlocked-worktree transition without choking.
    """
    path = Path(path)
    ds = _ds(path, fs_mode)
    _xfail_simulated_crippled(request, ds.repo)

    (ds.pathobj / "keep.bin").write_text("KEEP")
    ds.save()
    keep_sha = corresponding_hexsha(ds.repo)
    keep_key = ds.repo.get_file_annexinfo("keep.bin").get("key")
    ok_(keep_key)  # keep.bin is really annexed (else the test has no teeth)

    (ds.pathobj / "discard.bin").write_text("DISCARD")
    ds.save()
    neq_(corresponding_hexsha(ds.repo), keep_sha)

    res = ds.reset(target=keep_sha)
    _assert_reset_ok(res, ds.repo, fs_mode, keep_sha)
    assert_false((ds.pathobj / "discard.bin").exists())  # discarded file gone
    ok_(ds.repo.file_has_content("keep.bin"))            # retained file's content in the annex store...
    eq_((ds.pathobj / "keep.bin").read_text(), "KEEP")   # ...and materialised in the worktree


@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_to_sibling(path=None, *, fs_mode):
    path = Path(path)
    ds_src = _src_with_base_commit(path)
    ds_clone = _clone(ds_src, path, fs_mode)

    corr = _corr(ds_clone.repo)
    sibling = _sibling(ds_clone.repo)
    target = corresponding_hexsha(ds_src.repo)

    (ds_clone.pathobj / "local.txt").write_text("LOCAL")
    ds_clone.save()
    neq_(corresponding_hexsha(ds_clone.repo), target)

    res = ds_clone.reset(target=f"{sibling}/{corr}")
    _assert_reset_ok(res, ds_clone.repo, fs_mode, target)
    assert_false((ds_clone.pathobj / "local.txt").exists())  # removed local divergence


@slow  # ~12s
@with_tempfile(mkdir=True)
def test_reset_to_sibling_no_resurrection_or_work_loss(path=None, *, fs_mode):
    """gh-7772: on an adjusted branch a history-moving reset must reconcile
    git-annex's ``synced/<corr>`` ref to the target. If it does not, that ref
    still points at the discarded commit, and the next ``save`` -- which syncs on
    an adjusted branch -- merges it back. Two things then break, both severe:

    - *resurrection*: the commit the user just discarded comes back.
    - *work loss* (worse): the commit the user made *after* the reset is dropped
      in that sync -- real new work silently disappears.
    """
    path = Path(path)
    ds_src = _src_with_base_commit(path)
    ds_clone = _clone(ds_src, path, fs_mode)

    corr = _corr(ds_clone.repo)
    sibling = _sibling(ds_clone.repo)
    target = corresponding_hexsha(ds_src.repo)

    # the commit to discard, marked by a file that lives only here
    (ds_clone.pathobj / "discard.txt").write_text("DISCARD")
    ds_clone.save()
    discard_sha = corresponding_hexsha(ds_clone.repo)
    neq_(discard_sha, target)

    synced = f"synced/{corr}"
    if _is_adjusted_mode(fs_mode):
        # Seed the gh-7772 hazard explicitly: a stale synced/<corr> at the
        # discarded commit.
        ds_clone.repo.call_git(["branch", "-f", synced, discard_sha])

    res = ds_clone.reset(target=f"{sibling}/{corr}")
    _assert_reset_ok(res, ds_clone.repo, fs_mode, target)
    if _is_adjusted_mode(fs_mode):
        # direct teeth: reset moved synced/<corr> onto the reset tip, so the next
        # sync has nothing stale to merge back.
        eq_(ds_clone.repo.get_hexsha(synced),
            corresponding_hexsha(ds_clone.repo))

    # genuine new work on top of the reset; this save (a sync on an adjusted
    # branch) is what would merge a stale synced/<corr> back in.
    (ds_clone.pathobj / "precious.txt").write_text("PRECIOUS")
    ds_clone.save()

    # teeth #1 -- no resurrection: the discarded commit is back neither in the
    # worktree nor in history.
    assert_false((ds_clone.pathobj / "discard.txt").exists())
    assert_false(
        ds_clone.repo.is_ancestor(discard_sha, corresponding_hexsha(ds_clone.repo)))
    # teeth #2 -- no work loss: the new work survived the sync, with its content.
    eq_((ds_clone.pathobj / "precious.txt").read_text(), "PRECIOUS")


@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_nonexistent_target_errors(path=None, *, fs_mode):
    path = Path(path)
    ds = _ds(path, fs_mode)

    before = corresponding_hexsha(ds.repo)
    assert_in_results(
        ds.reset(target="no-such-ref", on_failure="ignore"),
        action="reset", status="error")
    eq_(corresponding_hexsha(ds.repo), before)  # unchanged
    if _is_adjusted_mode(fs_mode):
        # the error-restore path must not leave us stranded on corr
        ok_(ds.repo.is_managed_branch())


# ---------------------------------------------------------------------------
# C. Default HEAD & Dirty-tree parity (don't-refuse: match `git reset --hard`)
# ---------------------------------------------------------------------------

@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_default_head_clean_is_noop(path=None, *, fs_mode):
    path = Path(path)
    ds = _ds(path, fs_mode)

    before = corresponding_hexsha(ds.repo)
    res = ds.reset()  # default HEAD, clean tree
    _assert_reset_ok(res, ds.repo, fs_mode, before)  # no-op: ok, unchanged, still adjusted


@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_discards_unsaved_modification(path=None, *, fs_mode):
    path = Path(path)
    ds = _ds(path, fs_mode)

    tracked = ds.pathobj / "tracked.txt"
    tracked.write_text("CLEAN")
    ds.save()
    tracked_sha = corresponding_hexsha(ds.repo)

    ds.unlock("tracked.txt", result_renderer="disabled")  # writable in place (no-op if adjusted)
    tracked.write_text("DIRTY")                           # uncommitted modification

    res = ds.reset()
    _assert_reset_ok(res, ds.repo, fs_mode, tracked_sha)
    eq_(tracked.read_text(), "CLEAN")  # modification discarded -> committed content restored


@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_keeps_untracked(path=None, *, fs_mode):
    path = Path(path)
    ds = _ds(path, fs_mode)

    tracked = ds.pathobj / "tracked.txt"
    tracked.write_text("CLEAN")
    ds.save()
    tracked_sha = corresponding_hexsha(ds.repo)
    ds.unlock("tracked.txt", result_renderer="disabled")  # writable in place (no-op if adjusted)
    tracked.write_text("DIRTY")  # give the reset something real to do (teeth)
    untracked = ds.pathobj / "untracked.txt"
    untracked.write_text("KEEP")

    res = ds.reset()
    _assert_reset_ok(res, ds.repo, fs_mode, tracked_sha)
    eq_(tracked.read_text(), "CLEAN")    # tracked modification discarded
    eq_(untracked.read_text(), "KEEP")   # untracked file survived, with its content


# ---------------------------------------------------------------------------
# D. Relative targets (HEAD~N discards exactly N real commits)
# ---------------------------------------------------------------------------

@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_discards_n_commits(path=None, *, fs_mode, request):
    """Resolve the relative ref on the corresponding branch (N=N) and not on
    the adjusted branch (N=N+1) where the 'git-annex adjusted branch' commit
    sits on top of N real commits.
    """
    path = Path(path)
    ds = _ds(path, fs_mode)
    _xfail_simulated_crippled(request, ds.repo)

    (ds.pathobj / "first.txt").write_text("FIRST")
    ds.save()
    first_sha = corresponding_hexsha(ds.repo)
    (ds.pathobj / "second.txt").write_text("SECOND")
    ds.save()
    neq_(corresponding_hexsha(ds.repo), first_sha)

    res = ds.reset(target="HEAD~1")
    _assert_reset_ok(res, ds.repo, fs_mode, first_sha)
    assert_false((ds.pathobj / "second.txt").exists())    # discarded commit's file gone
    eq_((ds.pathobj / "first.txt").read_text(), "FIRST")  # kept commit's file materialised


# ---------------------------------------------------------------------------
# E. Recursive (-r) with --follow
# ---------------------------------------------------------------------------

@slow  # ~12s
@with_tempfile(mkdir=True)
def test_reset_recursive_default_resets_each_to_own_head(path=None, *, fs_mode):
    path = Path(path)
    ds = _ds_with_subds(path, fs_mode)
    ds_sub = _subds(ds)

    super_file = ds.pathobj / "super.txt"
    super_file.write_text("CLEAN")
    ds.save("super.txt")  # annexed; scoped: not the diverged sub
    super_sha = corresponding_hexsha(ds.repo)

    sub_file = ds_sub.pathobj / "sub.txt"
    sub_file.write_text("CLEAN")
    ds_sub.save("sub.txt")
    sub_sha = corresponding_hexsha(ds_sub.repo)

    eq_(super_file.read_text(), "CLEAN")
    eq_(sub_file.read_text(), "CLEAN")

    # unlock (no-op if adjusted), then make unCLEAN edits in both -- to discard
    ds.unlock("super.txt", result_renderer="disabled")
    super_file.write_text("DIRTY")
    ds_sub.unlock("sub.txt", result_renderer="disabled")
    sub_file.write_text("DIRTY")

    eq_(super_file.read_text(), "DIRTY")
    eq_(sub_file.read_text(), "DIRTY")

    res = ds.reset(recursive=True)  # default HEAD
    _assert_reset_ok(res, ds.repo, fs_mode, super_sha)
    _assert_reset_ok(res, ds_sub.repo, fs_mode, sub_sha)
    eq_(super_file.read_text(), "CLEAN")
    eq_(sub_file.read_text(), "CLEAN")


@slow  # ~12s
@with_tempfile(mkdir=True)
def test_reset_recursive_follow_parentds(path=None, *, fs_mode, request):
    path = Path(path)
    ds = _ds_with_subds(path, fs_mode)
    ds_sub = _subds(ds)
    # parentds snaps the sub back over retained annex content -- the one
    # combination the crippled-fs simulation can't render (passes on real Windows)
    _xfail_simulated_crippled(request, ds.repo)

    super_sha = corresponding_hexsha(ds.repo)
    sub_pin = corresponding_hexsha(ds_sub.repo)

    (ds_sub.pathobj / "sub.txt").write_text("DISCARD")
    ds_sub.save()
    neq_(corresponding_hexsha(ds_sub.repo), sub_pin)

    res = ds.reset(recursive=True, follow="parentds")
    _assert_reset_ok(res, ds.repo, fs_mode, super_sha)
    _assert_reset_ok(res, ds_sub.repo, fs_mode, sub_pin)
    assert_false((ds_sub.pathobj / "sub.txt").exists())    # discarded commit's file gone


@slow  # ~12s
@pytest.mark.parametrize("follow", [None, "parentds"])
@with_tempfile(mkdir=True)
def test_reset_recursive_to_sibling(path=None, *, fs_mode, follow):
    """Reset subds either to its own sibling's head or following parent's record.

    Bring sibling's parent and subds out-of-sync, i.e. subds's head is at a different
    commit than what parent records. Then reset with --follow=None or --follow=parentds.
    """
    path = Path(path)
    ds_src = _src_with_subds(path)
    ds_src_sub = _subds(ds_src)

    sibling_sha = corresponding_hexsha(ds_src.repo)
    sub_pin = corresponding_hexsha(ds_src_sub.repo)  # what the super records for the sub

    ds = _clone(ds_src, path, fs_mode, recursive=True)
    ds_sub = _subds(ds)

    # advance sibling-sub, save locally, so sibling-parent & -sub are out-of-sync
    # this creates two distinct reset target for the clone-sub
    (ds_src_sub.pathobj / "advance_sub.txt").write_text("ADVANCED")
    ds_src_sub.save()
    sub_tip = corresponding_hexsha(ds_src_sub.repo)
    neq_(sub_tip, sub_pin)

    # clone diverges from sibling, so reset has something to do
    (ds.pathobj / "diverge_clone.txt").write_text("DISCARD")
    (ds_sub.pathobj / "diverge_clone_sub.txt").write_text("DISCARD")
    ds.save(recursive=True)
    neq_(corresponding_hexsha(ds.repo), sibling_sha)
    # the teeth: ds_sub has genuinely diverged from its sibling, as well as from what
    # sibling's parent recorded
    neq_(corresponding_hexsha(ds_sub.repo), sub_pin)
    neq_(corresponding_hexsha(ds_sub.repo), sub_tip)

    # crucial: the test only works if clone-sub KNOWS about sibling-sub's state
    ds_sub.repo.fetch(remote=_sibling(ds_sub.repo))

    target = f"{_sibling(ds.repo)}/{_corr(ds.repo)}"
    res = ds.reset(recursive=True, target=target, follow=follow)
    _assert_reset_ok(res, ds.repo, fs_mode, sibling_sha)
    assert_false((ds.pathobj / "diverge_clone_sub.txt").exists())  # the divergence in sub is discarded

    # depending on the --follow argument, sub_ds should now match either
    # sub_pin (parentds) or sub_tip (default)
    if follow == "parentds":
        _assert_reset_ok(res, ds_sub.repo, fs_mode, sub_pin)      # snapped to recorded pin
        # lexists, not exists: on a normal branch the annexed file is a locked
        # symlink to (cloned-not-fetched) absent content, so exists() would follow
        # the broken symlink and report False even though the entry is present.
        assert_false(os.path.lexists(ds_sub.pathobj / "advance_sub.txt"))  # the advance was never seen by parent
    else:
        _assert_reset_ok(res, ds_sub.repo, fs_mode, sub_tip)   # resolved in its own sibling
        ok_(os.path.lexists(ds_sub.pathobj / "advance_sub.txt"))  # the advance is present


@slow  # ~10s
@pytest.mark.parametrize("target_form", ["sha", "relative"])
@with_tempfile(mkdir=True)
def test_reset_recursive_history_coordinate_requires_parentds(
        path=None, *, fs_mode, request, target_form):
    """A raw SHA and a relative ref (HEAD~1) are both parent-history coordinates
    with no per-subdataset meaning -> refused under -r unless --follow=parentds,
    which interprets them in the super and snaps subdatasets to the recorded
    pins. After the advance below, both forms name the parent-before-advance.
    """
    path = Path(path)
    ds = _ds_with_subds(path, fs_mode)
    ds_sub = _subds(ds)

    # the reset moves history over retained annex content -- the one
    # combination the crippled-fs simulation can't render (passes on real Windows)
    # see _xfail_simulated_crippled
    _xfail_simulated_crippled(request, ds.repo)

    parent_sha = corresponding_hexsha(ds.repo)
    sub_pin = corresponding_hexsha(ds_sub.repo)  # what the super records for the sub

    # the parent advances, so the reset has real work to do
    (ds.pathobj / "super.txt").write_text("DISCARD")
    ds.save()
    neq_(corresponding_hexsha(ds.repo), parent_sha)
    # the subds advances too, but the parent still records the old pointer
    (ds_sub.pathobj / "sub.txt").write_text("DISCARD")
    ds_sub.save()
    neq_(corresponding_hexsha(ds_sub.repo), sub_pin)

    target = parent_sha if target_form == "sha" else "HEAD~1"

    # no per-subds meaning -> refuse unless parentds is explicit
    assert_in_results(
        ds.reset(target=target, recursive=True, on_failure="ignore"),
        action="reset", status="impossible")
    neq_(corresponding_hexsha(ds.repo), parent_sha)  # untouched

    # with --follow=parentds: the super interprets it locally; subds snap to pins
    res = ds.reset(target=target, recursive=True, follow="parentds")
    _assert_reset_ok(res, ds.repo, fs_mode, parent_sha)
    _assert_reset_ok(res, ds_sub.repo, fs_mode, sub_pin)
    assert_false((ds.pathobj / "super.txt").exists())    # super's advance discarded
    assert_false((ds_sub.pathobj / "sub.txt").exists())  # sub's advance discarded


@slow  # ~12s
@with_tempfile(mkdir=True)
def test_reset_recursion_limit(path=None, *, fs_mode):
    # super -> sub -> subsub; -R 1 resets the super and its direct sub but stops
    # short of the nested subsub: exactly two reset records, not three.
    path = Path(path)
    ds_src = Dataset(path / "ds").create()
    ds_src_sub = ds_src.create("sub")
    ds_src_sub.create("subsub")
    ds_src.save(recursive=True)
    _adjust_for_mode(ds_src, fs_mode)  # children before parent

    ds = _clone(ds_src, path, fs_mode, recursive=True)
    ds_sub = _subds(ds)
    ds_sub_sub = _subds(ds_sub)

    super_sha = corresponding_hexsha(ds.repo)
    sub_sha = corresponding_hexsha(ds_sub.repo)
    subsub_before = corresponding_hexsha(ds_sub_sub.repo)

    (ds.pathobj / "super.txt").write_text("DISCARD")
    ds.save()
    neq_(corresponding_hexsha(ds_sub.repo), super_sha)

    (ds_sub.pathobj / "sub.txt").write_text("DISCARD")
    ds_sub.save()
    neq_(corresponding_hexsha(ds_sub.repo), sub_sha)

    (ds_sub_sub.pathobj / "subsub.txt").write_text("KEEP")
    ds_sub_sub.save()
    subsub_sha = corresponding_hexsha(ds_sub_sub.repo)
    neq_(subsub_sha, subsub_before)

    target = f"{_sibling(ds.repo)}/{_corr(ds.repo)}"
    res = ds.reset(target=target, recursive=True, recursion_limit=1)
    assert_result_count(res, 2, action="reset")  # super + direct sub, NOT subsub
    _assert_reset_ok(res, ds.repo, fs_mode, super_sha)
    _assert_reset_ok(res, ds_sub.repo, fs_mode, sub_sha)
    # no reset happened in subsub, but we can assert sha identity and adjusted mode
    _assert_reset_ok(res, ds_sub_sub.repo, fs_mode, subsub_sha)
    assert_false((ds.pathobj / "super.txt").exists())    # super's last commit is discarded
    assert_false((ds_sub.pathobj / "sub.txt").exists())  # sub's last commit is discarded
    ok_((ds_sub_sub.pathobj / "subsub.txt").exists())    # subsub's last commit is kept


# ---------------------------------------------------------------------------
# F. Adjust-mode preservation (non-unlock)
# ---------------------------------------------------------------------------

@slow  # ~8s
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
@pytest.mark.parametrize("adjust_mode, expected_string", [
    ("--fix", "fixed"),
    ("--hide-missing", "hidemissing"),
], ids=["fix", "hidemissing"])
def test_reset_preserves_adjust_mode(path=None, *, adjust_mode, expected_string):
    """Test that reset preserves the original adjust mode when moving history.

    For --hide-missing, this test is expected to xfail because datalad core
    doesn't support parsing that adjustment mode (AnnexRepo.get_corresponding_branch
    only resolves `(unlocked)` and `(fixed)`).
    """
    # Mark the --hide-missing case as xfail
    if adjust_mode == "--hide-missing":
        pytest.xfail(
            "`--hide-missing` is unsupported by datalad *core*, not by reset: "
            "AnnexRepo.get_corresponding_branch only resolves `(unlocked)` and "
            "`(fixed)` adjusted branches -- for `(hidemissing)` it returns a "
            "malformed corresponding-branch name, so reset cannot even resolve "
            "the branch to reset and `_get_adjust_mode` is never reached. "
            "If core learns `(hidemissing)` this xpasses and the xfail can be removed."
        )

    path = Path(path)
    ds = Dataset(path / "ds").create()

    # Adjust to the specified mode
    ds.repo.call_annex(["adjust", adjust_mode])
    ok_(expected_string in ds.repo.get_active_branch())

    target = corresponding_hexsha(ds.repo)
    (ds.pathobj / "discard.txt").write_text("DISCARD")
    ds.save()
    neq_(corresponding_hexsha(ds.repo), target)

    # A history-moving target routes through _reset_corresponding_branch,
    # the only place where a re-adjust could flip the mode
    res = ds.reset(target=target)
    assert_in_results(res, action="reset", status="ok")
    eq_(corresponding_hexsha(ds.repo), target)
    assert_false((ds.pathobj / "discard.txt").exists())
    ok_(ds.repo.is_managed_branch())
    branch = ds.repo.get_active_branch()
    assert expected_string in branch, \
        f"reset flipped the adjust mode to {branch!r} (expected {expected_string} preserved)"
