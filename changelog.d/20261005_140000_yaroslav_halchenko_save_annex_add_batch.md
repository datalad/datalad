### 🐛 Bug Fixes

- `save` hands new files to a single `git annex add --batch` via stdin rather
  than on command lines, which failed for many files under tight resource
  limits, and started `git annex add` anew for every chunk of a long file list.
  Fixes [#7568](https://github.com/datalad/datalad/issues/7568) and
  [#5721](https://github.com/datalad/datalad/issues/5721)
  (by [@yarikoptic](https://github.com/yarikoptic))
