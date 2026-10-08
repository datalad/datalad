### 🐛 Bug Fixes

- `save` and `run` no longer fail with "Argument list too long" for a commit
  message over 128KiB, e.g. a `run` record listing many expanded inputs.
  Fixes [#7611](https://github.com/datalad/datalad/issues/7611)
  (by [@yarikoptic](https://github.com/yarikoptic))
