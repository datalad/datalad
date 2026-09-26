### 🐛 Bug Fixes

- `download-url` and other downloads retry a transfer interrupted by a dropped
  connection, up to `datalad.downloaders.retry` times (default: 5), and on
  failure report how much was stored and, if short, the free space.
  Fixes [ReproNim/containers#169](https://github.com/ReproNim/containers/issues/169) via
  [PR #7930](https://github.com/datalad/datalad/pull/7930)
  (by [@yarikoptic](https://github.com/yarikoptic))

- Error messages no longer repeat the underlying error.
  [PR #7930](https://github.com/datalad/datalad/pull/7930)
  (by [@yarikoptic](https://github.com/yarikoptic))

### 🏠 Internal

- A `DownloadError` message no longer includes that of its `__cause__`.
