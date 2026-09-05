### 🚀 Enhancements and New Features

- `add-archive-content` now accepts any number of archives (or keys) in a
  single invocation.  All of them are extracted and added within a single
  commit, which is substantially faster than invoking the command once per
  archive.
  Addresses [#6590](https://github.com/datalad/datalad/issues/6590)
  (by [@yarikoptic](https://github.com/yarikoptic))

### 🐛 Bug Fixes

- `add-archive-content --delete-after` no longer leaves a temporary
  `.datalad*` directory behind whenever it is invoked from a directory other
  than the root of the dataset.
  (by [@yarikoptic](https://github.com/yarikoptic))
