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

### ~~TODO 2: `dataset=dataset or ds`~~ — resolved

Fixed: changed `dataset=dataset or ds` to `dataset=dataset` in the
`diff_dataset` call.  When `dataset=None`, `diff_dataset` discovers
the dataset from CWD via its own `require_dataset()` call (same as
`Status`), and `resolve_path(p, None)` resolves relative paths against
CWD (matching `Status` behavior).

`test_save_from_relpath` verifies this: from a subdirectory, relative
paths are resolved against CWD, not dataset root.

### ~~TODO 3: tests for standalone `datalad save --from`~~ — resolved

Five tests added in `test_save.py`:

- `test_save_from_basic` — merge topology, first/second parent, notneeded
- `test_save_from_no_inner_commits` — working-tree only, no merge
- `test_save_from_with_path_filter` — only declared paths saved
- `test_save_from_recursive` — merges at both super and sub levels
- `test_save_from_relpath` — CWD-relative paths from subdirectory

### TODO 4: `test_rerun` failure on CrippledFS (adjusted branches)

`test_rerun` (a pre-existing test, not added by this PR) fails on
CrippledFS after our changes.  The test does
`ds.run('echo x > sub/sequence')` — writes to a subdataset file
without creating inner commits.  After save, `sub` is reported as
modified.

The cause: `run_command` now always passes `fr=pre_cmd_hexsha` to
Save.  When no inner commits were created (`pre_cmd_hexsha == HEAD`),
the `diff_dataset(fr=HEAD, to=None)` path is used instead of the
standard `Status()` path.  On adjusted branches, `diff_dataset` may
handle subdataset submodule pointers differently from `Status`,
leaving the subdataset dirty after save.

This cannot be reproduced locally (requires CrippledFS / adjusted
branches).  On non-CrippledFS the same code path works correctly.

**Action items**:
- Reproduce on a CrippledFS environment (Docker image or CI)
- Compare what `diff_dataset(fr=HEAD, to=None)` returns vs
  `Status()` on an adjusted branch when only a subdataset file
  changed (no commits)
- If the difference is in how adjusted-branch submodule pointers
  are reported, fix in `diff_dataset` or in `save_ds`
- If the fix is complex, consider passing `fr=None` when
  `pre_cmd_hexsha == post_cmd_hexsha` (no top-level commits) as a
  workaround — but this requires also detecting subdataset-only
  commits to avoid breaking `test_run_merge_subdataset_only`
