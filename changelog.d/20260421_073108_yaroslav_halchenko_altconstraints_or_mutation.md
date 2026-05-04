### 🐛 Bug Fixes

- Fix `AltConstraints.__or__()` and `Constraints.__and__()` mutating
  their left-hand operand in place and returning `self`. This caused
  silent side effects when constraint objects defined at module level
  (e.g. `reckless_opt`) were reused across multiple `|` or `&` chains.
  Both operators now return a new instance, preserving the original.
  Identified via the constraint system overhaul in
  [datalad-next](https://github.com/datalad/datalad-next).
  Fixes [#7164](https://github.com/datalad/datalad/issues/7164)
  (by [@yarikoptic](https://github.com/yarikoptic))
