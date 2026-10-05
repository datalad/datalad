### 🐛 Bug Fixes

- `datalad run` no longer fails with "File unknown to git" when an output is an untracked directory containing only empty subdirectories (as e.g. snakemake creates them).  Fixes [#7955](https://github.com/datalad/datalad/issues/7955) (by [@just-meng](https://github.com/just-meng))
