### 🐛 Bug Fixes

- `run`/`rerun` with `--explicit` now refuse to execute a command when a
  declared input has unsaved modifications, instead of recording an input
  state that is nowhere recorded.  Use `--assume-ready=inputs` or the new
  configuration variable `datalad.run.dirty-inputs` to proceed regardless.
  Fixes [#5312](https://github.com/datalad/datalad/issues/5312) and
  [#3565](https://github.com/datalad/datalad/issues/3565)
- `run --explicit` no longer reports commits made by a nested `datalad run`
  as files "not declared as --output": they carry a complete run record of
  their own, so an outer run only has to declare the outputs it produces
  itself.
  Fixes [#7900](https://github.com/datalad/datalad/issues/7900)
- Concurrent `run` invocations in one dataset no longer commit each other's
  outputs, lose run records, or fail on `index.lock`: the saving phase is
  serialized, an `--explicit` commit is limited to the declared outputs, and
  only a run's own commits are wrapped into its merge commit.
  Fixes [#7899](https://github.com/datalad/datalad/issues/7899)
