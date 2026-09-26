### 🐛 Bug Fixes

- Open-file detection (used by e.g. `save`) compared its own UID via
  `os.getuid()` against `psutil`-reported UIDs of other processes.  Under
  UID-faking wrappers such as `fakeroot` (used during Debian package
  builds), the two disagreed, so every process -- including our own --
  was filtered out and no open file was ever detected.
  [PR #7941](https://github.com/datalad/datalad/pull/7941)
  (by [@yarikoptic](https://github.com/yarikoptic))
