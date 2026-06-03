### 🐛 Bug Fixes

- `update --how=merge` on an adjusted branch now removes the `synced/<branch>`
  ref it creates (matching `AnnexRepo.localsync`), so a later `git annex sync`
  cannot merge the zombie back and resurrect discarded commits.
  Re [#7772](https://github.com/datalad/datalad/issues/7772).
  (by [@just-meng](https://github.com/just-meng))
