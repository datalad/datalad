### 🚀 Enhancements and New Features

- New command `datalad reset`: like `git reset --hard`, but also correct on
  git-annex adjusted branches (Windows / crippled filesystems), where it resets
  the corresponding branch and regenerates the adjusted view. Supports
  `--recursive` and `--follow parentds`. Part of
  [#7872](https://github.com/datalad/datalad/issues/7872).
