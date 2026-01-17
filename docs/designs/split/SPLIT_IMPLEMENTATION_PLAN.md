# DataLad Split Command - Implementation Plan

## Executive Summary

This document outlines the implementation plan for a `datalad split` command that splits a DataLad dataset into multiple subdatasets, based on [GitHub Issue #3554](https://github.com/datalad/datalad/issues/3554) and related discussions. The command addresses the common scenario where users retroactively need to reorganize directories into independent subdatasets.

## Background & Use Cases

### Primary Use Cases
1. **Retroactive Organization**: Converting existing directories into subdatasets after realizing the dataset structure should have been different
2. **Size Management**: Splitting large datasets that have grown disproportionately
3. **Semantic Separation**: Organizing content into logical subdatasets for better management
4. **Nested Subdataset Handling**: Properly handling existing subdatasets during the split operation

### Key Challenge
As noted in the issue, when filtering repository history, "information about other keys for files that we filtered out...is still available in the git-annex branch," creating unnecessary bloat. The solution requires using `git-annex filter-branch` in conjunction with `git filter-branch`.

## Technical Approach

### Core Strategy: Clone-Based Filtering

Based on Kyle Meyer's proposal and community feedback, the implementation will use a **cloning-based approach** to avoid destructive in-place modifications:

1. **Clone** the source dataset to a temporary location
2. **Filter history** using `git filter-branch --subdirectory-filter` to isolate target paths
3. **Filter git-annex metadata** using `git-annex filter-branch` to remove unrelated key information
4. **Create new subdataset** with fresh UUID via `datalad create --force`
5. **Clean up remotes** by marking origin as dead and removing references
6. **Prune metadata** using `git annex forget --force --drop-dead`
7. **Register subdataset** in parent using git submodule
8. **Remove original content** from parent dataset

### Nested Subdataset Handling (Phase 4)

**Challenge**: `git filter-branch --subdirectory-filter` loses `.gitmodules` because it's at the repository root.

**Solution**: Reconstruct `.gitmodules` with adjusted paths:

1. **Before filtering**: Parse parent's `.gitmodules`, extract entries under target path
2. **After filtering**: Create new `.gitmodules` in split dataset with adjusted paths
   - Example: `data/raw/subject01` → `subject01`
3. **In parent**: Remove nested subdataset entries from parent's `.gitmodules`

**Phase 1 Limitations**:
1. Detect nested subdatasets and ERROR with clear message
2. **CRITICAL**: Only operate on paths belonging to current dataset, not subdatasets
   - If path belongs to subdataset, raise NotImplementedError
   - Recommend using `datalad foreach-dataset` to process subdatasets

**Phase 4 Implementation** will handle nested subdatasets through **bottom-up traversal** with `.gitmodules` reconstruction:

1. Discover all subdatasets recursively in the dataset
2. Process deepest subdatasets first (leaves of the tree)
3. Move up the hierarchy, handling parent datasets only after children
4. For each split: parse, reconstruct, and clean up `.gitmodules` at each level
5. This ensures nested subdatasets are properly registered with correct paths

### Command Execution Order

Critical insights from experiments and community discussion:

1. **`git rm -r --cached` MUST be done BEFORE cloning** (Experiment 11 fix) to prevent parent from tracking individual files
2. **Location tracking is preserved via `git-annex filter-branch --include-all-key-information`** (Experiment 7)
3. `git-annex filter-branch` should **precede** `git filter-branch` to ensure proper metadata cleanup
4. **Keep origin remote configured** to allow content retrieval on-demand

```bash
# CORRECT workflow (validated by Experiments 7, 9, 11):

# In parent repository:
cd <parent-dataset>

# Step 1: Remove from git index FIRST (while files still exist)
git rm -r --cached <path>/

# Step 2: Physically remove directory
rm -rf <path>/

# Step 3: Clone parent into the location
git clone . <path>/

# Step 4: Filter the cloned repository
cd <path>/
git-annex filter-branch <path> --include-all-key-information --include-all-repo-config
git filter-branch --subdirectory-filter <path> HEAD
git remote set-url origin <absolute-path-to-parent>  # Update origin URL
# CRITICAL: Do NOT run "git annex dead origin" or "git remote rm origin"
git annex forget --force --drop-dead    # Clean unrelated metadata

# Step 5: Return to parent and register as submodule
cd <parent-dataset>
git submodule add ./<path> <path>

# Step 6: Commit the changes
git commit -m "Split <path>/ into subdataset"

# Result:
# - Parent only tracks submodule commit (mode 160000), not individual files
# - Split dataset can retrieve content via 'datalad get' from parent
# - git annex whereis shows content available at origin
```

## Proposed Command Interface

### Basic Syntax
```bash
datalad split [-d|--dataset DATASET] [OPTIONS] PATH [PATH ...]
```

### Parameters

#### Required
- **PATH** (positional, multiple): Directory paths within the dataset to split into subdatasets

#### Optional
- **-d, --dataset DATASET**: Specify the parent dataset (default: current dataset)
- **--regex-subdatasets REGEX**: Pattern-based approach to identify multiple paths
- **-c, --cfg-proc PROC**: Configuration processor to apply to new subdatasets
- **-o, --output-path PATH**: Alternative output location (operate outside source directory)
- **--skip-rewrite {all,parent,subdataset}**: Control which history rewriting steps to skip
  - `all`: No history rewriting, use incremental approach (git rm/mv only)
  - `parent`: Skip parent dataset history rewrite
  - `subdataset`: Skip subdataset history rewrite
- **--dry-run**: Show what would be done without making changes
- **--force**: Proceed even if there are uncommitted changes (dangerous)
- **-r, --recursive**: Recursively handle nested subdatasets (enabled by default for bottom-up)
- **--jobs N**: Number of parallel operations for multiple splits

### Example Usage

```bash
# Simple case: split directory into subdataset
datalad split data/subject01

# Multiple directories with shell glob (makes data/, data/subject01/, data/subject02/, data/subject03/ all subdatasets)
datalad split data data/subject*

# Pattern-based splitting
datalad split --regex-subdatasets 'data/subject\d+' .

# With configuration
datalad split -c yoda data/code

# Dry-run to preview
datalad split --dry-run data/subject01

# Incremental mode (no history rewrite, backward compatible)
datalad split --skip-rewrite all data/subject01
```

## Implementation Plan

### Phase 1: Core Infrastructure

#### 1.1 Create Module Structure
- **Location**: `datalad/local/split.py`
- **Class**: `Split(Interface)`
- **Dependencies**:
  - `datalad.distribution.dataset.Dataset`
  - `datalad.support.annexrepo.AnnexRepo`
  - `datalad.support.gitrepo.GitRepo`
  - `datalad.cmd` for subprocess operations

#### 1.2 Parameter Definition
- Define all parameters using DataLad's `Parameter` system
- Add constraints and validators
- Write comprehensive docstrings

#### 1.3 Register Command
- Add to `datalad/interface/__init__.py` under appropriate group (likely `_group_2dataset`)
- Ensure command appears in `datalad --help`

### Phase 2: Core Functionality (Without Nested Subdatasets)

**Note**: Phase 2 implements the core split functionality for **leaf directories** only. Nested subdataset support (Phase 4) requires additional `.gitmodules` reconstruction logic.

#### 2.1 Path Discovery & Validation
```python
def _validate_paths(dataset, paths):
    """
    Validate that paths meet all requirements for splitting.

    Checks performed:
    1. Exist in the dataset
    2. Are not the dataset root
    3. Are not already subdatasets
    4. Are subdirectories (not files)
    5. Don't overlap (one is not parent of another)
    6. CRITICAL: Belong to current dataset, not to subdatasets

    For check #6:
    - Use dataset.get_containing_subdataset(path) or similar API
    - If path belongs to a subdataset (not current dataset):
      - Raise NotImplementedError with helpful message:
        "Cannot split paths that belong to subdatasets.
         To split content within subdatasets, use:
         datalad foreach-dataset --recursive <command>"

    Example error case:
        parent/
        ├── subds/         # existing subdataset
        │   └── data/      # user tries to split this

        $ datalad split subds/data
        ERROR: Path 'subds/data' belongs to subdataset 'subds', not to current dataset.
               Cannot split paths within subdatasets.

               To split content within subdatasets, navigate to the subdataset first:
                 cd subds
                 datalad split data

               Or use foreach-dataset to process multiple subdatasets:
                 datalad foreach-dataset --recursive split data

    Returns:
        validated_paths: List of validated absolute paths

    Raises:
        ValueError: For invalid paths (non-existent, root, files, overlapping)
        NotImplementedError: For paths belonging to subdatasets
    """
```

#### 2.2 Subdataset Discovery
```python
def _discover_subdatasets(dataset, path):
    """
    Recursively discover subdatasets under given path.
    Returns list ordered by depth (deepest first) for bottom-up processing.
    """
```

#### 2.3 History Filtering Workflow
```python
def _filter_repository_history(source_repo_path, target_path, subdir_path):
    """
    1. Clone source repository to target
    2. Run git-annex filter-branch with --include-all-key-information
       - This preserves location tracking information in git-annex branch
    3. Run git filter-branch --subdirectory-filter
    4. Update origin remote URL to point to original dataset location
       - CRITICAL: Do NOT mark origin as dead or remove it!
    5. Run git annex forget --force --drop-dead
       - Cleans unrelated metadata while preserving origin info
    6. Result: Split dataset can retrieve content via 'datalad get'
    """
```

#### 2.4 Subdataset Registration
```python
def _register_subdataset(parent_ds, subdataset_path):
    """
    Register newly created subdataset in parent:
    1. Initialize new dataset at target location
    2. Use datalad create --force to establish dataset
    3. Git add/commit in parent
    """
```

#### 2.5 Content Removal from Parent
```python
def _remove_content_from_parent(parent_ds, path):
    """
    Remove original content from parent dataset:
    1. git rm -r <path>/* (but keep the subdataset registration)
    2. Commit changes
    3. Optional: git annex forget to clean up parent's git-annex branch
    """
```

#### 2.6 Location Tracking Preservation (CRITICAL)
```python
def _preserve_location_tracking(clone_path, parent_path):
    """
    CRITICAL: Ensure split dataset can retrieve annexed content from parent.

    The key insight (from Experiment 7):
    - git-annex filter-branch with --include-all-key-information preserves
      location tracking information in the git-annex branch
    - Keeping origin remote configured allows on-demand content retrieval
    - No need to copy all content during split!

    Steps:
    1. After filtering, update origin remote URL to parent's absolute path
    2. Verify git-annex knows about origin: git annex whereis should show origin
    3. Test retrieval works: git annex find --not --in=here | head -n1 | xargs datalad get

    Parameters:
    - clone_path: Path to filtered clone (split dataset)
    - parent_path: Absolute path to parent dataset

    Returns:
    - location_preserved: Boolean indicating if location tracking is valid
    - content_available: Number of files that can be retrieved from origin
    """
```

**Why This Is Critical**:
- Experiment 7 validated that `git-annex filter-branch --include-all-key-information`
  properly preserves location tracking
- Split datasets can retrieve content on-demand via `datalad get`
- No wasteful copying of potentially large content during split
- Works with DataLad's standard content retrieval infrastructure

**Implementation Notes**:
- Use `git-annex filter-branch --include-all-key-information --include-all-repo-config`
- Update origin remote URL to absolute path of parent dataset
- **DO NOT** mark origin as dead or remove the remote
- Verify `git annex whereis` shows origin for tracked files
- Document that parent dataset must remain accessible for content retrieval
- Consider optional `--copy-content` flag for users who want "offline" split datasets

### Phase 3: Advanced Features

#### 3.1 Incremental Mode (--skip-rewrite all)
- Use simple `git rm` and `git mv` operations
- Maintain backward compatibility
- No history rewriting, simpler and safer but keeps all history in both datasets

#### 3.2 Pattern-Based Splitting (--regex-subdatasets)
- Parse regex pattern
- Find all matching directories
- Process in batch

#### 3.3 Configuration Processors
- Support `--cfg-proc` to apply configuration to new subdatasets
- Common processors: `yoda`, `text2git`, etc.

#### 3.4 Dry-Run Mode
- Simulate all operations
- Report what would be done
- No actual modifications

### Phase 4: Nested Subdataset Support

**Critical Insight** (from Experiments 2 & 10): `git filter-branch --subdirectory-filter` **loses `.gitmodules`** because it's at the repository root. The subdatasets become regular directories after filtering.

**Solution**: Manually reconstruct `.gitmodules` with adjusted paths.

#### 4.1 Nested Subdataset Detection
```python
def _detect_nested_subdatasets(dataset, target_path):
    """
    Parse .gitmodules to find subdatasets under target_path.

    Returns:
    - List of subdataset entries with original paths
    - e.g., for target "data/raw":
      [
        {"path": "data/raw/subject01", "url": "..."},
        {"path": "data/raw/subject02", "url": "..."}
      ]
    """
```

#### 4.2 .gitmodules Reconstruction
```python
def _reconstruct_gitmodules(split_dataset_path, target_path, nested_subdatasets):
    """
    CRITICAL: Recreate .gitmodules in the split dataset with ALL configuration.

    Problem: git filter-branch loses .gitmodules at repository root
    Solution:
    1. Parse parent's .gitmodules BEFORE filtering
    2. Extract ALL entries (path, url, and custom configs) under target_path
    3. AFTER filtering, create new .gitmodules with adjusted paths

    Example - Parent .gitmodules:
        [submodule "data/raw/subject01"]
            path = data/raw/subject01
            url = ./subject01
            update = checkout
            branch = main
            fetchRecurseSubmodules = false
            datalad-id = 12345-abcde
            datalad-url = https://example.com/dataset

    After filtering to "data/raw/", create in split dataset:
        [submodule "subject01"]
            path = subject01                    # ADJUSTED: stripped prefix
            url = ./subject01                   # ADJUSTED if relative to dataset root
            update = checkout                   # PRESERVED
            branch = main                       # PRESERVED
            fetchRecurseSubmodules = false      # PRESERVED
            datalad-id = 12345-abcde           # PRESERVED
            datalad-url = https://example.com/dataset  # PRESERVED

    Steps:
    1. Parse ALL settings for each submodule under target_path:
       - Use: git config -f .gitmodules --get-regexp '^submodule\.<name>\.'
    2. For each submodule entry:
       a. Adjust 'path': strip target_path prefix
       b. Adjust 'url' if it's a relative path referencing dataset internals
       c. PRESERVE all other settings (update, branch, datalad-*, etc.)
    3. Write new .gitmodules with all settings
    4. git add .gitmodules && git commit
    5. Update each subdataset's .git file to point to correct location

    Important URL handling:
    - Relative URLs like "./subject01" or "../other": Keep as-is or adjust if needed
    - Absolute paths within dataset: Strip prefix
    - External URLs (http://, git://): Preserve unchanged
    - DataLad URLs (datalad-url config): Preserve unchanged

    Returns:
    - Number of subdatasets reconstructed
    - List of any configuration that couldn't be transferred
    """
```

#### 4.3 Parent .gitmodules Cleanup
```python
def _remove_nested_subdatasets_from_parent(parent_dataset, target_path, nested_subdatasets):
    """
    Remove nested subdataset entries from parent's .gitmodules.

    When we split "data/raw/" containing "data/raw/subject01":
    1. Remove [submodule "data/raw/subject01"] from parent's .gitmodules
    2. These subdatasets are now registered in the split dataset's .gitmodules
    3. git add .gitmodules
    4. Commit will happen during final save

    Important: This is done BEFORE registering the split dataset itself
    """
```

#### 4.4 Bottom-Up Processing Algorithm
```python
def _split_with_nested_subdatasets(dataset, target_paths):
    """
    Process nested subdatasets in bottom-up order.

    Algorithm:
    1. For each target_path:
       a. Detect nested subdatasets under target_path
       b. Parse their .gitmodules entries

    2. Clone parent to target location

    3. Run git filter-branch (loses .gitmodules)

    4. Reconstruct .gitmodules with adjusted paths:
       - Parse saved entries
       - Strip target_path prefix
       - Create new .gitmodules

    5. Update .git files in nested subdatasets to point to correct locations

    6. In parent: Remove nested entries from .gitmodules

    7. In parent: Register split dataset as submodule

    Example workflow for splitting "data/raw/":

    # Before split - Parent .gitmodules:
    [submodule "data/raw/subject01"]
        path = data/raw/subject01
        url = ./data/raw/subject01
        update = checkout
        branch = main
        datalad-id = abc-123
    [submodule "data/raw/subject02"]
        path = data/raw/subject02
        url = https://example.com/subject02.git
        fetchRecurseSubmodules = false

    # After split - data/raw/ (split dataset) .gitmodules:
    [submodule "subject01"]
        path = subject01                    # ADJUSTED: prefix stripped
        url = ./subject01                   # ADJUSTED: relative to new root
        update = checkout                   # PRESERVED
        branch = main                       # PRESERVED
        datalad-id = abc-123               # PRESERVED
    [submodule "subject02"]
        path = subject02                    # ADJUSTED: prefix stripped
        url = https://example.com/subject02.git  # PRESERVED: external URL
        fetchRecurseSubmodules = false      # PRESERVED

    # After split - Parent .gitmodules:
    [submodule "data/raw"]
        path = data/raw
        url = ./data/raw
    # Note: data/raw/subject01 and data/raw/subject02 entries removed
    """
```

#### 4.5 Subdataset Boundary Handling
- Detect when a subdataset straddles the split boundary
- Provide clear error messages
- Suggest alternative split paths
- Examples:
  - ERROR: "Cannot split 'data/raw' because subdataset 'data/shared' crosses boundary"
  - SUGGEST: "Consider splitting 'data/' entirely, or split 'data/raw/subject01' individually"

### Phase 5: Testing Strategy

#### 5.1 Unit Tests (`datalad/local/tests/test_split.py`)

**Test Categories:**

1. **Basic Functionality**
   - `test_split_simple_directory`: Split single directory with files
   - `test_split_multiple_directories`: Split multiple directories in one command
   - `test_split_with_git_history`: Verify history is properly filtered
   - `test_split_preserves_annex_content`: Verify annexed files are accessible in new subdataset

2. **Git-Annex Integration & Location Tracking** (CRITICAL)
   - `test_split_preserves_location_tracking`: Verify git annex whereis shows origin
   - `test_split_content_retrieval`: Verify 'datalad get' works in split dataset
   - `test_split_content_integrity`: Verify checksums after retrieval
   - `test_split_roundtrip_retrieval`: Clone split dataset, verify content accessible
   - `test_split_filters_annex_metadata`: Verify git-annex branch is cleaned
   - `test_split_preserves_key_information`: Ensure key info for split files is retained
   - `test_split_cleans_unrelated_keys`: Verify unrelated keys are removed
   - `test_split_with_special_remotes`: Test with S3, WebDAV, etc.
   - `test_split_large_annexed_files`: Test with GB-sized files
   - `test_split_partial_content`: Handle case where some content is not available in parent

3. **Nested Subdatasets** (Phase 4 - .gitmodules reconstruction)
   - `test_split_detects_nested_subdatasets`: Detect subdatasets under target path
   - `test_split_error_on_nested_without_support`: Phase 1 should error with clear message
   - `test_split_reconstructs_gitmodules`: Verify .gitmodules recreated with adjusted paths
   - `test_split_removes_nested_from_parent_gitmodules`: Verify parent cleanup
   - `test_split_nested_subdataset_functionality`: Verify nested subdatasets work after split
   - `test_split_preserves_nested_hierarchy`: Multi-level nesting (e.g., data/raw/subject01/)
   - `test_split_cross_boundary_subdataset`: Subdataset partially in/out of split path (should error)
   - `test_split_gitmodules_path_adjustment`: Verify paths correctly adjusted (data/raw/sub01 → sub01)
   - `test_split_gitmodules_url_adjustment`: Verify URLs adjusted if relative to dataset root
   - `test_split_preserves_custom_submodule_config`: **CRITICAL** - Verify ALL config preserved:
     * `update` setting (merge, checkout, rebase, none)
     * `branch` setting
     * `fetchRecurseSubmodules` setting
     * `datalad-id` and `datalad-url` settings
     * Any custom configuration keys
   - `test_split_gitmodules_external_urls_preserved`: External URLs (http://, git://) unchanged
   - `test_split_gitmodules_relative_urls_adjusted`: Relative URLs adjusted correctly (./path, ../path)
   - `test_split_gitmodules_config_completeness`: Verify no configuration lost during reconstruction

4. **Edge Cases**
   - `test_split_nonexistent_path`: Should fail gracefully
   - `test_split_already_subdataset`: Should detect and error
   - `test_split_path_in_subdataset`: **CRITICAL** - Verify paths belonging to subdatasets are rejected
     * Create parent dataset with subdataset
     * Try to split path within subdataset (e.g., `subds/data`)
     * Should raise NotImplementedError with helpful message
     * Verify message suggests `datalad foreach-dataset`
     * Test with nested subdataset (multiple levels deep)
   - `test_split_overlapping_paths`: Two paths where one contains the other
   - `test_split_dataset_root`: Should fail (can't split entire dataset)
   - `test_split_empty_directory`: Handle empty directories
   - `test_split_with_uncommitted_changes`: Behavior with dirty working tree

5. **Configuration & Options**
   - `test_split_with_cfg_proc`: Apply configuration processors
   - `test_split_dry_run`: Verify no changes made in dry-run mode
   - `test_split_skip_rewrite`: Test incremental mode
   - `test_split_output_path`: Split to alternative location

6. **Error Handling**
   - `test_split_missing_dataset`: No dataset found
   - `test_split_permission_error`: Insufficient permissions
   - `test_split_git_annex_unavailable`: Fallback behavior without git-annex

7. **Integration Tests**
   - `test_split_roundtrip`: Split then clone, verify content retrievable
   - `test_split_roundtrip_with_get`: Clone split dataset, run 'datalad get -r'
   - `test_split_with_remotes`: Verify remote operations still work
   - `test_split_workflow_scenario`: Complete realistic workflow
   - `test_split_parent_remains_accessible`: Verify parent dataset can serve content
   - `test_split_chained_retrieval`: Clone of split can retrieve from original via origin chain

8. **Performance Tests** (in `benchmarks/`)
   - Benchmark splitting large directories (1000+ files)
   - Benchmark with many subdatasets (100+ nested)
   - Memory usage during filter operations

#### 5.2 Test Fixtures & Utilities

```python
@pytest.fixture
def dataset_with_nested_structure():
    """
    Create test dataset with structure:
    dataset/
      ├── data/
      │   ├── raw/
      │   │   ├── subject01/ (to be split)
      │   │   │   ├── session1/
      │   │   │   └── subsub/ (nested subdataset)
      │   │   └── subject02/ (to be split)
      │   └── processed/
      ├── code/ (already a subdataset)
      │   └── analysis/ (path within subdataset - should reject split)
      └── docs/

    This fixture is used to test:
    - Splitting leaf directories (subject01, subject02)
    - Detecting existing subdatasets (code)
    - CRITICAL: Rejecting paths within subdatasets (code/analysis)
    - Detecting nested subdatasets (subsub under subject01)
    """
```

#### 5.3 Integration with Existing Tests
- Ensure split command works with other DataLad operations
- Test interaction with `clone`, `get`, `push`, `update`
- Verify RIA stores compatibility

### Phase 6: Prototype Experimentation

Before implementing the full command, create experimental scripts to validate git/git-annex behavior:

#### 6.1 Experiment 1: Basic Filter Branch
```bash
# Script: experiments/01_basic_filter.sh
# Test: Does git filter-branch + git-annex filter-branch work as expected?
# Verify: Resulting repository size, git-annex branch content
```

#### 6.2 Experiment 2: Nested Subdataset Handling
```bash
# Script: experiments/02_nested_subdatasets.sh
# Test: What happens to nested subdatasets during filter-branch?
# Verify: Subdataset registrations preserved, .gitmodules handling
```

#### 6.3 Experiment 3: Metadata Cleanup
```bash
# Script: experiments/03_metadata_cleanup.sh
# Test: Does git annex forget properly clean up metadata?
# Verify: .log.met and .log.web files cleaned, repository size reduction
```

#### 6.4 Experiment 4: Performance Testing
```bash
# Script: experiments/04_performance.sh
# Test: Time and memory usage for various dataset sizes
# Verify: Scalability, identify bottlenecks
```

### Phase 7: Documentation

#### 7.1 Command Documentation
- Comprehensive docstring in `split.py`
- Examples for common use cases
- Warnings about potential issues

#### 7.2 User Guide
- Add section to DataLad Handbook
- Step-by-step tutorial with screenshots
- Best practices for splitting datasets

#### 7.3 Developer Documentation
- Architecture decisions document
- Algorithm explanations
- Troubleshooting guide for common issues

### Phase 8: Advanced Considerations

#### 8.1 Multiple Pruning Strategies

Support three pruning strategies as discussed in issue:

1. **Horizontal Prune** (default): Filter by directory, rebuild history
2. **Vertical Prune**: Time-based history reduction (future enhancement)
3. **Incremental Prune**: No history rewrite, just git rm/mv operations

#### 8.2 Safety Features

- **Pre-flight Checks**:
  - Verify git-annex version supports filter-branch
  - Check for uncommitted changes (unless --force)
  - Verify sufficient disk space for cloning
  - Check for existing subdatasets at target paths

- **Backup Recommendation**:
  - Warn user to backup before operation
  - Optionally create automatic backup branch

- **Atomic Operations**:
  - Use temporary directories for intermediate steps
  - Clean up on failure
  - Allow resumption if interrupted

#### 8.3 Parallel Processing

For splitting multiple directories:
- Use `--jobs N` to process in parallel
- Careful coordination of git-annex operations (may need locking)

## Implementation Checklist

### Pre-Implementation
- [x] Review issue #3554 and related discussions
- [x] Research git-annex filter-branch capabilities
- [x] Understand DataLad command structure
- [ ] Run prototype experiments (Phase 6)
- [ ] Validate approach with community/maintainers

### Core Implementation
- [ ] Create `datalad/local/split.py` module
- [ ] Implement parameter definitions
- [ ] Implement path validation
- [ ] Implement history filtering workflow
- [ ] Implement subdataset registration
- [ ] Implement content removal from parent
- [ ] Register command in interface

### Advanced Features
- [ ] Implement nested subdataset discovery
- [ ] Implement bottom-up traversal
- [ ] Implement incremental mode
- [ ] Implement pattern-based splitting
- [ ] Implement dry-run mode
- [ ] Implement configuration processors

### Testing
- [ ] Write basic functionality tests
- [ ] Write git-annex integration tests
- [ ] Write nested subdataset tests
- [ ] Write edge case tests
- [ ] Write error handling tests
- [ ] Write integration tests
- [ ] Add performance benchmarks

### Documentation
- [ ] Write comprehensive docstrings
- [ ] Add examples to command help
- [ ] Write Handbook section
- [ ] Create tutorial/walkthrough
- [ ] Document known limitations

### Finalization
- [ ] Code review with maintainers
- [ ] Address review feedback
- [ ] Performance optimization if needed
- [ ] Final testing on various platforms
- [ ] Prepare changelog entry

## Known Limitations & Future Work

### Current Limitations
1. **Destructive Operation**: While using clones, the operation modifies the parent dataset
2. **Disk Space**: Requires substantial temporary disk space for cloning
3. **Time Intensive**: History filtering can be slow for large datasets
4. **Git-Annex Requirement**: Requires recent git-annex version with filter-branch support

### Future Enhancements
1. **Vertical Pruning**: Time-based history reduction
2. **Smart Merging**: Ability to merge split datasets back together
3. **Interactive Mode**: Guide user through split decisions
4. **Undo/Rollback**: Easier reversal of split operations
5. **Partial History**: Option to keep only recent history
6. **Remote Awareness**: Better handling of existing remotes and siblings

## Technical Debt & Risk Mitigation

### Risks
1. **Data Loss**: Improper filtering could lose file availability information
2. **History Corruption**: Git filter-branch can corrupt history if misused
3. **Subdataset Conflicts**: Existing subdatasets might conflict with splits
4. **Performance**: Large datasets may take extremely long to process

### Mitigation Strategies
1. **Extensive Testing**: Comprehensive test suite covering edge cases
2. **Backup Prompts**: Always warn users to backup first
3. **Dry-Run Default**: Consider making dry-run the default, require explicit --execute
4. **Checkpoints**: Save state at each major step for recovery
5. **Validation**: Verify integrity after each operation
6. **Community Review**: Get feedback from experienced users before finalizing

## References

- [GitHub Issue #3554](https://github.com/datalad/datalad/issues/3554) - Main discussion
- [GitHub Issue #600](https://github.com/datalad/datalad/issues/600) - Related filtering discussion
- [git-annex filter-branch docs](https://git-annex.branchable.com/git-annex-filter-branch/)
- [git filter-branch docs](https://git-scm.com/docs/git-filter-branch)
- DataLad Handbook on subdatasets
