### 🚀 Enhancements and New Features

- `datalad run` now wraps command-created commits as merge commits,
  preserving linear first-parent history while keeping the full
  provenance record.  This works across subdataset hierarchies:
  each dataset that gained intermediate commits gets its own merge,
  and merge need propagates bottom-up.  A new `datalad save --from`
  (`fr=`) parameter makes this independently usable outside of `run`.
  [PR #7821](https://github.com/datalad/datalad/pull/7821)
  (by [@yarikoptic](https://github.com/yarikoptic))
