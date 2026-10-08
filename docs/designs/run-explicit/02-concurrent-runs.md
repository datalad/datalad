# Concurrent `datalad run` in one dataset

## Status: implemented

## Problem

The use case is N parallel `datalad run --explicit` in a single dataset,
without giving each run a worktree or a branch of its own -- a sweep
where every cell writes its own declared output into the same tree.

Staging and committing go through the shared Git index, so the runs raced
([gh-7899](https://github.com/datalad/datalad/issues/7899)):

- With nothing pre-staged, `save` committed **without a pathspec**, so a
  sibling run's staged output was swept into the wrong commit.  The
  sibling then found nothing left to commit and exited 0 **without any
  record** -- the loss is silent.

- `run` decides that its command created commits by comparing HEAD before
  and after execution.  A sibling committing in that window is
  indistinguishable from a nested run by inspection alone, so a
  concurrent run's commits were wrapped into an unrelated run's merge
  commit.  A `rerun` of that record then re-executes the other run's
  command.

- At higher concurrency the same race also surfaced as an outright
  `index.lock` failure.

Measured on the issue's reproducer at N=8: 1-2 records of 8, outputs
attributed to the wrong command, plus `index.lock` crashes.  After the
changes below: 8 of 8, each commit containing exactly its own declared
output, no crashes (independently reproduced up to N=64).

## Solution

Three independent measures, in the order in which they take effect:

- **Only own commits are wrapped in a merge.**  A `run` passes its
  identity to its command in the `DATALAD_RUN_ANCESTRY` environment
  variable, and a run that finds itself nested reports the chain it
  inherited in a `DataLad-Run-Ancestry:` commit message trailer.  A
  commit is attributed to this run when it names this run in that
  trailer, or when it carries no run record at all (then it is a plain
  commit of the command itself).  Since a merge has a single second
  parent, once a sibling's commits are interleaved with this command's
  own *no* range covers only this command; the results are then recorded
  **without** a merge, so the interleaved commits keep the records they
  came with.  The run record itself is unchanged, so a sidecar record
  keeps its content-based identity.

- **The commit is limited to the declared outputs.**  `save` commits with
  a pathspec whenever content is already staged; with the new private
  `_partial_commit` an `--explicit` run requests the same
  unconditionally, so a sibling's staged output cannot enter this run's
  commit.

- **The saving phase is serialized.**  An `InterProcessLock` on
  `.git/datalad/run-save.lck` is held across the `Save` call, which keeps
  staging and committing atomic with respect to another `run` and removes
  the `index.lock` failures.  The lock is taken on the **topmost
  superdataset**, not on the invoked dataset: saving is recursive, so a
  run in a superdataset writes the index of every subdataset underneath
  it, and a lock per invoked dataset would leave a super run and a sub
  run writing one index while each holds a lock of its own.  Command
  execution stays parallel -- the lock is taken after the command has
  run, via `try_lock_informatively()`, so a wait reports who holds it.

  If the lock cannot be acquired within the timeouts, `run` proceeds
  unlocked and warns, rather than discarding the results of a command
  that has already run.  Failing to *create* the lock directory is not
  caught: the `save` that follows writes the same `.git` and would fail
  anyway, so swallowing that error would only defer the failure and
  discard its cause.

## Non-goals / limitations

- **`run` outside of `datalad`.**  A concurrent plain `git commit` from
  another process during command execution is still attributed to the
  command.  Nothing in the commit can tell the two apart.

- **A command that hides its environment.**  Ancestry detection needs
  `DATALAD_RUN_ANCESTRY` to reach a nested `run`.  A command that scrubs
  its environment makes a nested run look like a concurrent one: the
  result is the pre-existing behaviour (a merge commit), not an error.

- **Saving without `run`.**  `datalad save <path>` in one process can
  still commit what another process staged.  `_partial_commit` is
  available to `Save` callers, but only `run --explicit` sets it, because
  a pathspec commit takes the worktree state of the given paths and
  ignores what is staged for them -- a change of semantics that a general
  `save` should not silently adopt.

- **Nothing to commit is not an error.**  An `--explicit` run whose
  command changed nothing still produces no record, and reports
  `save(notneeded)`.  Making that an error was considered (gh-7899,
  suggestion 2) and rejected: it is the normal outcome of a `rerun` of a
  deterministic command.

## Alternatives considered

- **Retrying on `index.lock`** instead of locking.  Rejected in the issue
  itself, and rightly so: it fixes the visible crash and leaves the
  silent misattribution in place.

- **Recording the nesting relation in the `chain` field of the run
  record.**  `chain` is the `rerun` trail (which record this record was
  re-executed from) and overloading it would break that meaning.  The
  nesting relation is reported in the `DataLad-Run-Ancestry:` trailer
  instead, which keeps the record -- and hence the content-based identity
  of a sidecar record -- unchanged.

- **Locking each invoked dataset** rather than the topmost superdataset.
  Leaves a super run and a sub run writing the same index while each
  holds a lock of its own; see above.

## Tests

| Test | Purpose |
| --- | --- |
| `test_run_explicit_concurrent` | 3 real `run` processes: every one has a record, and none claims another's output |
| `test_run_explicit_concurrent_subdataset` | The same in a subdataset, where the lock is taken on the superdataset |
| `test_run_explicit_no_merge_of_concurrent_commits` | A sibling's commits are not wrapped into this run's merge |
| `test_save_partial_commit_shrinking_annex` | Unchanged: a pre-staged partial commit still behaves as before |
