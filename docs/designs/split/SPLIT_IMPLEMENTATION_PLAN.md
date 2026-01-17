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

### Bottom-Up Traversal for Nested Subdatasets

The implementation will handle nested subdatasets through **bottom-up traversal**:

1. Discover all subdatasets recursively in the dataset
2. Process deepest subdatasets first (leaves of the tree)
3. Move up the hierarchy, handling parent datasets only after children
4. This ensures nested subdatasets are properly registered and their content is preserved

### Command Execution Order

Critical insights from experiments and community discussion:

1. **Content MUST be transferred BEFORE filtering** (Experiments 5 & 6)
2. `git-annex filter-branch` should **precede** `git filter-branch` to ensure proper metadata cleanup

```bash
# Recommended order (Strategy A - with content transfer):
git annex get <path>                    # CRITICAL: Transfer content FIRST
git annex find --in=here <path>         # Verify content present
git-annex filter-branch <path> --include-all-key-information --include-all-repo-config
git filter-branch --subdirectory-filter <path> HEAD
git annex dead origin                   # Content already local, safe to remove
git remote rm origin
git annex forget --force --drop-dead

# Alternative order (Strategy B - keep origin):
git-annex filter-branch <path> --include-all-key-information --include-all-repo-config
git filter-branch --subdirectory-filter <path> HEAD
git remote set-url origin <absolute-path-to-original>  # Keep origin for content retrieval
# Skip: git annex dead origin (we want to keep it!)
# Skip: git remote rm origin
git annex forget --force --drop-dead    # Clean metadata but keep remote info
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
- **--get-content / --no-get-content**: Transfer annexed content before split (default: True)
  - `--get-content`: Copy all annexed content to split dataset (Strategy A - recommended)
  - `--no-get-content`: Keep origin remote for on-demand retrieval (Strategy B - smaller dataset)
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

# Large dataset - don't copy content, keep origin as source
datalad split --no-get-content data/large-subject
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

### Phase 2: Core Functionality

#### 2.1 Path Discovery & Validation
```python
def _validate_paths(dataset, paths):
    """
    Validate that paths:
    - Exist in the dataset
    - Are not the dataset root
    - Are not already subdatasets
    - Are subdirectories (not files)
    - Don't overlap (one is not parent of another)
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
def _filter_repository_history(source_repo_path, target_path, subdir_path, get_content=True):
    """
    1. Clone source repository to target
    2. CRITICAL: Transfer annexed content (see 2.6)
       - If get_content=True: Run 'git annex get <subdir_path>'
       - Verify content present with 'git annex find --in=here'
    3. Run git-annex filter-branch for the subdirectory
    4. Run git filter-branch --subdirectory-filter
    5. If get_content=True:
       - Mark origin as dead
       - Remove origin remote
       - Run git annex forget --force --drop-dead
    6. If get_content=False:
       - Update origin remote URL to point to original
       - Keep origin as git-annex remote
    7. Update git-annex branch
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

#### 2.6 Content Transfer (CRITICAL)
```python
def _transfer_annexed_content(clone_path, subdir_path, get_content=True):
    """
    CRITICAL: Transfer annexed content before filtering history.

    Two strategies available:

    Strategy A (Recommended - Default): Copy content before filtering
    1. Before filter-branch: git annex get <subdir_path>
    2. Verify content present: git annex find --in=here <subdir_path>
    3. Proceed with filtering - content survives in .git/annex/objects/
    4. Result: Split dataset is independent, content immediately available

    Strategy B (Alternative): Maintain origin remote
    1. Skip marking origin as dead
    2. Configure origin remote with proper URL
    3. Content retrievable via 'datalad get' from original
    4. Result: Smaller split dataset, requires access to original

    Parameters:
    - clone_path: Path to cloned repository
    - subdir_path: Subdirectory being split
    - get_content: If True, use Strategy A; if False, use Strategy B

    Returns:
    - content_transferred: Number of annexed files transferred
    - content_missing: Number of annexed files not available
    """
```

**Why This Is Critical**:
- Experiments 5 & 6 revealed that `git filter-branch` does NOT transfer annexed content
- Without explicit content handling, split datasets have broken symlinks
- Users cannot retrieve content from split datasets
- This is a **blocking issue** that must be solved in Phase 1

**Implementation Notes**:
- Add `--get-content` flag (default: True) to control behavior
- For large datasets, provide option to use Strategy B (--no-get-content)
- Progress reporting during content transfer
- Verify all content transferred successfully before proceeding
- Handle cases where content is not available in original

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

#### 4.1 Bottom-Up Traversal Algorithm
```python
def _process_nested_subdatasets(dataset, target_paths):
    """
    For each target path:
    1. Discover all nested subdatasets
    2. Sort by depth (deepest first)
    3. Process each subdataset:
       a. If subdataset is entirely within target path: include in split
       b. If subdataset crosses boundary: error or warn
    4. Process leaf subdatasets first, then parents
    """
```

#### 4.2 Subdataset Boundary Handling
- Detect when a subdataset straddles the split boundary
- Provide clear error messages
- Suggest alternative split paths

### Phase 5: Testing Strategy

#### 5.1 Unit Tests (`datalad/local/tests/test_split.py`)

**Test Categories:**

1. **Basic Functionality**
   - `test_split_simple_directory`: Split single directory with files
   - `test_split_multiple_directories`: Split multiple directories in one command
   - `test_split_with_git_history`: Verify history is properly filtered
   - `test_split_preserves_annex_content`: Verify annexed files are accessible in new subdataset

2. **Git-Annex Integration & Content Transfer** (CRITICAL)
   - `test_split_transfers_annexed_content`: Verify annexed content is accessible (Strategy A)
   - `test_split_content_integrity`: Verify checksums after content transfer
   - `test_split_with_no_get_content`: Test Strategy B (keep origin remote)
   - `test_split_content_retrieval`: Verify 'datalad get' works in split dataset
   - `test_split_filters_annex_metadata`: Verify git-annex branch is cleaned
   - `test_split_preserves_key_information`: Ensure key info for split files is retained
   - `test_split_cleans_unrelated_keys`: Verify unrelated keys are removed
   - `test_split_with_special_remotes`: Test with S3, WebDAV, etc.
   - `test_split_large_annexed_files`: Test with GB-sized files
   - `test_split_partial_content`: Handle case where some content is not available

3. **Nested Subdatasets**
   - `test_split_with_nested_subdatasets`: Directory containing subdatasets
   - `test_split_preserves_nested_subdataset_structure`: Verify hierarchy maintained
   - `test_split_cross_boundary_subdataset`: Subdataset partially in/out of split path
   - `test_split_bottom_up_processing`: Verify correct order of operations

4. **Edge Cases**
   - `test_split_nonexistent_path`: Should fail gracefully
   - `test_split_already_subdataset`: Should detect and error
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
   - `test_split_roundtrip`: Split then clone, verify content accessible
   - `test_split_roundtrip_with_get`: Clone split dataset and retrieve all content
   - `test_split_with_remotes`: Verify remote operations still work
   - `test_split_workflow_scenario`: Complete realistic workflow
   - `test_split_content_survives_clone`: Verify content accessible in cloned split dataset

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
      └── docs/
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
