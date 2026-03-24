# Run-merge commits in subdataset hierarchies

## Status: implemented

Merge-commit wrapping now works across subdataset hierarchies.
The logic lives in `Save` (via the `fr=` parameter) rather than in
`run_command`, making it available to both `datalad run` and standalone
`datalad save --from`.

## Problem

When `datalad run` executes a command that creates git commits inside
subdatasets, the merge-commit wrapping must operate at every level of the
hierarchy — not just the top-level dataset.  Each subdataset that gained
inner commits needs its own merge commit carrying the run record, and the
parent's submodule pointer must reference the subdataset's merge commit
(not the raw inner commit).

## Implementation

### Architecture

The merge-commit logic is a first-class feature of `datalad save` via the
`--from` / `fr=` parameter (`save.py`).  `run_command` passes
`fr=pre_cmd_hexsha` to `Save.__call__()`, which handles discovery, saving,
and merge creation in a single pass.

When `fr` is `None` (inject mode or plain `datalad save`), the standard
`Status`-based discovery is used — identical to prior behavior.

### Discovery: `diff_dataset` replaces `Status` when `fr` is set

`Save.__call__` conditionally uses `diff_dataset(fr=..., to=None)` instead
of `Status()` for change discovery (`save.py:292-326`).  This is necessary
because:

- `Status` hardcodes `fr='HEAD'` — after the command moves HEAD, it cannot
  see the pre-command baseline.
- `diff_dataset` accepts an explicit `fr` and **translates it
  per-subdataset** via `prev_gitshasum` from the parent's diff result
  (`diff.py:401-411`).

The `dataset` argument is passed as the original (non-Dataset-instance)
value to preserve `resolve_path()` CWD-relative semantics matching the
`Status()` branch (see `resolve_path()` docs: only Dataset *instances*
trigger dataset-root-relative resolution).

### Merge creation: bottom-up in `save_ds`

Inside the `save_ds` closure (`save.py:396-487`):

1. **`fr_map`** maps each dataset path to its pre-command hexsha
   (top-level gets `fr` directly; subdatasets get `prev_gitshasum`
   from diff_dataset results).

2. **Merge detection** per dataset: `had_inner = (pre_hexsha is not None
   and pre_hexsha != start_commit)`.  Additionally, `child_merged` checks
   if any child subdataset was merged (upward propagation via
   `_merged_datasets` set).

3. **Save remaining changes**: if the dataset has uncommitted changes,
   `repo.save_()` commits them with a "Remaining changes" message (when a
   merge follows) or the run record message (when no merge needed).

4. **Create merge**: `_create_merge_commit(repo, pre_hexsha, message)`
   produces a two-parent commit: parent1 = pre-command state (linear
   first-parent history), parent2 = current HEAD (all changes), tree =
   current HEAD's tree.

5. **Record in `_merged_datasets`** so parent datasets know to create
   their own merge even if they had no direct inner commits.

Bottom-up ordering is guaranteed by `ProducerConsumerProgressLog` with
`sorted(..., reverse=True)` + `no_subds_in_futures`.

### Adjusted-branch handling

`_create_merge_commit` (`save.py:59-111`) checks `is_managed_branch()`
per-repo.  On adjusted branches: `git annex sync` → `commit-tree` on
original branch → `git annex merge`.  Each subdataset independently
handles its own adjusted-branch state.

### Run record placement

Option A (duplicate): the full run record is embedded in every dataset's
merge commit message.  This matches the existing docstring claim
(`run.py:116-117`) that the record is "duplicated in each modified
(sub)dataset" and allows each subdataset to be understood independently.

### `run_command` simplification

`run_command` (`run.py:1170-1182`) is now a single `Save.__call__()` with
`fr=pre_cmd_hexsha`:

```python
if do_save:
    with chpwd(pwd):
        for r in Save.__call__(
                dataset=ds_path,
                path=outputs_to_save,
                recursive=True,
                message=msg,
                jobs=jobs,
                fr=pre_cmd_hexsha,   # None for inject → standard save
                ...):
            yield r
```

This replaced ~120 lines of `diff_dataset` traversal, merge detection,
upward propagation, and manual `save_()` calls that previously lived in
`run_command`.

## Test coverage

Tests in `test_run.py` (all `@known_failure_windows`,
`@pytest.mark.ai_generated`):

| Test | Scenario |
|------|----------|
| `test_run_merge_commits` | Single/multiple inner commits, mixed committed+uncommitted |
| `test_run_explicit_dirty_committed` | Explicit mode inner commit check + config override |
| `test_run_merge_subdataset_only` | Inner commit only in sub → merges in both |
| `test_run_merge_both_levels` | Inner commits in super and sub → merges in both |
| `test_run_merge_three_levels` | Three-level hierarchy, commit at leaf → merges propagate up |
| `test_run_merge_no_subdataset_change` | Commit only in super → sub HEAD unchanged |
| `test_run_merge_subdataset_deletions` | Committed + uncommitted deletions in sub |
| `test_rerun_merge` (`test_rerun.py`) | `rerun` traverses merge first-parent correctly |

Adjusted-branch test (scenario 4 from design) is covered by
`test_run_merge_commits` on CrippledFS CI environments where all repos
are on adjusted branches.

## Resolved questions

- **`rerun` compatibility**: resolved.  `datalad rerun` extracts the run
  record from the merge commit message (option A — duplicate records).
  `test_rerun_merge` verifies this.  `rerun` follows first-parent by
  default, which skips the inner commits inside the merge.

- **Interaction with `--explicit`**: resolved.  When `path` is provided
  (from `outputs_to_save`), it is passed to `diff_dataset` to constrain
  discovery.  The `dirty-committed` check in `run_command` catches inner
  commits that sweep in undeclared files.  `test_run_explicit_dirty_committed`
  verifies both the error path and the config override.

- **Distinguishing command commits from pre-existing state**: resolved.
  `run` requires a clean tree (checked before command execution).
  `--explicit` mode skips that check, but the `dirty-committed` check
  catches undeclared files swept in by inner commits.

- **Partial failures**: partially addressed.  Each `_create_merge_commit`
  is an atomic `update_ref` per dataset.  If a parent merge fails after a
  child succeeded, the child's merge is already recorded.  The parent's
  `save_ds` would yield an error result.  No rollback mechanism exists,
  but the child state is valid on its own.  This is consistent with how
  recursive `save` already handles partial failures.

## TODO

### ~~TODO 1: `untracked` mode~~ — resolved

Fixed: the `fr` branch now passes `untracked='normal'` to
`diff_dataset` (matching the old `run_command` behavior), instead of
`untracked_mode` (`'all'`).

**Why it matters**: `'all'` calls `git ls-files -o` which enumerates
every individual untracked file; `'normal'` adds `--directory
--no-empty-directory` which collapses untracked directories to single
entries.  With a `node_modules/` or `build/` containing 50k files,
`'all'` would build a 50k-entry `paths_by_ds` dict; `'normal'` builds
1 entry.

**Why `'normal'` is safe**: `save_()` handles directory entries
correctly — they land in `untracked_dirs`, get checked for submodules,
then `git add <dir>/` recursively adds all contents.  Dotfile
directories (e.g. `.hidden/`) are also reported by `--directory`.

### TODO 2: `dataset=dataset or ds` — path resolution when `dataset=None`

When `Save` is called without an explicit `dataset` argument (e.g.,
standalone `datalad save --from HEAD~3 somefile` without `-d`),
`dataset` is `None`.  The expression `dataset or ds` falls back to
`ds` — a `Dataset` instance from `require_dataset()`.

**Problem**: `resolve_path(p, Dataset_instance)` resolves relative
paths against the dataset root, while `resolve_path(p, None)` (used
by `Status` when `dataset=None`) resolves against CWD.  This means
a user running `datalad save --from HEAD~3 myfile` from a
subdirectory would get different path resolution than
`datalad save myfile` (without `--from`).

**Action items**:
- Write a test: from a subdirectory of a dataset (without `-d`),
  run `save(path=['somefile'], fr=<commit>)` and verify that
  `somefile` is resolved relative to CWD (matching `save` without
  `fr`).  This test will currently fail and document the bug.
- Fix: when `dataset` is `None`, pass `None` to `diff_dataset` so
  it falls through to `require_dataset()` internally, which returns a
  Dataset instance but `resolve_path` still receives `None` as `ds`
  and resolves against CWD.  Or: resolve paths explicitly before
  calling diff_dataset.
- Alternatively: pass `dataset` unconditionally (even when `None`)
  since `diff_dataset` calls `require_dataset()` itself.  However,
  `diff_dataset(dataset=None)` may not discover the dataset from CWD
  the same way `Status(dataset=None)` does — needs verification.

### TODO 3: tests for standalone `datalad save --from`

The `fr=` parameter is documented as independently useful ("can also
be used standalone to close a unit of work as a merge"), but all
current tests exercise it indirectly through `datalad run`.

**Action items** — extend existing save tests in `test_save.py`:

- **`test_save` or new `test_save_from_basic`**: create commits A, B, C.
  Call `save(fr=A)`.  Verify: merge commit at HEAD, first-parent = A,
  second-parent = C, run of `git log --first-parent` is linear.  Then
  verify `save(fr=HEAD)` (no changes since baseline) → `status='notneeded'`.

- **`test_subdataset_save` or new `test_save_from_recursive`**: create a
  dataset with subdataset.  Make commits in both.  Call
  `save(fr=<before>, recursive=True)`.  Verify merge commits at both
  levels with correct `fr_map` propagation.

- **`test_relpath_add` / `test_symlinked_relpath` extension**: from a
  subdirectory, call `save(path=['somefile'], fr=<commit>)`.  Verify the
  path is resolved relative to CWD, not dataset root (this is the
  TODO 2 bug — the test should initially fail, then pass after the fix).

- **`test_save_from_no_inner_commits`**: `fr=HEAD` with only working-tree
  changes (no intermediate commits).  Verify: plain save, no merge commit.
  This ensures `fr=` falls back correctly when there's nothing to merge.

- **`test_save_from_with_path_filter`**: `fr=<commit>` with explicit
  `path=` argument.  Verify only the specified paths are saved, other
  changed files remain uncommitted — matching `save(path=...)` behavior
  without `fr`.

These tests establish behavioral expectations that work on TODOs 1
and 2 must preserve.
