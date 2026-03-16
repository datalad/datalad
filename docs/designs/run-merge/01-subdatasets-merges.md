# Run-merge commits in subdataset hierarchies

## Status: TODO

## Problem

When `datalad run` executes a command that creates git commits inside
subdatasets, the merge-commit wrapping (introduced in this PR) only
operates on the top-level dataset.  Subdatasets that gained inner commits
during command execution receive no merge commit and therefore no run
record annotation at their level.

## Current behavior

### Detection is top-level only

`pre_cmd_hexsha` and `post_cmd_hexsha` are computed only for the dataset
on which `run()` was invoked (`run.py:1019,1026`):

```python
pre_cmd_hexsha = ds.repo.get_hexsha() if not inject else None
# ... command executes ...
post_cmd_hexsha = ds.repo.get_hexsha() if not inject else None
cmd_made_commits = (
    pre_cmd_hexsha is not None
    and post_cmd_hexsha is not None
    and pre_cmd_hexsha != post_cmd_hexsha
)
```

No subdataset HEADs are recorded or compared.

### Save is recursive but produces regular commits

The `Save(recursive=True)` call (`run.py:1162-1173`) does save bottom-up
through the hierarchy: subdatasets first, then parent submodule-pointer
updates.  But these are ordinary commits, not merge commits carrying the
run record.

### Merge commit is created only at top level

The `git commit-tree` merge (`run.py:1178-1191`) operates only on the
top-level repo.  The subdataset's inner commits end up as ancestors of
the submodule pointer recorded in the superdataset's merge, but the
subdataset itself has no merge commit wrapping them.

### Consequence

Given a superdataset `ds` with subdataset `sub`, and a command like:

```bash
datalad run 'cd sub && touch foo && git add foo && git commit -m inner'
```

The result is:

- **`sub`**: has the bare "inner" commit.  No merge commit, no run record.
  `Save` may add a follow-up commit for any remaining dirty state, but
  it's a plain commit.
- **`ds`**: gets a merge commit if its own HEAD changed (due to the
  submodule pointer update from `Save`).  The run record lives only here.

If the command creates commits only in `sub` without changing `ds`'s own
working tree, then `cmd_made_commits` is `False` for `ds` and no merge
is created anywhere.

## Desired behavior

Each dataset in the hierarchy where the command created intermediate
commits should get its own merge commit that:

1. Wraps the inner commit(s) in that dataset
2. Carries the run record (or a reference to the top-level run record)
3. Has first-parent = pre-command state, second-parent = post-command
   state (same topology as the current top-level merge)

The superdataset's merge commit then records submodule pointers that
point to the subdatasets' merge commits, giving a consistent merge
topology across the entire hierarchy.

## Implementation plan

### Key insight: Diff and Status diverge on `fr` handling

`datalad diff` and `datalad status` both use `repo.diffstatus()` under
the hood but handle the `fr` (baseline revision) parameter very
differently:

**`datalad diff`** (`diff.py:_diff_ds`, line 296):
- Accepts `fr`/`to` as parameters, passes them directly to
  `repo.diffstatus(fr, to)` (line 331-337).
- For subdataset recursion, **translates `fr`/`to` per-subdataset**
  using `prev_gitshasum`/`gitshasum` from the parent's diff result
  (lines 404-411):
  ```python
  fr=props['prev_gitshasum']   # pre-command sub pointer
  to=None if to is None else props['gitshasum']
  ```
- Supports `order='bottom-up'` for processing deepest subdatasets first.

**`datalad status`** (`status.py:yield_dataset_status`, line 105):
- **Hardcodes `fr='HEAD'`** (line 160), no parameter to override.
- For subdataset recursion, passes **`None`** as paths (line 207) —
  no `fr` translation, each sub just uses its own HEAD.

**`datalad save`** (`save.py:Save.__call__`, line 222):
- Calls `Status()` internally — inherits the hardcoded `fr='HEAD'`.
- No `fr`/`to` parameters in its interface.

So Save → Status → `diffstatus(fr='HEAD')` is locked to comparing
against current HEAD.  After the command moves HEAD, `prev_gitshasum`
for subdatasets reflects the **post-command** state, not pre-command.

### Recommended approach: use `diff_dataset` with `fr=pre_cmd_hexsha`

The `diff_dataset()` function (`diff.py:142`) already provides
everything we need:

1. Accepts `fr`/`to` parameters with proper subdataset translation
2. Supports `order='bottom-up'` (deepest subdatasets first)
3. Reports `prev_gitshasum` (= pre-command pointer) for each
   subdataset at every level of nesting
4. Recurses automatically — no manual per-level handling

Instead of calling Save (which calls Status with hardcoded
`fr='HEAD'`), the `cmd_made_commits` path in `run_command` could:

1. Call `diff_dataset(fr=pre_cmd_hexsha, to=None, ...)` with
   `reporting_order='bottom-up'` to discover all changes since
   pre-command, including already-committed ones, recursively through
   the entire hierarchy.

2. For each dataset reported bottom-up:
   - If it has uncommitted changes: save them (via `repo.save_()`
     directly, or a targeted `Save` call).
   - If its `prev_gitshasum` differs from current HEAD (command
     created commits): create a merge commit using `prev_gitshasum`
     as parent1.

3. `git add` of already-committed files is a no-op (worktree matches
   index), so the diff reporting them as 'modified' is harmless — no
   spurious commits are created.

This reuses the existing `_diff_ds` recursion and `fr` translation
machinery with **zero new git plumbing calls** at the top level.
Each subdataset level uses the same `diffstatus()` call that Status
would have made — just with `fr=prev_gitshasum` (pre-command pointer)
instead of `fr='HEAD'` (post-command).

### Why not extend Status/Save with `fr`?

Adding `fr` to Status → `yield_dataset_status` is possible but would
require:

- Adding `fr`/`to` parameters to both Status and Save interfaces
- Reimplementing the subdataset `fr` translation logic that `_diff_ds`
  already has (lines 401-411)
- Changing the Status contract (callers assume `fr='HEAD'`)

Since `_diff_ds` already has this logic, it's simpler to use it
directly in the `cmd_made_commits` path rather than duplicating it
into Status/Save.

### On adjusted branches

Each subdataset on an adjusted branch needs its own
`git annex sync` + `commit-tree` on original branch +
`git annex merge` cycle before the parent can record its submodule
pointer.  This must happen bottom-up, which aligns with the
`order='bottom-up'` traversal from `diff_dataset`.

### Run record placement

Two options:

- **A) Duplicate**: embed the full run record in every subdataset's merge
  commit message (matches the existing docstring claim at `run.py:116-117`
  that the record is "duplicated in each modified (sub)dataset").
- **B) Top-only**: only the top-level merge carries the full run record;
  subdataset merges get a shorter message referencing the parent.

Option A is more self-contained (each subdataset can be understood
independently) and aligns with the existing documented intent.

### Adjusted-branch handling

The current adjusted-branch path (`git annex sync` + `commit-tree` on
original branch + `git annex merge`) must be applied per-subdataset as
well.  Each subdataset on an adjusted branch needs its own sync-merge
cycle before the parent can record its submodule pointer.

## Test scenarios

All tests should use `@known_failure_windows`, `@pytest.mark.ai_generated`.

### 1. Inner commit in a subdataset only

```
ds/
  sub/  ← command creates commit here, nothing in ds itself
```

Run: `datalad run 'cd sub && touch foo && git add foo && git commit -m inner'`

Assert:
- `sub` has a merge commit at HEAD (on corresponding branch if adjusted)
- `ds` has a merge commit whose tree records `sub`'s merge as the
  submodule pointer
- Run info is extractable from both merge commit messages

### 2. Inner commits in both superdataset and subdataset

```
ds/    ← command creates commit here
  sub/ ← and here
```

Run: `datalad run 'touch top && git add top && git commit -m top-inner && cd sub && touch foo && git add foo && git commit -m sub-inner'`

Assert:
- Both `ds` and `sub` have merge commits
- `ds`'s merge records `sub`'s merge commit as submodule pointer
- Both merge commits carry valid run info

### 3. Three-level hierarchy: commit only at leaf

```
ds/
  mid/
    leaf/  ← command creates commit here only
```

Run: `datalad run 'cd mid/leaf && touch foo && git add foo && git commit -m inner'`

Assert:
- `leaf` has a merge commit wrapping the inner commit
- `mid` has a merge commit (or at least records `leaf`'s new pointer)
- `ds` has a merge commit recording the full chain
- Run info extractable at each level

### 4. Adjusted branch (crippled FS) with subdataset commit

Same as scenario 1 but on a vfat / adjusted-branch filesystem.

Assert:
- Merge created on the original branch of each affected dataset
- `git annex sync` succeeds at all levels
- `git annex merge` propagates correctly bottom-up

### 5. No inner commits in subdataset (negative case)

Command creates commits only in the top-level dataset; subdataset is
unmodified.

Assert:
- Only the top-level dataset gets a merge commit
- Subdataset HEAD is unchanged
- No spurious merge commits in subdatasets

## Open questions

- **Partial failures**: if a subdataset merge succeeds but the parent
  merge fails, we need a recovery strategy.  Currently the top-level
  merge is atomic (single `update_ref`), but with a hierarchy there are
  multiple refs to update.
- **`rerun` compatibility**: `datalad rerun` needs to handle merge
  commits at each level of the hierarchy.  The current rerun
  implementation extracts the run record from the commit message, which
  would work with option A (duplicate records).
- **Interaction with `--explicit`**: in explicit mode, `outputs_to_save`
  scoping might need to be per-subdataset.
- **Distinguishing command commits from pre-existing state**: if a
  subdataset was already at a different commit than what the parent
  recorded (dirty submodule pointer before `run`), `ls-tree` comparison
  would show a difference that isn't from the command.  This shouldn't
  happen because `run` checks for a clean tree first, but `--explicit`
  mode skips that check.
