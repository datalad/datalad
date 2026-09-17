### 🚀 Enhancements and New Features

- Downloads now retry a transfer interrupted by a lost connection instead of
  aborting the command, `datalad.downloaders.retry` (default: 5) times.  A
  failed download also reports how far it got and how much room was left on
  the target file system, so a filling disk is not mistaken for a flaky
  server.  Reported in
  [ReproNim/containers#169](https://github.com/ReproNim/containers/issues/169)
  (by [@yarikoptic](https://github.com/yarikoptic))

### 🐛 Bug Fixes

- A download failure is no longer reported several times over within a single
  error message.
  (by [@yarikoptic](https://github.com/yarikoptic))

### 💥 Breaking Changes

- `DownloadError` from the downloaders no longer renders the underlying
  exception into its own message; it is attached as the `__cause__` instead.
  Code matching on the text of the underlying failure has to consult
  `exc.__cause__`.
  (by [@yarikoptic](https://github.com/yarikoptic))
