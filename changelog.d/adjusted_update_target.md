### 🐛 Bug Fixes

- `update --how=reset` (and `--how=merge`) now resolves the corresponding branch
  when determining the update target on adjusted branches (Windows / crippled
  filesystems). Previously the adjusted branch name was used to build a
  nonexistent `<remote>/adjusted/...` ref, so the update aborted with
  "Could not determine update target".
  Fixes [#7873](https://github.com/datalad/datalad/issues/7873).
  (by [@just-meng](https://github.com/just-meng))
