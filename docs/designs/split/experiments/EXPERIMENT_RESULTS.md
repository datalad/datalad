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

## Experiment 5: Real-World Dataset Validation

**Status**: ⚠️ **FAILURE** - Identifies critical content issue

### Results

Split datasets **CANNOT** retrieve annexed content - this is a critical blocker!

**What Happened**:
1. ✅ Split dataset created successfully
2. ✅ File structure preserved correctly
3. ⚠️ **Annexed content is NOT present** in split dataset
4. ⚠️ **`datalad get` fails** with "not available"
5. ⚠️ Content links are broken - no way to retrieve actual data

**Key Findings**:
```
Files in split dataset:
./anat/anat1.txt    ✅ Present (text file)
./func/scan1.txt    ✅ Present (text file)

Annexed files status:
anat/T1w.nii.gz     ⚠️ Symlink exists, but content MISSING
func/bold.nii.gz    ⚠️ Symlink exists, but content MISSING

Attempting datalad get:
get(error): func/bold.nii.gz (file) [not available]
get(error): anat/T1w.nii.gz (file) [not available]
```

**Why This Happens**:
- `git filter-branch` rewrites history but doesn't copy annexed objects
- `git annex filter-branch` preserves metadata but not actual files
- After removing origin remote, git-annex has no location information
- The `.git/annex/objects/` directory doesn't contain the actual content

### Conclusions

**CRITICAL FINDING**: Simply filtering git history does **NOT** preserve annexed content!

The split command implementation MUST:
1. **Either**: Copy annexed content BEFORE filtering
2. **Or**: Maintain origin as a git-annex remote for retrieval

This is a **blocking issue** - without solving this, split datasets are incomplete and unusable for annexed content.

---

## Experiment 6: Content Transfer Fix

**Status**: ✅ **SUCCESS** - Found working solutions

### Results

Tested three different approaches to preserve annexed content during split:

#### Method 1: Split WITHOUT preserving content link
- ✗ **Result**: Content NOT available
- Origin marked as dead and removed
- No way to retrieve content
- Files: 2 present, 0 annexed content, 1 missing

#### Method 2: Split WITH preserved content link
- ✓ **Result**: Content retrievable from origin
- Origin remote kept with updated URL
- `datalad get` successfully retrieves content
- Files: 4 present, 1 annexed content retrieved, 0 missing
```bash
# Keep origin as source
git remote set-url origin "$(realpath $EXPERIMENT_DIR/parent-dataset)"
datalad get .
# Result: get(ok): data.dat (file) [from origin...]
```

#### Method 3: Copy annexed objects BEFORE splitting
- ✓ **Result**: Content survives filtering
- Content copied before any filtering
- Content remains in `.git/annex/objects/` after split
- Files: 4 present, 1 annexed content, 0 missing
```bash
# Get content BEFORE filtering
git annex get data/subject01/ 2>&1 | tail -3
# Now filter
git annex filter-branch data/subject01 --include-all-key-information
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD
# Result: Content survived! Accessible via symlink
```

**Content Verification**:
```
METHOD 1 (no source):
  data.dat: missing ✗

METHOD 2 (kept source):
  data.dat: missing ✗ (but retrievable via datalad get)

METHOD 3 (copied before filter):
  data.dat: symlink → 2097152 bytes (✓ accessible)
```

### Conclusions

**RECOMMENDED APPROACH**: Method 3 (Copy content before filtering)

**Why Method 3 is best**:
1. ✅ Split dataset is **independent** - doesn't rely on original
2. ✅ Content is **immediately available** - no need to fetch
3. ✅ Works **offline** - no network dependency
4. ✅ Simpler user experience - content "just works"

**Why Method 2 is viable alternative**:
1. ✅ Smaller split dataset - no duplicate content storage
2. ✅ Can retrieve content on-demand
3. ⚠️ Requires maintaining original dataset location
4. ⚠️ Requires network/filesystem access to original

**Implementation Requirements**:
- Add `--get-content` flag (default: true) to control behavior
- Before filtering: Run `git annex get <path>` to fetch all content
- Verify content present: Check `git annex find --in=here`
- Provide option to skip copy for large datasets (use Method 2 instead)

---

## Experiment 7: Correct Location Tracking

**Status**: ✅ **SUCCESS** - Validated the proper git-annex workflow!

### Results

**This is the CORRECT approach** - `git-annex filter-branch` with `--include-all-key-information` properly preserves location tracking information!

**What Worked**:
1. ✅ Clone source dataset
2. ✅ Run `git-annex filter-branch <path> --include-all-key-information --include-all-repo-config`
3. ✅ Run `git filter-branch --subdirectory-filter <path>`
4. ✅ Update origin remote URL (DON'T remove it!)
5. ✅ Split dataset knows where to get content: `git annex whereis` shows origin
6. ✅ `datalad get` successfully retrieves content from origin
7. ✅ Even clones of the split dataset can retrieve content!

**Key Evidence**:
```
$ git annex whereis data.dat
whereis data.dat (1 copy)
  bd845c82-4768-4773-8e3e-7eac455c7447 -- [...]/parent-dataset [origin]
ok

$ datalad get data.dat
get(ok): data.dat (file) [from origin...]

# Roundtrip test - clone the split dataset
$ git clone split-correct split-correct-clone
$ cd split-correct-clone
$ git annex whereis data.dat
whereis data.dat (2 copies)
  bd845c82-4768-4773-8e3e-7eac455c7447 -- [...]/parent-dataset
  fab26add-acf5-4046-bd97-fe9ddfbbbeff -- [...]/split-correct [origin]
ok

$ datalad get data.dat
get(ok): data.dat (file) [from origin...]
✓ SUCCESS: Content retrieved in clone!
```

### Conclusions

**CRITICAL CORRECTION**: Experiments 5 & 6 were testing the wrong approach!

The **CORRECT workflow** is:
1. Use `git-annex filter-branch` with `--include-all-key-information` to preserve location tracking
2. **Keep the origin remote** (don't mark as dead or remove it)
3. Content remains available on-demand via `datalad get`
4. **No need to copy all content during split** - this would be wasteful!

**Why This Is the Right Approach**:
- ✅ Split dataset is smaller (no duplicate content storage)
- ✅ Content retrievable on-demand via standard `datalad get`
- ✅ Works with DataLad's existing infrastructure
- ✅ Supports chained retrieval (clone of split can still get content)
- ✅ Efficient for large datasets (don't copy everything unnecessarily)

**Implementation Requirements**:
- Use `git-annex filter-branch --include-all-key-information --include-all-repo-config`
- Update origin remote URL to point to parent dataset location
- **DO NOT** mark origin as dead or remove it
- Document that parent dataset must remain accessible for content retrieval

**Supersedes**: The recommendations from Experiment 6 about copying content first (Method 3) are now obsolete. Method 2 (keep origin) is the correct and only necessary approach.

---

## Overall Assessment

### What's Ready for Implementation

1. ✅ **Basic workflow**: Clone → filter → cleanup sequence works
2. ✅ **Size reduction**: Achieves significant .git size reduction
3. ✅ **Command ordering**: git-annex filter-branch before git filter-branch
4. ✅ **Metadata cleanup**: git annex forget executes successfully

### Critical Issues to Address

1. ✅ **Content Retrieval**: SOLVED (see Experiment 7)
   - Use `git-annex filter-branch --include-all-key-information`
   - Keep origin remote configured (don't mark as dead)
   - Content remains available via `datalad get`
2. ⚠️ **Nested subdatasets**: Require special handling (see Experiment 2)
3. ⚠️ **Git protocol**: Need to handle protocol.file.allow for local operations
4. ℹ️ **Metadata references**: Some cross-references may persist (minor issue)

### Recommendations for Implementation

#### Phase 1: Basic Implementation
- Implement basic split without nested subdataset support
- **CRITICAL**: Preserve location tracking via `git-annex filter-branch --include-all-key-information`
- **CRITICAL**: Keep origin remote configured (update URL, don't mark as dead)
- Add explicit check to ERROR if nested subdatasets detected
- Document that parent dataset must remain accessible for content retrieval
- Document limitations clearly

#### Phase 2: Nested Subdataset Support & Advanced Features
- Implement subdataset detection
- Add logic to preserve/reconstruct .gitmodules
- Consider option to copy content locally for "offline" split datasets (optional)
- Test thoroughly with various nesting scenarios

#### Testing Priorities
1. **Critical**: Test content retrieval via `datalad get` from split datasets
2. **Critical**: Verify location tracking preserved correctly (git annex whereis)
3. **High**: Test with nested subdatasets (various depths)
4. **High**: Test roundtrip (clone split dataset, verify content accessible)
5. **High**: Verify content integrity after retrieval (checksums)
6. **Medium**: Test with special remotes (S3, WebDAV, etc.)
7. **Medium**: Test performance with many files (1000+)
8. **Low**: Test optional "offline mode" if implemented (copy content during split)

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

### Experiment 5: 05_real_world_validation.sh
- No fixes needed - correctly identified the content transfer issue

### Experiment 6: 06_content_transfer_fix.sh
- No fixes needed - successfully found working solutions
- **Note**: Method 3 recommendations superseded by Experiment 7

### Experiment 7: 07_correct_location_tracking.sh
- No fixes needed - validates the correct git-annex workflow
- **This is the definitive experiment for content handling**

---

## Next Steps

1. ✅ Document these findings
2. ✅ Update implementation plan based on nested subdataset discovery
3. ✅ Validate content transfer requirements (Experiments 5, 6 & 7)
4. ✅ Identified correct approach: preserve location tracking, keep origin remote
5. ⏭ Update implementation plan to reflect correct git-annex workflow
6. ⏭ Begin implementation with basic split (no nested subdatasets)
7. ⏭ Implement location tracking preservation (keep origin remote)
8. ⏭ Add nested subdataset detection and error handling
9. ⏭ Design and implement nested subdataset preservation strategy

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
bash docs/designs/split/experiments/05_real_world_validation.sh
bash docs/designs/split/experiments/06_content_transfer_fix.sh
bash docs/designs/split/experiments/07_correct_location_tracking.sh  # DEFINITIVE
```

**Note**: Experiments create temporary directories under `/tmp/datalad-split-expXX/` which can be examined after running.

**Important**:
- Experiments 5 & 6 initially explored content transfer approaches
- **Experiment 7 validates the CORRECT approach** using proper git-annex location tracking
- The correct workflow: use `--include-all-key-information` and keep origin remote configured
