### 🐛 Bug Fixes

- `update --how=reset` on an adjusted branch now reconciles git-annex's
  `synced/<branch>` ref, so a discarded commit is not resurrected by the next
  `git annex sync` (run internally by `save`/`push`).
  Re [#7772](https://github.com/datalad/datalad/issues/7772).
  (by [@just-meng](https://github.com/just-meng))
