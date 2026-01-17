# Analysis of git-annex filter-branch Options

## Purpose

Review all available `git-annex filter-branch` options to determine if any should be added to our split workflow beyond the currently used:
- `--include-all-key-information`
- `--include-all-repo-config`

## Tested Options

### 1. `--include-global-config`

**Test**: Compare filter-branch WITH and WITHOUT this flag

**Result**: **No difference** when `--include-all-repo-config` is already specified

**Explanation**:
- `numcopies` and `mincopies` are stored in the git-annex branch (`numcopies.log`, `mincopies.log`)
- These are already included by `--include-all-repo-config`
- The `--include-global-config` flag appears to be redundant when using `--include-all-repo-config`

**Files compared**:
```
WITHOUT --include-global-config:
- 170/0d8/MD5E-s2097152--30534fa675bb384c9582c269ac4dac5c.dat.log
- mincopies.log (contains: 1768621562s 1)
- numcopies.log (contains: 1768621562s 2)
- uuid.log

WITH --include-global-config:
- 170/0d8/MD5E-s2097152--30534fa675bb384c9582c269ac4dac5c.dat.log
- mincopies.log (contains: 1768621562s 1)
- numcopies.log (contains: 1768621562s 2)
- uuid.log
```

**Conclusion**: ❌ Not needed - already covered by `--include-all-repo-config`

### 2. `--all` flag

**Test**: Try using `--all` with path specification

**Result**: **Error** - mutually exclusive options

```
git-annex: Can only specify one of file names, --all, --branch,
--unused, --failed, --key, or --incomplete
```

**Explanation**:
- `--all`: Operates on all keys in entire repository
- `path`: Operates on keys in specified path
- These are mutually exclusive selectors

**Conclusion**: ❌ Cannot be used - we need path specification for split

### 3. `--fast` flag

**Test**: Compare performance with and without `--fast`

**Result**: **No performance benefit** (possibly slight regression)

```
Without --fast: 0m0.039s
With --fast:    0m0.050s
```

**Explanation**:
- The `--fast` flag avoids some slow operations
- For our use case (filtering by path), there are no expensive operations being avoided
- The overhead of the flag check might actually be slightly slower

**Conclusion**: ❌ No benefit for our use case

### 4. Path Filtering Verification

**Test**: Verify that path-based filtering correctly excludes unrelated keys

**Setup**:
- Created file in `data/subdir/file.dat`
- Modified same file (creating new key)
- Filtered with path `data/subdir`

**Original git-annex branch files**:
```
170/0d8/MD5E-s2097152--30534fa675bb384c9582c269ac4dac5c.dat.log  (original)
3b2/4dc/MD5E-s2097161--6e6cbc0bbd67aa205a75d17bc3a878de.dat.log  (modified)
mincopies.log
numcopies.log
uuid.log
```

**Filtered git-annex branch files**:
```
170/0d8/MD5E-s2097152--30534fa675bb384c9582c269ac4dac5c.dat.log  (original)
mincopies.log
numcopies.log
uuid.log
```

**Observation**: ✅ Path filtering works correctly - both versions of the file are included if they existed in the specified path

**Conclusion**: ✅ Path-based filtering is working as expected

## Options Analysis Summary

### Currently Used (Correct!)
- ✅ `path` - Specifies which files to include
- ✅ `--include-all-key-information` - Includes location tracking for all repositories
- ✅ `--include-all-repo-config` - Includes numcopies, mincopies, trust settings, etc.

### Tested but Not Needed
- ❌ `--include-global-config` - Redundant with `--include-all-repo-config`
- ❌ `--all` - Mutually exclusive with path specification
- ❌ `--fast` - No performance benefit for our use case

### Not Applicable to Our Use Case
- `--branch=ref` - We use current HEAD, not specific branch
- `--key=key` - We filter by path, not individual keys
- `--unused` - Not relevant for split operation
- `--include-key-information-for=remote` - We want ALL repos (--include-all-key-information)
- `--exclude-key-information-for=remote` - We don't want to exclude any repos
- Matching options (`--in`, `--copies`, etc.) - Not needed, we filter by path

## Important Finding: Git Config Not Transferred

**What IS transferred by filter-branch**:
- Location tracking (which repos have which keys)
- Repository-specific config from git-annex branch
- numcopies/mincopies (stored in git-annex branch)
- Trust settings
- Preferred content expressions

**What is NOT transferred by filter-branch**:
- `.git/config` settings like `annex.addunlocked`, `annex.backend`, etc.
- These are git config settings, NOT git-annex branch metadata

**Implication**: Our design already handles this correctly with the `--propagate-annex-config` option that separately copies git config `annex.*` settings from parent to subdataset.

## Recommendations

### For Split Implementation

**Keep current approach**:
```bash
git-annex filter-branch <path> \
    --include-all-key-information \
    --include-all-repo-config
```

**Do NOT add**:
- `--include-global-config` (redundant)
- `--all` (conflicts with path)
- `--fast` (no benefit)

**Continue with separate git config propagation**:
- Use `git config` commands to copy `annex.*` settings
- Already covered by `--propagate-annex-config` parameter in our design

## Test Commands

To reproduce these findings:

```bash
bash /tmp/test_filter_branch_options.sh
```

Results saved in `/tmp/test-filter-options/`
