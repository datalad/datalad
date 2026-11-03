# The `--explicit` contract of `datalad run`

## Status: implemented

## Problem

`--explicit` is documented as *"Consider the specification of inputs and
outputs to be explicit. Don't warn if the repository is dirty, and only
save modifications to the listed outputs."*  Two ways in which the
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

## Solution

### Declared inputs must be saved

Before any worktree preparation — so a rejected run leaves no trace —
`run_command` reports declared inputs whose state is not `clean`.
Untracked content counts only when it *is* a declared input, not when it
merely sits inside a declared directory.

The check is limited to `--explicit`: without it a dirty dataset is
refused outright, which subsumes the check.  Its only escape hatch is
`--assume-ready inputs|both`, with which the caller asserts that the
inputs are ready; no configuration variable relaxes it, because
`--assume-ready` already covers the case per call and a persistent
"ignore" setting would silently reintroduce the very records this check
exists to prevent.

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

## Non-goals / limitations

- **Inputs that appear only after a subdataset is installed.**  The check
  runs before worktree preparation, so an input pattern that matches
  nothing until `run` installs a subdataset for it is not evaluated.
  Reporting it would require preparing the worktree first, which is
  exactly what a rejected run must not do.

## Alternatives considered

- **A narrower `datalad.run.dirty-committed` value** for "commits from a
  nested run are expected", as suggested in gh-7900.  Not needed: a
  commit with a run record is a recorded commit, not dirt, so no
  configuration should be required to accept it.  The configuration
  variable keeps its meaning for genuinely undeclared content.

## Tests

| Test | Purpose |
| --- | --- |
| `test_run_explicit_dirty_inputs` | Modified/untracked inputs, the `--assume-ready` escape hatch, no false positives |
| `test_rerun_explicit_dirty_input` | The gh-5312 reproducer, for `rerun` |
| `test_run_explicit_nested_run` | Nested runs succeed; a plain commit of an undeclared file still fails |
| `test_run_explicit_nested_run_adjusted` | The same on an adjusted branch, where git-annex commits of its own |
| `test_run_explicit_nested_run_in_subdataset` | A subdataset pointer move judged by the subdataset's own commits |
| `test_rerun_explicit_dirty_input_stops_range` | A refused input ends a `--since=` replay instead of only being reported |
| `test_run_explicit_dirty_committed` | Unchanged: undeclared content from a plain commit is still refused |
