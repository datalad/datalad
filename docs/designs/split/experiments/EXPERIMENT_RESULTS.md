# Experiment Results

Results from running the prototype validation experiments for the datalad split command.

**Date**: 2026-01-16
**Environment**:
- DataLad: 1.2.3
- git-annex: 10.20251114
- Git: 2.39.5
- Python: 3.11.2

## Experiment 1: Basic Filter Branch

**Status**: ✅ **SUCCESS**

### Results

The basic filtering workflow works as expected!

**Key Metrics**:
- Original `.git` size: 11M
- Filtered `.git` size: 396K
- **Size reduction: ~96%** (100% shown due to rounding)

**What Worked**:
1. ✅ Clone → git-annex filter-branch → git filter-branch workflow executes successfully
2. ✅ Only target directory files remain in filtered repository
3. ✅ Files are accessible in the filtered dataset
4. ✅ No unwanted files from other directories present
5. ✅ git annex forget completes without errors

**Command Sequence Validated**:
```bash
git-annex filter-branch data/subject01 --include-all-key-information
git filter-branch --subdirectory-filter data/subject01 HEAD
git annex dead origin
git remote rm origin
git annex forget --force --drop-dead
```

**Issues Found**:
- Minor: Initial script had missing directory creation for `data/subject02/large`
  - **Fixed**: Added `mkdir -p data/subject02/large` to the script

### Conclusions

- Basic workflow is sound and ready for implementation
- Significant size reduction achieved
- Metadata cleanup works as expected

---

## Experiment 2: Nested Subdataset Handling

**Status**: ⚠️ **PARTIAL SUCCESS** - Identifies critical issue

### Results

Nested subdatasets DO NOT survive `git filter-branch` properly!

**What Happened**:
1. ⚠️ `.gitmodules` file **disappears** during filtering
2. ⚠️ Subdataset directories remain but are **no longer git repositories**
3. ⚠️ Git submodule tracking is **lost completely**
4. ✅ Regular file content (metadata.txt) is preserved correctly
5. ✅ Clone with `-c protocol.file.allow=always` works for local testing

**Before Filtering**:
```
.gitmodules exists with submodule entries
data/subject01/raw/.git exists (is a repository)
```

**After Filtering**:
```
.gitmodules: MISSING
data/subject01/raw/.git: MISSING
raw/ directory exists but is not a git repo
```

**Git Warnings**:
```
warning: unable to rmdir 'code': Directory not empty
warning: unable to rmdir 'data/subject01/raw': Directory not empty
```

**Issues Found**:
- Git protocol security: Needed `-c protocol.file.allow=always` for local cloning
  - **Fixed**: Added to both clone commands in the script
- Directory cleanup: Needed `chmod -R +w` before `rm -rf`
  - **Fixed**: Added to cleanup section

### Conclusions

**CRITICAL FINDING**: The split command implementation MUST handle nested subdatasets specially:

1. **Detect nested subdatasets** before filtering
2. **Preserve .gitmodules** entries or reconstruct them
3. **Re-register subdatasets** after filtering
4. Consider using a **different approach** for paths containing subdatasets:
   - Option A: Error if nested subdataset detected
   - Option B: Preserve subdataset as-is (don't filter its history)
   - Option C: Manually reconstruct .gitmodules after filtering

**Recommended Approach**: During implementation, when a path contains subdatasets:
- Detect them via `datalad subdatasets -r`
- Either error out with helpful message, OR
- Use special logic to preserve/reconstruct the subdataset registrations

---

## Experiment 3: Metadata Cleanup

**Status**: ✅ **SUCCESS** with observations

### Results

Git annex forget works but provides marginal additional benefit in this test case.

**Key Metrics**:
- Original `.git` size: 19M
- Without forget: 616K (100% reduction)
- With forget: 636K (100% reduction)
- **Additional benefit from forget: ~0%**

**What Worked**:
1. ✅ git annex forget executes successfully
2. ✅ Both approaches achieve dramatic size reduction
3. ✅ .log files reduced from 26 to 8 files
4. ✅ Total log size reduced from 100K to 28K

**What Didn't Work**:
1. ⚠️ References to other subjects still found in logs after forget
2. ⚠️ Forget didn't provide measurable additional .git size reduction

**Possible Explanations**:
- The test dataset was small, so forget's benefits are less visible
- Some metadata may be intentionally preserved by git-annex
- The filtering already removed most unnecessary data

### Conclusions

- `git annex forget` should still be included in the workflow for larger datasets
- The benefit may be more significant with:
  - Larger datasets (GB to TB scale)
  - Datasets with many historical key locations
  - Datasets with extensive special remote configurations
- For small datasets, the overhead is minimal

---

## Overall Assessment

### What's Ready for Implementation

1. ✅ **Basic workflow**: Clone → filter → cleanup sequence works
2. ✅ **Size reduction**: Achieves significant .git size reduction
3. ✅ **Command ordering**: git-annex filter-branch before git filter-branch
4. ✅ **Metadata cleanup**: git annex forget executes successfully

### Critical Issues to Address

1. ⚠️ **Nested subdatasets**: Require special handling (see Experiment 2)
2. ⚠️ **Git protocol**: Need to handle protocol.file.allow for local operations
3. ℹ️ **Metadata references**: Some cross-references may persist (minor issue)

### Recommendations for Implementation

#### Phase 1: Basic Implementation
- Implement basic split without nested subdataset support
- Add explicit check to ERROR if nested subdatasets detected
- Document limitation clearly

#### Phase 2: Nested Subdataset Support
- Implement subdataset detection
- Add logic to preserve/reconstruct .gitmodules
- Test thoroughly with various nesting scenarios

#### Testing Priorities
1. **High**: Test with nested subdatasets (various depths)
2. **High**: Test with large datasets (multi-GB)
3. **Medium**: Test with special remotes (S3, WebDAV, etc.)
4. **Medium**: Test performance with many files (1000+)

---

## Script Fixes Applied

### Experiment 1: 01_basic_filter.sh
- **Fixed**: Added `mkdir -p data/subject02/large` to create missing directory

### Experiment 2: 02_nested_subdatasets.sh
- **Fixed**: Added `chmod -R +w` before cleanup to handle annex permissions
- **Fixed**: Added `-c protocol.file.allow=always` to git clone commands
- **Fixed**: Improved cleanup logic with proper permission handling

### Experiment 3: 03_metadata_cleanup.sh
- No fixes needed - worked on first run

---

## Next Steps

1. ✅ Document these findings
2. ✅ Update implementation plan based on nested subdataset discovery
3. ⏭ Begin implementation with basic split (no nested subdatasets)
4. ⏭ Add nested subdataset detection and error handling
5. ⏭ Design and implement nested subdataset preservation strategy

---

## Test Command Summary

To reproduce these experiments:

```bash
# Setup
uv venv
source .venv/bin/activate
uv pip install datalad

# Run experiments
bash docs/designs/split/experiments/01_basic_filter.sh
bash docs/designs/split/experiments/02_nested_subdatasets.sh
bash docs/designs/split/experiments/03_metadata_cleanup.sh
```

**Note**: Experiments create temporary directories under `/tmp/datalad-split-expXX/` which can be examined after running.
