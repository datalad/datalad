# Run-merge commits in subdataset hierarchies

## Status: implemented

## Problem

When `datalad run` executes a command that creates git commits inside
subdatasets, the merge-commit wrapping must operate at every level of
the hierarchy — not just the top-level dataset.  Each subdataset that
gained inner commits needs its own merge commit carrying the run
record, and the parent's submodule pointer must reference the
subdataset's merge commit (not the raw inner commit).

## Architecture

### Two-phase approach: detect, then save

`run_command` (`run.py`) handles **detection** — did the command create
commits anywhere?  `Save` (`save.py`) handles **discovery, saving, and
merge creation** via the `fr=` parameter.

```
run_command:
  1. Snapshot: pre_cmd_hexsha + git submodule status --recursive
  2. Execute command
  3. Detect: compare top-level HEAD + submodule status string
  4. Save(fr=pre_cmd_hexsha if commits detected else None,
         _fr_sub_info=parsed submodule status if needed)

Save.__call__(fr=...):
  if fr is set:
    diff_dataset(fr=...) for change discovery
    _inject_sub_info() for adjusted-branch fixups
  else:
    Status() for standard discovery
  → paths_by_ds, fr_map
  → save_ds (bottom-up): save_ + merge if needed
```

### Why `fr=` lives in Save (not run_command)

The initial implementation kept all merge logic in `run_command`:
diff_dataset traversal, merge detection, upward propagation, and manual
`save_()` calls (~120 lines).  This duplicated Save's own tree walk.

The current design makes merge-commit creation a first-class feature of
`datalad save` via `--from` / `fr=`.  This:
- Eliminates the duplicate traversal
- Makes `datalad save --from <commit>` independently useful
- Reduces `run_command`'s save block to a single `Save.__call__()` call

### Why `fr=` is conditional (not always passed)

The initial refactoring always passed `fr=pre_cmd_hexsha` to Save.
This broke `test_rerun` on CrippledFS because `diff_dataset` handles
adjusted-branch subdataset pointers differently from `Status`.
Specifically, when no commits were created, `diff_dataset(fr=HEAD,
to=None)` on adjusted branches misreports submodule state, leaving
subdatasets dirty after save.

The fix: `fr=` is only passed when `cmd_made_commits` is True (the
command actually created commits somewhere).  When it didn't, `fr=None`
falls through to the standard Status-based save path which handles
adjusted branches correctly.

### Commit detection: cheap submodule status comparison

The initial implementation called `ds.subdatasets(recursive=True)` and
instantiated a `Dataset().repo.get_hexsha()` for every present
subdataset before every `run` invocation — O(n) Dataset objects.

The current design uses a single `git submodule status --recursive`
call (one git process) to snapshot the submodule state as a string.
After the command, if the top-level HEAD didn't change, a second
`git submodule status --recursive` is compared string-wise.  If the
strings differ, subdataset commits were created.  The per-sub SHA
parsing (via `_parse_sub_status`) is only done when actually needed
for `_fr_sub_info`.

### Change discovery: `diff_dataset` replaces `Status`

When `fr` is set, `Save.__call__` uses `diff_dataset(fr=..., to=None)`
instead of `Status()`.  This is necessary because `Status` hardcodes
`fr='HEAD'` — after the command moves HEAD, it cannot see the
pre-command baseline.  `diff_dataset` accepts an explicit `fr` and
translates it per-subdataset via `prev_gitshasum` from the parent's
diff result (`diff.py:401-411`).

Key details:
- `dataset=dataset` (not `ds`) preserves CWD-relative path resolution
  matching `Status` semantics (see `resolve_path()` docs)
- `untracked='normal'` (not `'all'`) reports untracked directories as
  single entries, avoiding huge `paths_by_ds` dicts for large
  untracked trees

### Adjusted-branch workaround: `_inject_sub_info`

On adjusted branches, `diff_dataset` reports subdatasets as `clean`
even when they have new commits, because the index submodule pointer
records the adjusted SHA (which doesn't change).  Neither
`diff_dataset` nor `Status` can detect this.

The workaround: `run_command` passes `_fr_sub_info` (parsed from the
pre-command `git submodule status` snapshot) to Save.  After
`diff_dataset` discovery, `_inject_sub_info()` compares each sub's
current HEAD against the pre-command SHA.  For changed subs:
1. Overrides `fr_map` with the true pre-command SHA
2. Adds the sub to `paths_by_ds` so `save_ds` processes it
3. Walks up to `ds_path`, ensuring each ancestor has `fr_map` and
   `paths_by_ds` entries for merge propagation

This is a private parameter (`_fr_sub_info`, not exposed via CLI).

### Merge creation: bottom-up in `save_ds`

Inside the `save_ds` closure:

1. **`fr_map`** maps each dataset path to its pre-command hexsha.
2. **`had_inner`**: `pre_hexsha is not None and pre_hexsha != start_commit`.
3. **`child_merged`**: any child path in `_merged_datasets` set
   (requires `pre_hexsha is not None`).
4. **`will_merge`** = `had_inner or child_merged` — always implies
   `pre_hexsha` is valid.
5. If uncommitted changes exist: `repo.save_()` with "Remaining
   changes after command execution" message (when merge follows) or
   the run record message (when no merge).
6. If `will_merge`: `_create_merge_commit(repo, pre_hexsha, message)`.
7. Record in `_merged_datasets` for upward propagation.

Bottom-up ordering: `ProducerConsumerProgressLog` with
`sorted(..., reverse=True)` + `no_subds_in_futures`.

### `_create_merge_commit`

Produces a two-parent commit via `git commit-tree`:
- parent1 = pre-command state (linear first-parent history)
- parent2 = current HEAD (all changes)
- tree = current HEAD's tree

On adjusted branches: `git annex sync` → `commit-tree` on original
branch → `git annex merge` to propagate back.

### Run record placement

The full run record is embedded in every dataset's merge commit
message (option A from design).  This matches the existing behavior
that the record is "duplicated in each modified (sub)dataset" and
allows each subdataset to be understood independently.

## Test coverage

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
| `test_save_from_basic` | Merge topology, first/second parent, notneeded |
| `test_save_from_no_inner_commits` | Working-tree only, no merge |
| `test_save_from_with_path_filter` | Only declared paths saved |
| `test_save_from_recursive` | Merges at both super and sub levels |
| `test_save_from_relpath` | CWD-relative paths from subdirectory |

Test helpers `_merge_ref(repo)` and `_assert_run_merge(ds)` in
`test_run.py` handle adjusted-branch commit offsets (`HEAD~1` vs
`HEAD`) and are imported by `test_save.py` and `test_rerun.py`.

## Resolved questions

- **`rerun` compatibility**: `datalad rerun` extracts the run record
  from the merge commit message.  `rerun` follows first-parent by
  default, which skips inner commits inside the merge.

- **`--explicit` interaction**: `path` from `outputs_to_save` is
  passed to `diff_dataset` to constrain discovery.  The
  `dirty-committed` check catches undeclared files swept in by inner
  commits.

- **Pre-existing state vs command commits**: `run` requires a clean
  tree.  `--explicit` skips that check but `dirty-committed` catches
  undeclared changes.

- **Partial failures**: each `_create_merge_commit` is an atomic
  `update_ref`.  No rollback, but consistent with how recursive `save`
  handles partial failures.

## Design evolution

### Initially: merge logic inline in run_command

The first implementation kept diff_dataset traversal, merge detection,
upward propagation, and manual `save_()` calls in `run_command`
(~120 lines).  This worked but duplicated Save's tree walk and was not
reusable outside of `run`.

**Changed to**: merge logic in Save via `fr=` parameter — single
traversal, reusable as `datalad save --from`.

### Initially: always pass fr= to Save

After moving merge logic to Save, `fr=pre_cmd_hexsha` was passed
unconditionally.  This used `diff_dataset` even when no commits were
created, which broke `test_rerun` on CrippledFS — `diff_dataset`
handles adjusted-branch submodule pointers differently from `Status`,
leaving subs dirty when no actual commits occurred.

**Changed to**: conditional `fr=` — only when `cmd_made_commits` is
True.  Detection uses cheap `git submodule status` string comparison.

### Initially: untracked='all' inherited from Status path

The `fr` branch inherited `untracked_mode='all'` from the standard
Save path, enumerating every file in untracked directories.

**Changed to**: `untracked='normal'` when `fr` is set — reports
untracked dirs as single entries.  Benchmarked: 26% faster at 5000
files, scaling with directory size.

### Initially: O(n) Dataset instantiations for commit detection

Pre-command subdataset snapshot called `ds.subdatasets(recursive=True)`
and instantiated `Dataset().repo.get_hexsha()` for each — expensive
on every `datalad run` invocation.

**Changed to**: single `git submodule status --recursive` call.  The
output is compared as a string; per-sub SHA parsing is deferred to
when actually needed.

### Initially: dataset=dataset or ds

When `dataset=None` (standalone `datalad save --from`), the fallback
`or ds` passed a Dataset instance to `diff_dataset`, causing
`resolve_path()` to resolve relative paths against the dataset root
instead of CWD.

**Changed to**: `dataset=dataset` unconditionally — `diff_dataset`
discovers the dataset from CWD via its own `require_dataset()`.

## Performance

Benchmarks in `benchmarks/save_run.py` (10 annex subs × 1000 files):

| Operation | Time | vs baseline |
|-----------|------|-------------|
| `save` (no fr=, Status path) | ~4.2s | baseline |
| `save --from` (diff_dataset, no inner commits) | ~4.2s | ~1.0x |
| `save --from` (with 2-sub merges) | ~4.2s | ~1.0x |
| `run` (no inner commits) | ~4.2s | ~1.0x |
| `run` (inner commits in 2/10 subs) | ~4.2s | ~1.0x |

On lightweight single-dataset benchmarks, `run` shows ~20ms overhead
from the `git submodule status` call — invisible on real workloads.
