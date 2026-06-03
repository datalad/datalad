### 🐛 Bug Fixes

- `update --how=reset` (and `--how=merge`) now work correctly on adjusted
  branches (Windows / crippled filesystems). Three problems are fixed: target
  determination resolved the *adjusted* branch name and built a nonexistent
  `<remote>/adjusted/...` ref (so reset aborted with "Could not determine
  update target"); a reset left `synced/<branch>` at the pre-reset state; and
  `update --how=merge` left behind the `synced/<branch>` it created. The
  leftover/stale `synced/<branch>` could then be merged back by a later
  `git annex sync` (run internally by `save`/`push`), resurrecting commits the
  user had intentionally discarded.
  Fixes [#7772](https://github.com/datalad/datalad/issues/7772) and
  [#7873](https://github.com/datalad/datalad/issues/7873); part of
  [#7872](https://github.com/datalad/datalad/issues/7872).
  (by [@just-meng](https://github.com/just-meng))
