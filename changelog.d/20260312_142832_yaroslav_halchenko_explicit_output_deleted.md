### 🐛 Bug Fixes

- Fix `run --explicit --output` failing to commit file deletions.
  When a command deleted files specified in `--output`, the deletions
  were left unstaged because post-command globbing only matched
  files still present on disk.
  Fixes [#7822](https://github.com/datalad/datalad/issues/7822) via
  [PR #7823](https://github.com/datalad/datalad/pull/7823)
  (by [@yarikoptic](https://github.com/yarikoptic))
