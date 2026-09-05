### 🚀 Enhancements and New Features

- `add-archive-content` now takes any number of archives (or keys) in a
  single invocation.  Their content is extracted and added within a single
  commit, reusing the same batched git-annex processes, which is
  substantially faster than invoking the command once per archive.  All
  given archives are vetted before any of them is acted on, and original
  archives (`--delete`) are removed only once all of them were added.
  Addresses [#6590](https://github.com/datalad/datalad/issues/6590)
  (by [@yarikoptic](https://github.com/yarikoptic))

- `add-archive-content` now yields a result record for every given archive,
  identifying it via `path` and `type='file'` (or `key` and `type='key'`
  with `--key`), in addition to the dataset-level record it yielded before.
  Result records about archives which can not be used now identify the
  archive as well, instead of the dataset.  Two conditions which raised a
  `RuntimeError` before -- the archive not being under annex control, and
  its content not being available locally -- are now reported as
  `impossible` result records.
  (by [@yarikoptic](https://github.com/yarikoptic))

### 🐛 Bug Fixes

- `add-archive-content --delete-after` failed (`git rm` of a non-existing
  path, followed by `OSError: Directory not empty`) and left a temporary
  `.datalad*` directory behind, whenever it was invoked from a directory
  other than the root of the dataset and the dataset was not given as a
  `Dataset` instance.
  (by [@yarikoptic](https://github.com/yarikoptic))
