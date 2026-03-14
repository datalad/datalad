### 🐛 Bug Fixes

- Suppress `RequestsDependencyWarning` emitted by `requests` 2.32.x
  when `chardet>=6` is installed.  The warning was purely cosmetic
  (HTTP functionality is unaffected) but appeared on stderr for every
  datalad command.
  Fixes [#7825](https://github.com/datalad/datalad/issues/7825)
  (by [@yarikoptic](https://github.com/yarikoptic))
