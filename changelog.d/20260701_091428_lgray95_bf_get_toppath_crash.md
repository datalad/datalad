### 🐛 Bug Fixes

- `get_toppath()` now returns `None` instead of crashing with `TypeError` when
  called on a path whose existence can't be verified (e.g. a broken symlink or
  a nonexistent directory).  Discovered while investigating
  [#7882](https://github.com/datalad/datalad/issues/7882).
  (by [@LiamDGray](https://github.com/LiamDGray))
