### 🐛 Bug Fixes

- `GitRepo.set_gitattributes()` accepts patterns anchored with a leading `/`,
  e.g. `/*.tsv` for top-level TSV files only, instead of rejecting them as
  outside the repository.  Absolute paths into the repository are anchored
  likewise, rather than matching at any depth.
  Fixes [#7972](https://github.com/datalad/datalad/issues/7972)
  (by [@yarikoptic](https://github.com/yarikoptic))
