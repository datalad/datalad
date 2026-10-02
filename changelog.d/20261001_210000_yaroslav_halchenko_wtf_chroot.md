### 🐛 Bug Fixes

- `wtf` no longer warns, and `test_wtf` no longer fails, when filesystem
  details cannot be determined, e.g. in a chroot during package builds.
  Fixes [#7950](https://github.com/datalad/datalad/issues/7950)
  (by [@yarikoptic](https://github.com/yarikoptic))
