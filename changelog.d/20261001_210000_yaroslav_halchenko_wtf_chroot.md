### 🐛 Bug Fixes

- `wtf` no longer warns about failing to determine filesystem types when a
  path's mountpoint is not among the physical partitions, e.g. in a chroot
  used for package builds; it now considers all mounts before giving up.
  `test_wtf` no longer fails in such environments.
  Fixes [#7950](https://github.com/datalad/datalad/issues/7950)
  (by [@yarikoptic](https://github.com/yarikoptic))
