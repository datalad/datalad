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

- `add-archive-content` gained `--overwrite-prior-check`
  (`error` (default), `stats`, `ignore`), which guards the content one
  archive added against the archives which follow it in the same
  invocation.  Discarding it is only possible with
  `--existing=overwrite`, and now leads to an error unless permitted;
  `stats` permits it and reports the affected files as
  `overwritten prior` in the statistics.  Files with identical content,
  and the `--existing` suffix modes (which rename the incoming file
  rather than discard anything), are never reported.
  (by [@yarikoptic](https://github.com/yarikoptic))

### 🐛 Bug Fixes

- `add-archive-content --delete-after` failed (`git rm` of a non-existing
  path, followed by `OSError: Directory not empty`) and left a temporary
  `.datalad*` directory behind, whenever it was invoked from a directory
  other than the root of the dataset and the dataset was not given as a
  `Dataset` instance.
  (by [@yarikoptic](https://github.com/yarikoptic))
