### 🚀 Enhancements and New Features

- `push` gained a `--set-upstream`/`-u` option, analogous to
  `git push -u`: after a successful push, it configures the current
  branch to track the given sibling. Since "upstream" only makes sense
  relative to one specific sibling, it requires `--to` to be given and
  errors out otherwise.
  Fixes [#7917](https://github.com/datalad/datalad/issues/7917)
  (by [@yarikoptic](https://github.com/yarikoptic))
