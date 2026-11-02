### 🐛 Bug Fixes

- `update --how=reset` no longer refuses to reset a dataset because of changes
  in its subdatasets, which the reset leaves untouched, and with `--recursive`
  it no longer saves the dataset to a new commit past its reset target.
  Part of [#7949](https://github.com/datalad/datalad/issues/7949)
  (by [@yarikoptic](https://github.com/yarikoptic))
