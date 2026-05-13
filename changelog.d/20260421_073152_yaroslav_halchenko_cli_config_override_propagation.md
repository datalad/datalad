### 🐛 Bug Fixes

- Propagate `datalad -c key=value` CLI config overrides and `DATALAD_*`
  environment variables to subprocesses via Git's native
  environment-based configuration mechanism (`GIT_CONFIG_COUNT` /
  `GIT_CONFIG_KEY_N` / `GIT_CONFIG_VALUE_N`). Previously the overrides
  were only stored in `datalad.cfg.overrides` and were invisible to
  subprocesses spawned by commands like `datalad run`, so e.g.
  `datalad -c user.name=Test run git config user.name` did not return
  the override. Adapted near-verbatim from the `cli_configoverrides`
  patch in
  [datalad-next](https://github.com/datalad/datalad-next/blob/904ca6e/datalad_next/patches/cli_configoverrides.py),
  with its `get_gitconfig_items_from_env` /
  `set_gitconfig_items_in_env` helpers also added under
  `datalad.config`.
  Fixes [#4119](https://github.com/datalad/datalad/issues/4119)
  (by [@yarikoptic](https://github.com/yarikoptic))
