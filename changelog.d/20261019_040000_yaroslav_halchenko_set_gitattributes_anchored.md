### 💥 Breaking Changes

- `GitRepo.set_gitattributes()` writes patterns as given: absolute paths, and
  paths starting with `./` or `../`, are no longer converted into patterns
  relative to the directory of the `.gitattributes` file.  Pass such patterns
  instead.
  (by [@yarikoptic](https://github.com/yarikoptic))

### 🐛 Bug Fixes

- `GitRepo.set_gitattributes()` accepts patterns anchored with a leading `/`,
  e.g. `/*.tsv` for top-level TSV files only, instead of rejecting them as
  outside the repository.
  Fixes [#7972](https://github.com/datalad/datalad/issues/7972)
  (by [@yarikoptic](https://github.com/yarikoptic))
