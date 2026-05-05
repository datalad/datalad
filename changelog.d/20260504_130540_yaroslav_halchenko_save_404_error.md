### 🐛 Bug Fixes

- `save` now emits an `error` result record for each path argument that
  does not match any file known to git and does not exist on the
  filesystem, instead of silently exiting with success. This restores
  behavior in line with `git add` / `git commit` and the now-removed
  `datalad add`. Mixed invocations (some matching paths, some not) save
  the matching paths and still exit non-zero.
  Fixes [#7840](https://github.com/datalad/datalad/issues/7840) and
  [#3844](https://github.com/datalad/datalad/issues/3844)
  (by [@yarikoptic](https://github.com/yarikoptic))
