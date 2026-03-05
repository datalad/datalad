### 🐛 Bug Fixes

- Avoid use of `return` in a `finally` block, which raises a `SyntaxWarning` as of Python 3.14.
  Fixes [#7817](https://github.com/datalad/datalad/issues/7817) via
  [PR #7818](https://github.com/datalad/datalad/pull/7818)
  (by [@effigies](https://github.com/effigies))
