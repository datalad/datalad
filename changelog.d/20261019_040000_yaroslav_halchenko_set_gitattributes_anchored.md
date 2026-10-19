### 🐛 Bug Fixes

- `GitRepo.set_gitattributes()` accepts patterns anchored with a leading `/`,
  e.g. `/*.tsv` for the TSV files at the top of the dataset only, instead of
  rejecting them as paths outside the repository.
  Fixes [#7972](https://github.com/datalad/datalad/issues/7972)
  (by [@yarikoptic](https://github.com/yarikoptic))
