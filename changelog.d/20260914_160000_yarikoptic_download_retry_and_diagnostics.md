### 🚀 Enhancements and New Features

- Downloads (`download-url`, and every other use of datalad's downloaders)
  now retry a transfer which was interrupted by a lost connection, a reset,
  or a read timeout, instead of aborting the whole command over a single
  dropped connection.  A retry restarts the download from the beginning; how
  many are made is controlled by the new `datalad.downloaders.retry`
  configuration option (default: 5), which also governs the pre-existing
  retries of incomplete transfers and of 5xx server responses.  Retries are
  now also announced (at `info` level) and backed off, rather than being
  attempted silently and immediately.
  Reported in
  [ReproNim/containers#169](https://github.com/ReproNim/containers/issues/169)

- A failed download now reports how far it got and how much room was left for
  it on the target file system, and running out of space is called out as
  such (and not retried).  A download which cannot possibly fit is warned
  about before it starts.  Without that, a file system filling up is hard to
  tell apart from a server truncating the response -- both just break off at
  a different offset every time.

### 🐛 Bug Fixes

- Download failures are no longer reported several times over within a single
  error message.  `DownloadError` used to render the underlying exception into
  its own message *and* carry it as its cause, so every renderer of the
  `-caused by-` chain spelled the same `IncompleteRead` out twice, on top of
  the copy logged separately at `error` level.  The message now only states
  the context, and a cause which the wrapping exception has already rendered
  into its own message (as urllib3's `ProtocolError` does) is not repeated.
