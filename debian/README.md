# Procedures & History


- Debian packaging resides within the same upstream source repo
  (http://github.com/datalad/datalad)
- Packaging branch *used to* be based on upstream branches (maint/master)
  and were just merging releases, but that procedures were changed
  to rely on released sources. So:
- Upstream releases (typically off `maint` branch) automatically uploaded
  to pypi
- `uscan` would download most recent release on pypi
- Branch `upstream` - imported sources from up pypi via 
  `gbp import-orig --pristine-tar`
- Branch `debian` - merges `upstream`
- `quilt` is used to manage patchset under `debian/patches`, containing
  - some debian specifics
  - post-release fixes (typically patches created/named by `git format-patch`)
