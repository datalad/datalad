# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
"""Tests for `datalad reset`.

Every test runs on a ``normal`` branch, an ``adjusted`` branch, and a
``crippled`` filesystem simulated via ``annex.crippledfilesystem=true``.
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


@pytest.fixture(params=("normal", "adjusted", "crippled"))
def fs_mode(request, monkeypatch):
    # crippledness is decided at `git annex init`, so set it before any create
    mode = request.param
    if mode == "crippled":
        n = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
        monkeypatch.setenv("GIT_CONFIG_KEY_{}".format(n), "annex.crippledfilesystem")
        monkeypatch.setenv("GIT_CONFIG_VALUE_{}".format(n), "true")
        monkeypatch.setenv("GIT_CONFIG_COUNT", str(n + 1))
    return mode


def _xfail_simulated_crippled(request, repo):
    """The crippled-fs simulation on a symlink-capable filesystem cannot reset
    over present annexed content (passes on real Windows)."""
    if repo.is_crippled_fs() and has_symlink_capability():
        request.applymarker(pytest.mark.xfail(
            strict=False,
            reason="crippled-fs simulation cannot reset over present annexed "
                   "content; only real Windows can"))


def _is_adjusted_mode(mode):
    return mode in ("adjusted", "crippled")


def _prepare(ds, mode):
    """Adjust DS (and its subdatasets) for MODE; skip a normal leg where the
    filesystem forces adjusted branches."""
    if mode == "adjusted":
        for sub in ds.subdatasets(recursive=True, result_xfm="datasets",
                                  result_renderer="disabled"):
            maybe_adjust_repo(sub.repo)
        maybe_adjust_repo(ds.repo)
    if mode == "normal" and ds.repo.is_managed_branch():
        pytest.skip("normal branch N/A on a crippled filesystem")
    return ds


def _corr(repo):
    return repo.get_corresponding_branch() or repo.get_active_branch()


def _assert_reset_ok(res, repo, fs_mode, target_sha):
    assert_in_results(res, action="reset", status="ok")
    eq_(corresponding_hexsha(repo), target_sha)
    if _is_adjusted_mode(fs_mode):
        ok_(repo.is_managed_branch())


def _ds(path, mode):
    return _prepare(Dataset(path / "ds").create(), mode)


def _with_subds(path, name):
    ds = Dataset(path / name).create()
    ds_sub = ds.create("sub")
    (ds.pathobj / "base.txt").write_text("BASE")
    (ds_sub.pathobj / "subbase.txt").write_text("BASE")
    ds.save(recursive=True)
    return ds


def _src_with_base_commit(path):
    ds_src = Dataset(path / "source").create()
    (ds_src.pathobj / "base.txt").write_text("BASE")
    ds_src.save()
    return ds_src


def _clone(ds_src, path, mode, recursive=False):
    return _prepare(install(source=ds_src.path, path=path / "clone",
                            recursive=recursive, result_xfm="datasets"), mode)


def _sibling(repo):
    return repo.get_remotes()[0]


def _subds(ds):
    return ds.subdatasets(result_xfm="datasets", result_renderer="disabled")[0]


@with_tempfile(mkdir=True)
def test_reset_unsupported_follow_rejected(path=None):
    ds = Dataset(Path(path) / "ds").create()
    with pytest.raises(ValueError):
        ds.reset(follow="bogus", on_failure="ignore")


@slow  # ~10s
@with_tempfile(mkdir=True)
def test_is_current_head_routing(path=None, *, fs_mode):
    """Only a target at the current HEAD (adjusted HEAD or corresponding tip)
    takes the view-only reset."""
    if fs_mode == "normal":
        pytest.skip("branch needs to be adjusted")

    path = Path(path)
    ds_src = _src_with_base_commit(path)
    maybe_unadjust_repo(ds_src.repo)
    ds = _clone(ds_src, path, fs_mode)
    sibling_ref = f"{_sibling(ds.repo)}/{_corr(ds.repo)}"

    corr_tip = corresponding_hexsha(ds.repo)
    view_tip = ds.repo.get_hexsha("HEAD")
    neq_(corr_tip, view_tip)

    for target in ("HEAD", corr_tip, view_tip, sibling_ref):
        ok_(_is_current_head(ds.repo, target))
    for target in ("HEAD~1", corresponding_hexsha(ds.repo, "HEAD~1")):
        assert_false(_is_current_head(ds.repo, target))

    # a sibling that moved on
    (ds_src.pathobj / "advance_src.txt").write_text("ADVANCED")
    ds_src.save()
    ds.repo.fetch(remote=_sibling(ds.repo))
    assert_false(_is_current_head(ds.repo, sibling_ref))


@slow  # ~8s
@pytest.mark.parametrize("target_form", ["sha", "relative", "sibling"])
@with_tempfile(mkdir=True)
def test_reset_to_target(path=None, *, fs_mode, target_form):
    """Each target form discards the one local commit; ``HEAD~1`` counts real
    commits, not the adjusted view commit."""
    path = Path(path)
    ds_src = _src_with_base_commit(path)
    ds = _clone(ds_src, path, fs_mode)
    target_sha = corresponding_hexsha(ds_src.repo)

    (ds.pathobj / "local.txt").write_text("LOCAL")
    ds.save()
    neq_(corresponding_hexsha(ds.repo), target_sha)

    target = {"sha": target_sha,
              "relative": "HEAD~1",
              "sibling": f"{_sibling(ds.repo)}/{_corr(ds.repo)}"}[target_form]
    _assert_reset_ok(ds.reset(target=target), ds.repo, fs_mode, target_sha)
    assert_false((ds.pathobj / "local.txt").exists())


@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_keeps_annexed_content(path=None, *, fs_mode, request):
    """Retained annexed files are materialised; discarded ones keep their
    content in the annex."""
    path = Path(path)
    ds = _ds(path, fs_mode)
    _xfail_simulated_crippled(request, ds.repo)

    (ds.pathobj / "keep.bin").write_text("KEEP")
    ds.save()
    keep_sha = corresponding_hexsha(ds.repo)
    (ds.pathobj / "discard.bin").write_text("DISCARD")
    ds.save()
    discard_key = ds.repo.get_file_annexinfo("discard.bin").get("key")
    ok_(discard_key)

    _assert_reset_ok(ds.reset(target=keep_sha), ds.repo, fs_mode, keep_sha)
    assert_false((ds.pathobj / "discard.bin").exists())
    ok_(ds.repo.get_contentlocation(discard_key))
    eq_((ds.pathobj / "keep.bin").read_text(), "KEEP")


@slow  # ~8s
@with_tempfile(mkdir=True)
def test_reset_nonexistent_target_errors(path=None, *, fs_mode):
    ds = _ds(Path(path), fs_mode)
    before = corresponding_hexsha(ds.repo)
    assert_in_results(
        ds.reset(target="no-such-ref", on_failure="ignore"),
        action="reset", status="error")
    eq_(corresponding_hexsha(ds.repo), before)
    if _is_adjusted_mode(fs_mode):
        ok_(ds.repo.is_managed_branch())


@slow  # ~8s
@pytest.mark.parametrize("target", ["HEAD", "HEAD~1"])
@with_tempfile(mkdir=True)
def test_reset_dirty_tree(path=None, *, fs_mode, request, target):
    """Like ``git reset --hard``: discard tracked modifications, keep untracked
    files -- with or without moving history."""
    ds = _ds(Path(path), fs_mode)
    if target != "HEAD":
        _xfail_simulated_crippled(request, ds.repo)
    tracked = ds.pathobj / "tracked.txt"
    tracked.write_text("CLEAN")
    ds.save()
    tracked_sha = corresponding_hexsha(ds.repo)
    if target != "HEAD":
        (ds.pathobj / "discard.txt").write_text("DISCARD")
        ds.save()
    ds.unlock("tracked.txt", result_renderer="disabled")
    tracked.write_text("DIRTY")
    untracked = ds.pathobj / "untracked.txt"
    untracked.write_text("KEEP")

    _assert_reset_ok(ds.reset(target=target), ds.repo, fs_mode, tracked_sha)
    eq_(tracked.read_text(), "CLEAN")
    eq_(untracked.read_text(), "KEEP")


@slow  # ~12s
@with_tempfile(mkdir=True)
def test_reset_recursive_default_head(path=None, *, fs_mode):
    """``-r`` with plain HEAD discards modifications in every dataset."""
    ds = _prepare(_with_subds(Path(path), "ds"), fs_mode)
    ds_sub = _subds(ds)
    shas = {}
    for d, name in ((ds, "super.txt"), (ds_sub, "sub.txt")):
        (d.pathobj / name).write_text("CLEAN")
        d.save(name)
        shas[d.path] = corresponding_hexsha(d.repo)
        d.unlock(name, result_renderer="disabled")
        (d.pathobj / name).write_text("DIRTY")

    res = ds.reset(recursive=True)
    for d, name in ((ds, "super.txt"), (ds_sub, "sub.txt")):
        _assert_reset_ok(res, d.repo, fs_mode, shas[d.path])
        eq_((d.pathobj / name).read_text(), "CLEAN")


@slow  # ~12s
@pytest.mark.parametrize("follow", [None, "parentds"])
@with_tempfile(mkdir=True)
def test_reset_recursive_to_sibling(path=None, *, fs_mode, follow):
    """The subdataset resets to its own sibling's tip by default, or to the
    revision the superdataset records with ``--follow=parentds``."""
    path = Path(path)
    ds_src = _with_subds(path, "source")
    ds_src_sub = _subds(ds_src)
    sibling_sha = corresponding_hexsha(ds_src.repo)
    sub_pin = corresponding_hexsha(ds_src_sub.repo)

    ds = _clone(ds_src, path, fs_mode, recursive=True)
    ds_sub = _subds(ds)

    # the sibling's sub moves past what its super records
    (ds_src_sub.pathobj / "advance_sub.txt").write_text("ADVANCED")
    ds_src_sub.save()
    sub_tip = corresponding_hexsha(ds_src_sub.repo)

    # local divergence to discard
    (ds.pathobj / "diverge_clone.txt").write_text("DISCARD")
    (ds_sub.pathobj / "diverge_clone_sub.txt").write_text("DISCARD")
    ds.save(recursive=True)
    ds_sub.repo.fetch(remote=_sibling(ds_sub.repo))

    res = ds.reset(recursive=True, follow=follow,
                   target=f"{_sibling(ds.repo)}/{_corr(ds.repo)}")
    _assert_reset_ok(res, ds.repo, fs_mode, sibling_sha)
    assert_false((ds_sub.pathobj / "diverge_clone_sub.txt").exists())
    _assert_reset_ok(res, ds_sub.repo, fs_mode,
                     sub_pin if follow == "parentds" else sub_tip)
    # lexists: the annexed file may be a symlink to absent content
    eq_(os.path.lexists(ds_sub.pathobj / "advance_sub.txt"),
        follow != "parentds")


@slow  # ~10s
@pytest.mark.parametrize("target_form", ["sha", "relative"])
@with_tempfile(mkdir=True)
def test_reset_recursive_history_coordinate_requires_parentds(
        path=None, *, fs_mode, request, target_form):
    """A SHA or ``HEAD~N`` under ``-r`` is refused without
    ``--follow=parentds``."""
    ds = _prepare(_with_subds(Path(path), "ds"), fs_mode)
    ds_sub = _subds(ds)
    _xfail_simulated_crippled(request, ds.repo)
    parent_sha = corresponding_hexsha(ds.repo)
    sub_pin = corresponding_hexsha(ds_sub.repo)

    (ds_sub.pathobj / "sub.txt").write_text("DISCARD")
    ds_sub.save()
    (ds.pathobj / "super.txt").write_text("DISCARD")
    ds.save("super.txt")
    target = parent_sha if target_form == "sha" else "HEAD~1"

    assert_in_results(
        ds.reset(target=target, recursive=True, on_failure="ignore"),
        action="reset", status="impossible")
    neq_(corresponding_hexsha(ds.repo), parent_sha)

    res = ds.reset(target=target, recursive=True, follow="parentds")
    _assert_reset_ok(res, ds.repo, fs_mode, parent_sha)
    _assert_reset_ok(res, ds_sub.repo, fs_mode, sub_pin)
    assert_false((ds.pathobj / "super.txt").exists())
    assert_false((ds_sub.pathobj / "sub.txt").exists())


@slow  # ~12s
@with_tempfile(mkdir=True)
def test_reset_recursion_limit(path=None, *, fs_mode):
    """``-R 1`` resets super and sub, not subsub."""
    path = Path(path)
    ds_src = Dataset(path / "ds").create()
    ds_src.create("sub").create("subsub")
    ds_src.save(recursive=True)

    ds = _clone(ds_src, path, fs_mode, recursive=True)
    ds_sub = _subds(ds)
    ds_sub_sub = _subds(ds_sub)
    super_sha = corresponding_hexsha(ds.repo)
    sub_sha = corresponding_hexsha(ds_sub.repo)

    for d in (ds_sub_sub, ds_sub, ds):
        (d.pathobj / "local.txt").write_text("LOCAL")
        d.save("local.txt")
    subsub_sha = corresponding_hexsha(ds_sub_sub.repo)

    res = ds.reset(target=f"{_sibling(ds.repo)}/{_corr(ds.repo)}",
                   recursive=True, recursion_limit=1)
    assert_result_count(res, 2, action="reset")
    _assert_reset_ok(res, ds.repo, fs_mode, super_sha)
    _assert_reset_ok(res, ds_sub.repo, fs_mode, sub_sha)
    eq_(corresponding_hexsha(ds_sub_sub.repo), subsub_sha)


@slow  # ~8s
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_reset_preserves_adjust_mode(path=None):
    """A history-moving reset re-adjusts in the original (non-unlock) mode."""
    ds = Dataset(Path(path) / "ds").create()
    ds.repo.call_annex(["adjust", "--fix"])
    target = corresponding_hexsha(ds.repo)
    (ds.pathobj / "discard.txt").write_text("DISCARD")
    ds.save()

    assert_in_results(ds.reset(target=target), action="reset", status="ok")
    eq_(corresponding_hexsha(ds.repo), target)
    ok_("(fixed)" in ds.repo.get_active_branch())
