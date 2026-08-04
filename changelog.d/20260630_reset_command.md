### 🚀 Enhancements and New Features

- New command `datalad reset`: discard local divergence and set a dataset
  (optionally a whole hierarchy) to a target revision, like `git reset --hard`
  but correct on git-annex *adjusted* branches (the default on Windows /
  crippled filesystems). A plain `git reset` there operates on the disposable
  adjusted *view* and leaves the real history untouched, so discarded commits
  can be resurrected by the next sync; `datalad reset` instead resets the
  corresponding branch, reconciles git-annex's `synced/<branch>` ref, and
  regenerates the adjusted view. Supports `--recursive` (each dataset resolves
  the target locally) and `--follow parentds` (subdatasets reset to the
  revisions the superdataset records). Addresses part of
  [#7872](https://github.com/datalad/datalad/issues/7872).
