# The `--explicit` contract of `datalad run`

## Status: implemented

## Problem

`--explicit` is documented as *"Consider the specification of inputs and
outputs to be explicit. Don't warn if the repository is dirty, and only
save modifications to the listed outputs."*  Three ways in which the
implementation did not keep that promise are addressed here.

1. **Declared inputs were not checked at all**
   ([gh-5312](https://github.com/datalad/datalad/issues/5312),
   [gh-3565](https://github.com/datalad/datalad/issues/3565)).  A command
   could be executed on an input with unsaved modifications, and the
   resulting record would name a state that is nowhere recorded.  A
   `rerun` of that record uses the committed state instead, so the record
   is not reproducible — and nothing said so.

2. **A nested `datalad run` was treated as an undeclared side-effect**
   ([gh-7900](https://github.com/datalad/datalad/issues/7900)).  An outer
   run whose command performs inner runs failed with *"command created
   commits that include files not declared as --output"* unless the outer
   run redeclared every output of every inner run — which for a sweep
   with a runtime-determined cell list is not knowable when the outer
   command line is constructed.

3. **Concurrent runs committed each other's outputs**
   ([gh-7899](https://github.com/datalad/datalad/issues/7899)).  Staging
   and committing use the shared Git index.  With nothing pre-staged,
   `save` committed without a pathspec, so a sibling run's staged output
   was swept into the wrong commit; the sibling then found nothing to
   commit and exited 0 **without any record**.  At higher concurrency the
   same race also surfaced as an `index.lock` failure.

## Solution

### Declared inputs must be saved

Before any worktree preparation — so a rejected run leaves no trace —
`run_command` reports declared inputs whose state is not `clean`.
Untracked content counts only when it *is* a declared input, not when it
merely sits inside a declared directory.

The check is limited to `--explicit`: without it a dirty dataset is
refused outright, which subsumes the check.  It is skipped for
`--assume-ready inputs|both` (the caller asserts the inputs are ready)
and can be relaxed with the configuration variable
`datalad.run.dirty-inputs` (`error` — the default, `warning`, `ignore`).

Only `inputs` are checked, not `extra_inputs`: the latter is an unexposed
implementation detail for wrappers, which have their own notion of what a
usable state is.

### A commit with a run record is not an undeclared side-effect

The `dirty-committed` check no longer looks at all paths a command
committed, but only at those introduced by commits *without* a run
record.  Such commits are the ones the check was written for: content
swept in by a plain `git commit` (or `datalad save`) in the command, with
no provenance of its own.

The `base..head` first-parent chain is walked in a single `git log` call.
Following first parents is what makes a "run merge" (see
`../run-merge/01-subdatasets-merges.md`) account for everything it wraps:
the commits it subsumes live on its second parent.  A subdataset pointer
move is resolved one level deeper — it is accounted for when the
subdataset's own new commits all carry run records.

On an adjusted branch git-annex maintains the branch with commits of its
own (`git-annex adjusted branch`), which sit on the first-parent chain,
carry no run record, and re-render the content of the commits they
follow — under `--unlock`, every file of a `run` shows up in such a
commit's diff.  They are the doing of no command and are skipped
throughout.  `AnnexRepo._save_post()` identifies them by the same
message.

### Concurrency

Three independent measures, in the order in which they take effect:

- **A merge never wraps another run's commits.**  `run` decides that its
  command created commits by comparing HEAD before and after execution.
  A concurrent run committing in that window is indistinguishable from a
  nested one by inspection alone, so a `run` passes its identity to its
  command in the `DATALAD_RUN_ANCESTRY` environment variable, and a run
  that finds itself nested reports the chain it inherited in a
  `DataLad-Run-Ancestry:` commit message trailer.  A commit is attributed
  to this run when it names this run in that trailer, or when it carries
  no run record at all (then it is a plain commit of the command itself).

  A merge has a single second parent, so when a concurrent run's commits
  are interleaved with this command's own, *no* range covers only this
  command — narrowing the range cannot help.  The results are then
  recorded without a merge: the interleaved commits keep the records they
  came with, and no record claims another run's work.  Without this, a
  concurrent run's commits end up on the second parent of an unrelated
  run's merge, and a `rerun` of that record re-executes the other run's
  commands and re-materialises its files.

- **The commit is limited to the declared outputs.**  `save` commits with
  a pathspec whenever content is already staged; with `_partial_commit`
  an `--explicit` run requests the same unconditionally, so a sibling's
  staged output cannot enter this run's commit.

- **The saving phase is serialized.**  An `InterProcessLock` on
  `.git/datalad/run-save.lck` is held across the `Save` call.  This is
  what keeps the two operations that make up saving — staging and
  committing — atomic with respect to another `run`, and it is what
  removes the `index.lock` failures.  Command execution stays parallel:
  the lock is taken after the command has run.

  The lock lives in the *topmost* superdataset, not in the dataset the
  `run` was invoked in.  Saving is recursive, so a `run` in a
  superdataset writes the index of every subdataset underneath it; a lock
  per invoked dataset would leave a superdataset run and a subdataset run
  writing one index while each holds a lock of its own.  It is acquired
  through `try_lock_informatively()`, which reports which process holds
  it rather than stalling silently.  The timeouts are generous and end in
  `proceed_unlocked`: the command has already run at that point, so
  giving up on the lock would mean discarding its results.

## Non-goals / limitations

- **`run` outside of `datalad`.**  A concurrent plain `git commit` from
  another process during command execution is still attributed to the
  command.  Nothing in the commit can tell the two apart.

- **A command that hides its environment.**  Ancestry detection needs
  `DATALAD_RUN_ANCESTRY` to reach a nested `run`.  A command that scrubs
  its environment makes a nested run look like a concurrent one: the
  result is the pre-existing behaviour (a merge commit), not an error.

- **Inputs that appear only after a subdataset is installed.**  The check
  runs before worktree preparation, so an input pattern that matches
  nothing until `run` installs a subdataset for it is not evaluated.
  Reporting it would require preparing the worktree first, which is
  exactly what a rejected run must not do.

- **Saving without `run`.**  `datalad save <path>` in one process can
  still commit what another process staged.  `_partial_commit` is
  available to `Save` callers, but only `run --explicit` sets it, because
  a pathspec commit takes the worktree state of the given paths and
  ignores what is staged for them — a change of semantics that a general
  `save` should not silently adopt.

- **The lock spans the hierarchy, not the dataset.**  Two runs in
  unrelated subdatasets of one superdataset serialize their saving phases
  even though neither writes the other's index.  That is the price of
  covering the recursive save with a single lock; the phase is short, but
  it is worth knowing for a wide hierarchy driven by many parallel runs.
  When the lock cannot be acquired at all (after ~41 minutes of
  contention) saving proceeds unlocked, with a warning, rather than
  discarding the results of a command that has already run.

- **A run interleaved with a concurrent one records no merge.**  Its own
  inner commits then stay on the linear history with the records they
  carry, and the run's own record commit holds only what was left in the
  worktree.  `rerun` over such a range re-executes the inner records and
  the outer one separately, as it did before merge-wrapping existed.
  That is the price of not claiming another run's commits; a sweep that
  wants one merge per sweep should not share its dataset with a
  concurrent outer run.

- **Nothing to commit is not an error.**  An `--explicit` run whose
  command changed nothing still produces no record, and reports
  `save(notneeded)`.  Making that an error was considered
  ([gh-7899](https://github.com/datalad/datalad/issues/7899), suggestion
  2) and rejected: it is the normal outcome of a `rerun` of a
  deterministic command.

## Alternatives considered

- **A narrower `datalad.run.dirty-committed` value** for "commits from a
  nested run are expected", as suggested in gh-7900.  Not needed: a
  commit with a run record is a recorded commit, not dirt, so no
  configuration should be required to accept it.  The configuration
  variable keeps its meaning for genuinely undeclared content.

- **Retrying on `index.lock`** instead of locking.  Rejected in the issue
  itself, and rightly so: it fixes the visible crash and leaves the
  silent misattribution in place.

- **Recording the nesting relation in the `chain` field of the run
  record.**  `chain` is the `rerun` trail (which record this record was
  re-executed from) and overloading it would break that meaning.  The
  nesting relation is reported in the `DataLad-Run-Ancestry:` trailer
  instead, which keeps the record itself — and hence the content-based
  identity of a sidecar record — unchanged.

## Tests

| Test | Purpose |
| --- | --- |
| `test_run_explicit_dirty_inputs` | Modified/untracked inputs, both escape hatches, no false positives |
| `test_rerun_explicit_dirty_input` | The gh-5312 reproducer, for `rerun` |
| `test_run_explicit_nested_run` | Nested runs succeed; a plain commit of an undeclared file still fails |
| `test_run_explicit_nested_run_adjusted` | The same on an adjusted branch, where git-annex commits of its own |
| `test_run_explicit_concurrent` | Every concurrent run has a record, and none claims another's output |
| `test_run_explicit_concurrent_subdataset` | One lock governs the hierarchy: a super run and a sub run do not race |
| `test_run_explicit_no_merge_of_concurrent_commits` | No merge is made when another run's commits are interleaved |
| `test_run_explicit_dirty_committed` | Unchanged: undeclared content from a plain commit is still refused |
