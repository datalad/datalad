### 🐛 Bug Fixes

- `status` no longer reports a file with a tab in its name as deleted, and
  the rest of its name after the tab as added, which also broke `save` and
  `run` on such files; `AnnexRepo.unannex()` now returns such paths (and paths
  with a backslash) unmangled.
  (by [@yarikoptic](https://github.com/yarikoptic))

### 🧪 Tests

- `OBSCURE_FILENAME` includes a tab, and on UTF-8 filesystems again includes
  unicode characters, which it had lacked since 1.3.2.
  (by [@yarikoptic](https://github.com/yarikoptic))
