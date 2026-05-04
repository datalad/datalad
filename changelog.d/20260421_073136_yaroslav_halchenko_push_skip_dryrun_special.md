### 🏎 Performance

- `datalad push` no longer runs a pointless `git push --dry-run` and
  refspec computation when the target is a git-annex special remote
  (e.g. WebDAV, S3, directory) that has no git URL. This was wasteful
  at best and could cause errors or significant slowdowns for remotes
  like WebDAV. The `target_is_git_remote` check is now performed before
  the dry-run block and guards the entire dry-run + refspec computation.
  Ported from the `push_optimize` patch in
  [datalad-next](https://github.com/datalad/datalad-next).
  Fixes [#6657](https://github.com/datalad/datalad/issues/6657)
  (by [@yarikoptic](https://github.com/yarikoptic))
