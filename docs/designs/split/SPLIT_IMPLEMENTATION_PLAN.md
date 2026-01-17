# DataLad Split Command - Implementation Plan

## Executive Summary

This document outlines the implementation plan for a `datalad split` command that splits a DataLad dataset into multiple subdatasets, based on [GitHub Issue #3554](https://github.com/datalad/datalad/issues/3554) and related discussions. The command addresses the common scenario where users retroactively need to reorganize directories into independent subdatasets.

## ⚠️ CRITICAL DISCLAIMER

**IMPORTANT: The split operation is complex and potentially alters repository behavior in subtle ways.**

This command performs destructive operations including:
- Git history rewriting (`git filter-branch`)
- Git-annex branch filtering and metadata cleanup
- Removal of content from parent dataset
- Reconstruction of `.gitattributes` with path adjustments
- Modification of git-annex location tracking
- Potential alteration of content accessibility

**BEFORE RUNNING `datalad split`:**

1. **BACKUP YOUR DATASET**: Create a complete backup of your dataset before proceeding
   ```bash
   # Create backup clone with all annexed content
   datalad clone --reckless availability /path/to/dataset /path/to/backup
   cd /path/to/backup
   datalad get -r .  # Get all content if needed
   ```

2. **Verify backup integrity**: Ensure backup is complete and functional
   ```bash
   cd /path/to/backup
   git status  # Should be clean
   datalad status  # Should show all content available
   ```

3. **Test on small dataset first**: Before splitting large/important datasets, test the workflow on a small test dataset

4. **Understand the changes**: Review what will happen:
   - Original content will be removed from parent
   - Subdatasets will depend on parent for content retrieval (origin remote)
   - Parent dataset must remain accessible for content access
   - Git history will be rewritten (irreversible without backup)
   - `.gitattributes` rules will be reconstructed (may affect behavior)

5. **Use verification**: Always run with `--check full` (default) to verify integrity

**Recovery**: If something goes wrong, restore from backup:
```bash
# Discard failed split attempt
cd /path/to/dataset
git reset --hard HEAD~N  # Reset to pre-split state
# Or completely restore from backup
rm -rf /path/to/dataset
datalad clone /path/to/backup /path/to/dataset
```

**When in doubt**:
- Use `--dry-run` first to see what would happen
- Ask for help on DataLad mailing list or GitHub
- Keep your backup until you've verified the split succeeded

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
- **--check {full,annex,tree,none}**: Post-split verification level (default: `full`)
  - `full`: Perform both annex and tree verification (default, recommended)
  - `annex`: Verify git-annex integrity and content accessibility
    * Run `git annex fsck` in split subdatasets
    * Verify all annexed files are accessible (locally or from remotes)
    * Check that location tracking is preserved correctly
  - `tree`: Verify directory tree structure matches original
    * Compare complete file tree across all split subdatasets
    * Ensure tree union matches original dataset tree
    * Detect any missing or extra files
  - `none`: Skip all verification checks (fast but risky)
- **--propagate-annex-config {all,common,none,SETTINGS}**: Control git config annex.* propagation (default: `common`)
  - `all`: Propagate all annex.* settings from parent to subdatasets
  - `common`: Propagate safe common settings (annex.addunlocked, annex.largefiles, annex.backend)
  - `none`: Don't propagate any annex.* settings
  - `SETTINGS`: Comma-separated list of specific settings (e.g., "annex.addunlocked,annex.backend")
  - Note: Repository-wide settings (`git annex config`) are handled automatically by git-annex filter-branch
- **--exclude-annex-config SETTINGS**: Exclude specific annex.* settings from propagation (comma-separated)
- **--interactive-config**: Interactively prompt for each annex.* setting to propagate
- **--clone-mode {clone,reckless-ephemeral,worktree}**: Control how subdataset repository is created (default: `clone`)
  - `clone`: Standard git clone approach - **default**
    * Full independent repository
    * Separate .git directory with own objects
    * Safe for production use
  - `reckless-ephemeral`: Share annex object store via symlink
    * Symlink .git/annex/objects to parent
    * Minimal overhead, not independent
    * Temporary working copies only
  - `worktree`: Use git worktree with namespace
    * Create as git worktree on branch in namespace
    * Share git objects and annex objects with parent
    * Most efficient, uses git namespaces for clean separation
    * Branch in namespace: `refs/namespaces/split/<hierarchical-path>`
    * Example: `data/subjects/subject01` → `refs/namespaces/split/data/subjects/subject01`
    * Preserves hierarchical structure, no path collapsing needed
- **--content {auto,copy,move,none}**: Control how annexed content is handled (default: `auto`)
  - `auto`: Automatic based on clone-mode - **default**
    * For `clone`: Use `none` (on-demand retrieval)
    * For `reckless-ephemeral`: Use `none` (shares annex via symlink)
    * For `worktree`: Use `none` (shares annex objects)
  - `none`: Don't copy content to subdataset
    * Retrieve on-demand via `datalad get` from origin
    * Most storage-efficient
  - `copy`: Copy present content from parent to subdataset
    * Only valid with `--clone-mode=clone`
    * Run `datalad get` in subdataset
    * Doubles storage (unless CoW filesystem)
  - `move`: Move content from parent to subdataset
    * Only valid with `--clone-mode=clone`
    * Use `git annex move --to <subdataset>`
    * Storage-efficient, subdataset becomes content holder
- **--preserve-branch-name**: Ensure branch name in subdataset matches parent (default: `true`)
  - Subdataset will have same branch checked out as parent had for that path
  - Important for workflows that depend on branch names
  - With worktree mode: Branch created under prefix, then checked out locally
- **--worktree-branch-prefix**: Prefix for worktree branches (default: `split/`)
  - Used with `--clone-mode=worktree` to organize split branches
  - Branch created as `<prefix><target_path>` (e.g., `split/data/subjects/subject01`)
  - Preserves hierarchical structure in branch names
  - Can be customized (e.g., `--worktree-branch-prefix=archive/` → `archive/data/subjects/subject01`)

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

# Skip verification for speed (use with caution)
datalad split --check none data/subject01

# Only verify annex integrity
datalad split --check annex data/subject01

# Full verification (default, recommended)
datalad split --check full data/subject01

# Propagate specific annex config settings
datalad split --propagate-annex-config="annex.addunlocked,annex.backend" data/subject01

# Interactive config propagation
datalad split --interactive-config data/subject01

# Don't propagate any annex config (manual configuration later)
datalad split --propagate-annex-config=none data/subject01

# Clone mode options (how to create subdataset repository)
# Default: standard clone (independent repository)
datalad split data/subject01

# Use git worktree (most efficient, shares git + annex objects)
datalad split --clone-mode=worktree data/subjects/subject01
# Creates branch: split/data/subjects/subject01 (preserves hierarchy)

# Custom branch prefix
datalad split --clone-mode=worktree --worktree-branch-prefix=archive/ data/old/study01
# Creates branch: archive/data/old/study01

# Reckless ephemeral mode (temporary working copy, shares annex via symlink)
datalad split --clone-mode=reckless-ephemeral data/subject01

# Content handling options (what to do with annexed content)
# Default: auto (none for worktree/reckless, none for clone)
datalad split data/subject01

# Copy present content to subdataset (only with clone mode)
datalad split --clone-mode=clone --content=copy data/subject01

# Move content from parent to subdataset (only with clone mode)
datalad split --clone-mode=clone --content=move data/subject01

# Explicit none (on-demand retrieval)
datalad split --clone-mode=clone --content=none data/subject01

# Combined: worktree mode with explicit content setting (content=auto → none)
datalad split --clone-mode=worktree --content=auto data/subjects/subject01
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

#### 2.1 Safety Warning Display
```python
def _display_safety_warning(dataset, paths, force=False):
    """
    Display critical safety warning before performing split.

    MUST be called before any destructive operations.

    Warning message should include:
    1. List of destructive operations that will be performed
    2. Recommendation to create backup first
    3. Note that operation is irreversible without backup
    4. Warning about potential behavior changes

    If not in force mode and not dry-run:
    - Display warning
    - Prompt user for confirmation: "Continue? [y/N]"
    - Abort if user doesn't confirm

    If --force flag is set:
    - Display warning (non-interactive)
    - Proceed automatically (user accepted responsibility)

    Example warning:
        WARNING: This operation will:
        - Rewrite git history (irreversible)
        - Filter git-annex metadata
        - Remove content from parent dataset
        - Reconstruct .gitattributes

        STRONGLY RECOMMENDED: Create a backup first!
          datalad clone --reckless availability . /path/to/backup

        Continue? [y/N]

    Documentation requirements:
    - Prominently display backup instructions in command help
    - Include warning in docstring
    - Reference full disclaimer in user documentation
    """
```

#### 2.2 Path Discovery & Validation
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

#### 2.3 Subdataset Discovery
```python
def _discover_subdatasets(dataset, path):
    """
    Recursively discover subdatasets under given path.
    Returns list ordered by depth (deepest first) for bottom-up processing.
    """
```

#### 2.4 History Filtering Workflow
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

#### 2.5 Subdataset Registration
```python
def _register_subdataset(parent_ds, subdataset_path):
    """
    Register newly created subdataset in parent:
    1. Initialize new dataset at target location
    2. Use datalad create --force to establish dataset
    3. Git add/commit in parent
    """
```

#### 2.6 Gitattributes Inheritance (CRITICAL)
```python
def _reconstruct_gitattributes(parent_ds, target_path, split_dataset_path):
    """
    CRITICAL: Reconstruct .gitattributes in split subdataset to preserve git/git-annex behavior.

    Git's .gitattributes inheritance behavior (validated via testing):
    - Per-attribute inheritance: Subdirectories inherit attributes from parent .gitattributes
      unless specifically overridden for that attribute
    - Proximity precedence: Closer .gitattributes files override more distant ones
    - Path-specific rules: Patterns like data/raw/** apply to matching paths
    - Subdirectories inherit from all .gitattributes files in parent directories

    Example from testing:
        Root .gitattributes:
            *.txt text eol=lf
            * annex.largefile=((mimeencoding=binary)and(largerthan=100kb))
            data/raw/** annex.largefiles=anything

        data/.gitattributes:
            *.txt text eol=crlf
            *.csv diff=csv

        Result for data/raw/nested.txt:
            text: set (from root *.txt)
            eol: crlf (from data/ *.txt, overrides root)
            annex.largefile: ((mimeencoding=binary)and(largerthan=100kb)) (from root *)
            annex.largefiles: anything (from root data/raw/**)

    Strategy for splitting data/raw/ into subdataset:

    1. Collect all .gitattributes from root down to target directory:
       - Read /.gitattributes
       - Read /data/.gitattributes
       - Read /data/raw/.gitattributes (if exists)

    2. Filter and adjust rules for each .gitattributes file:
       a. Wildcard rules (*, *.txt, etc.): Copy as-is
       b. Path-specific rules:
          - If path matches or is under target_path:
            * Strip target_path prefix
            * Example: "data/raw/**" → "**" when splitting data/raw/
            * Example: "data/*.csv" → SKIP (doesn't apply to data/raw/)
          - If path doesn't match target_path: SKIP

    3. Merge rules respecting precedence:
       - Start with rules from root
       - Layer on rules from intermediate directories (data/)
       - Layer on rules from target directory (data/raw/)
       - Closer directories override earlier ones (per-attribute)

    4. Write consolidated .gitattributes to split dataset root:
       - Include all applicable wildcard rules
       - Include adjusted path-specific rules
       - Maintain precedence order (later rules override earlier)

    5. Handle special cases:
       - If only wildcard rules (*), can copy parent .gitattributes as-is
       - If no .gitattributes in ancestry, no file needed
       - Preserve comments for documentation

    Parameters:
    - parent_ds: Parent dataset object
    - target_path: Path being split (e.g., "data/raw")
    - split_dataset_path: Path to split subdataset

    Returns:
    - gitattributes_content: String content of reconstructed .gitattributes
    - rules_applied: List of rules that apply to split content

    Example:
        Splitting data/raw/ with parent rules:
            Root: "*.dat filter=annex"
            Root: "data/raw/** annex.largefiles=anything"
            data/: "*.csv diff=csv"

        Result in data/raw/.gitattributes:
            *.dat filter=annex
            ** annex.largefiles=anything
            *.csv diff=csv

    References:
    - Git docs: https://git-scm.com/docs/gitattributes
    - Testing validated per-attribute inheritance and precedence behavior
    """
```

**Implementation Notes**:
- Use `git check-attr -a <file>` to verify reconstructed attributes match expected
- Test with both wildcard patterns and path-specific rules
- Preserve per-attribute precedence (don't just concatenate files)
- Consider `--preserve-gitattributes` flag to skip this step if user wants manual control

#### 2.7 Content Removal from Parent
```python
def _remove_content_from_parent(parent_ds, path):
    """
    Remove original content from parent dataset:
    1. git rm -r <path>/* (but keep the subdataset registration)
    2. Commit changes
    3. Optional: git annex forget to clean up parent's git-annex branch
    """
```

#### 2.8 Location Tracking Preservation (CRITICAL)
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
  - `--include-all-repo-config` handles repository-wide settings from `git annex config`
  - This includes special remote configs, trust settings, preferred content, etc.
- Update origin remote URL to absolute path of parent dataset
- **DO NOT** mark origin as dead or remove the remote
- Verify `git annex whereis` shows origin for tracked files
- Document that parent dataset must remain accessible for content retrieval
- Consider optional `--copy-content` flag for users who want "offline" split datasets

**Git-Annex Config Propagation**:

Repository-wide settings (handled by `git-annex filter-branch --include-all-repo-config`):
- Settings from `git annex config` (stored in git-annex branch)
- Special remote configurations
- Trust settings (trusted, semitrusted, untrusted repos)
- Preferred content expressions
- Required content settings
- Numcopies settings

Local git config annex.* settings (require explicit handling):
- `annex.addunlocked`: Controls whether files are added in unlocked mode
- `annex.largefiles`: Expression for which files go to annex vs git
- `annex.dotfiles`: Whether to annex dotfiles
- `annex.backend`: Default backend for storing file content
- `annex.thin`: Use hard links for unlocked files
- `annex.stalldetection`: Network stall detection settings
- `annex.retry`: Number of retries for failed transfers
- `annex.web-options`: Options for web special remote

Strategy for local git config propagation:
1. **Scan parent's git config** for annex.* settings:
   ```bash
   git config --local --get-regexp '^annex\.'
   ```

2. **Interactive mode** (default with `--interactive-config`):
   - Present user with list of parent's annex.* settings
   - Ask which to propagate to split subdatasets
   - Explain each setting's impact
   - Example: "Parent has annex.addunlocked=true. Apply to split subdataset? [Y/n]"

3. **Automatic propagation** (with `--propagate-annex-config all|common|none`):
   - `all`: Propagate all annex.* settings
   - `common`: Propagate common safe settings (addunlocked, largefiles, backend)
   - `none`: Don't propagate any (user manually configures later)
   - Default: `common`

4. **Explicit selection** (with `--propagate-annex-config="setting1,setting2"`):
   - User specifies exact settings to propagate
   - Example: `--propagate-annex-config="annex.addunlocked,annex.backend"`

5. **Exclusion** option: `--exclude-annex-config="setting1,setting2"`

Implementation:
```python
def _propagate_annex_config(parent_ds, split_ds, mode='common', explicit_settings=None):
    """
    Propagate annex.* git config settings to split subdataset.

    Note: git annex config settings are handled by git-annex filter-branch
    --include-all-repo-config. This function handles local git config only.
    """
```

**Documentation Requirements**:
- Explicitly state that `git annex config` (repository-wide) is handled by filter-branch
- Document which local settings are safe to propagate automatically
- Warn about settings that may need customization per subdataset
- Provide examples of common configuration scenarios

References:
- [git-annex filter-branch](https://git-annex.branchable.com/git-annex-filter-branch/)
- [git-annex-config](https://git-annex.branchable.com/git-annex-config/)
- [annex.largefiles configuration](https://git-annex.branchable.com/tips/largefiles/)
- [unlocked files configuration](https://github.com/RonnyPfannschmidt/git-annex/blob/master/doc/tips/unlocked_files.mdwn)

#### 2.9 Content Mode Handling (--content-mode option)
```python
def _handle_content_mode(parent_ds, split_ds, target_path, content_mode='nothing'):
    """
    Handle annexed content according to specified mode.

    IMPORTANT: This addresses the use case where parent dataset has
    annexed content present locally (e.g., locked under .git/annex).

    Parameters:
    - parent_ds: Parent dataset object
    - split_ds: Split subdataset object (after filtering)
    - target_path: Path that was split
    - content_mode: Strategy for handling content

    Modes:

    1. 'nothing' (default):
       - Do nothing - content not present in subdataset
       - Subdataset can retrieve on-demand via 'datalad get' from origin
       - Most storage-efficient
       - Implementation: Already handled by location tracking (section 2.8)

    2. 'copy':
       - Copy present content from parent to subdataset
       - Implementation:
         cd <split_ds>
         # Get list of annexed files
         annexed_files=$(git annex find)
         # For each file, copy from parent (origin)
         for file in $annexed_files; do
             datalad get "$file"
         done
       - Result: Content in both parent and subdataset
       - Storage: Doubles usage
       - Benefit: Subdataset is self-contained

    3. 'move':
       - Move content from parent to subdataset
       - Implementation:
         cd <parent_ds>
         # Initialize subdataset as git-annex remote
         cd <target_path>
         git annex init
         cd <parent_ds>
         git remote add subdataset-temp ./<target_path>
         # Move content for files under target_path
         git annex move --to subdataset-temp <target_path>/
         git remote remove subdataset-temp
       - Result: Content only in subdataset, parent knows location
       - Storage: No duplication
       - Benefit: Parent freed of content, subdataset becomes holder

    4. 'reckless-hardlink':
       - Hardlink content from parent to subdataset
       - Implementation:
         cd <split_ds>
         # For each annexed file
         annexed_files=$(git annex find)
         for file in $annexed_files; do
             key=$(git annex lookupkey "$file")
             parent_obj="<parent>/.git/annex/objects/.../SHA256-..."
             subds_obj=".git/annex/objects/.../SHA256-..."
             # Create hardlink
             mkdir -p $(dirname "$subds_obj")
             ln "$parent_obj" "$subds_obj"
             git annex fsck "$file"  # Update location tracking
         done
       - Result: Shared storage via hardlinks
       - Storage: No duplication (same inode)
       - WARNING: Modifications affect both datasets
       - Requirement: Same filesystem

    5. 'reckless-ephemeral':
       - Share entire annex object store via symlink
       - Implementation:
         cd <split_ds>
         rm -rf .git/annex/objects
         ln -s <parent>/.git/annex/objects .git/annex/objects
         # Keep separate annex metadata
       - Result: Complete sharing of object store
       - Storage: No duplication
       - WARNING: Not independent, relies on parent
       - Use case: Temporary working copies

    6. 'worktree':
       - Use git worktree instead of clone
       - Implementation (REPLACES the clone step in 2.4):
         cd <parent_ds>
         # Create branch with hierarchical name (preserves path structure)
         # Path: data/subjects/subject01 → Branch: split/data/subjects/subject01
         # Default prefix: "split/", configurable via --worktree-branch-prefix
         prefix="${worktree_branch_prefix:-split/}"
         branch_name="${prefix}${target_path}"
         git branch "$branch_name" HEAD
         # Remove from index (as in corrected workflow)
         git rm -r --cached <target_path>/
         # Remove physically
         rm -rf <target_path>
         # Create worktree
         git worktree add <target_path> "$branch_name"
         cd <target_path>
         # Filter as normal - annex symlinks will still work!
         git-annex filter-branch <target_path> --include-all-key-information --include-all-repo-config
         git filter-branch --subdirectory-filter <target_path> --prune-empty HEAD
         # Result: Worktree shares BOTH git objects AND annex objects
       - Result: **Most efficient approach**
       - Storage: Parent .git (~5.3M), Worktree .git (**4KB**), Annex fully shared
       - Branch organization: Hierarchical under prefix (e.g., split/data/subjects/...)
       - Benefit: Shares both git history and annex content
       - Why it works:
         * Git worktree shares .git/objects (standard worktree behavior)
         * Git branch names can contain slashes (feature/x, split/y, etc.)
         * After filtering, annex symlinks (../../../.git/annex/objects/...) still resolve to parent
         * No duplication of git OR annex content
         * Uses git's built-in mechanism - no manual symlink hacks
       - Note: **Validated in Experiment 12** - worktree overhead only 4KB vs 5.3M for clone
       - Constraint: Parent and subdataset must stay together (worktree dependency)

    Returns:
    - content_handled: Boolean indicating success
    - content_stats: Dict with storage info, file counts
    """
```

**Implementation Considerations**:

1. **Storage Impact Table** (validated in Experiment 12):
   ```
   Mode               | Parent Storage | Subdataset Storage | Total Impact        | Notes
   -------------------|----------------|--------------------|--------------------|-------------------
   nothing            | Unchanged      | 0                  | No increase         | Content on-demand
   copy               | Unchanged      | ~5.0M (100% dup)   | ~2x original        | CoW may reduce
   move               | Freed          | Original size      | No increase         | Transfers content
   reckless-hardlink  | Unchanged      | 0 (hardlinks)      | No increase*        | Same filesystem
   reckless-ephemeral | Unchanged      | 0 (symlink)        | No increase         | Shares annex
   worktree           | ~5.3M (shared) | 4KB (metadata)     | 4KB overhead only   | MOST EFFICIENT

   * Requires same filesystem
   ** Experiment 12: Parent 5.3M, Worktree 4KB, Annex fully shared via relative symlinks
   ```

2. **Independence Matrix**:
   ```
   Mode               | Dataset Independent? | Content Independent? | Safe for Production?
   -------------------|----------------------|----------------------|---------------------
   nothing            | Yes                  | N/A (on-demand)      | Yes
   copy               | Yes                  | Yes                  | Yes
   move               | Yes                  | Yes                  | Yes
   reckless-hardlink  | Yes (metadata)       | No (shared inodes)   | Use with caution
   reckless-ephemeral | No (shared annex)    | No                   | No (temp only)
   worktree           | Partial (branch)     | Partial (shared)     | Use with caution
   ```

3. **Selection Guidance**:
   - **Local dataset reorganization (RECOMMENDED)**: Use `worktree` - only 4KB overhead, shares everything
   - **Production datasets (distribution)**: Use `nothing` (default), `copy`, or `move`
   - **Development/testing**: Use `reckless-hardlink` or `worktree`
   - **Temporary analysis**: Use `reckless-ephemeral`
   - **Large datasets with limited storage**: Use `nothing` or `move` or `worktree`
   - **Offline subdatasets needed**: Use `copy`
   - **Subdatasets for distribution/publishing**: Use `clone` mode with appropriate content handling

4. **Validation Requirements**:
   - For all modes: Verify content accessibility post-split
   - For reckless modes: Display warning about implications
   - For worktree: Check git-annex compatibility
   - For hardlink: Verify same filesystem

#### 2.10 Post-Split Verification (--check option)
```python
def _verify_split(parent_ds, split_paths, check_level='full', original_tree_snapshot=None):
    """
    Verify the split operation completed successfully.

    Parameters:
    - parent_ds: Parent dataset object
    - split_paths: List of paths that were split into subdatasets
    - check_level: Verification level ('full', 'annex', 'tree', 'none')
    - original_tree_snapshot: Pre-split tree state for comparison

    Returns:
    - verification_results: Dict with verification status and details

    Raises:
    - VerificationError: If critical issues found during verification
    """
```

**Check Level: 'annex' - Git-Annex Integrity Verification**
```python
def _verify_annex_integrity(parent_ds, split_subdatasets):
    """
    Verify git-annex integrity and content accessibility.

    For each split subdataset:
    1. Run 'git annex fsck' to verify repository integrity
       - Check for corrupted objects
       - Verify key information consistency
       - Report any anomalies

    2. Verify content accessibility:
       - List all annexed files: git annex find
       - For each file, check locations: git annex whereis <file>
       - Ensure file is either:
         a. Present locally (--in=here), OR
         b. Available from at least one remote (origin or other)
       - Report files with no known locations (DATA LOSS!)

    3. Verify location tracking preservation:
       - Check origin remote is configured
       - Verify git annex whereis shows origin for files not present locally
       - Test sample retrieval: datalad get <sample-file>

    4. Check parent dataset:
       - Verify parent no longer tracks content in split paths
       - Verify parent's git-annex branch cleaned (optional: git annex unused)

    Returns:
    - annex_status: Dict with:
        * fsck_passed: Boolean
        * files_accessible: List of files with known locations
        * files_missing: List of files with NO known locations (critical!)
        * location_tracking_ok: Boolean
        * origin_configured: Boolean
        * sample_retrieval_test: Boolean

    Raises:
    - AnnexVerificationError: If files have no known locations (data loss)
    """
```

**Check Level: 'tree' - Directory Tree Verification**
```python
def _verify_tree_integrity(parent_ds, split_subdatasets, original_tree_snapshot):
    """
    Verify directory tree structure matches original dataset.

    Strategy:
    1. Capture original tree before split:
       - Use git ls-files to list all tracked files
       - Store paths and their git object hashes (for verification)
       - Optionally include annex keys for annexed files

    2. After split, reconstruct tree from:
       - Parent dataset (remaining files)
       - All split subdatasets (union of their contents)

    3. Compare original vs reconstructed:
       - Verify all original files present in union
       - Check for extra files (should not exist)
       - Verify file paths match (no renames/moves)
       - Optional: Verify object hashes match (content unchanged)

    4. Verify subdataset boundaries:
       - Ensure no file appears in multiple subdatasets
       - Ensure split paths cleanly partition the tree
       - Check that parent contains subdataset references, not content

    Parameters:
    - parent_ds: Parent dataset object
    - split_subdatasets: List of split subdataset paths
    - original_tree_snapshot: Pre-split tree state
        * Structure: {
            'files': {
                'path/to/file': {
                    'hash': 'git-object-hash',
                    'type': 'file|symlink|submodule',
                    'annex_key': 'SHA256-s...' (if annexed)
                }
            },
            'total_files': count,
            'total_annexed': count
        }

    Returns:
    - tree_status: Dict with:
        * files_in_original: count
        * files_in_union: count
        * files_missing: List[str] (files lost during split)
        * files_extra: List[str] (unexpected new files)
        * files_duplicated: List[str] (appears in multiple subdatasets)
        * tree_matches: Boolean

    Raises:
    - TreeVerificationError: If files are missing or duplicated
    """
```

**Check Level: 'full' - Combined Verification**
```python
def _verify_full(parent_ds, split_paths, original_tree_snapshot):
    """
    Run both annex and tree verification.

    Steps:
    1. Run tree verification first (faster, structural issues)
    2. If tree verification passes, run annex verification
    3. Combine results and report comprehensive status

    Returns:
    - combined_status: Dict with both annex_status and tree_status

    Raises:
    - VerificationError: If either verification fails
    """
```

**Check Level: 'none' - Skip Verification**
```python
# Simply return success without checks
# Log warning: "Skipping verification - data integrity not verified"
```

**Implementation Notes**:
- **Capture original tree state BEFORE split** (required for tree verification)
- Use `git ls-files -s` to get file list with modes and hashes
- For annexed files, use `git annex whereis --json` for machine-readable output
- Run fsck with `--fast` option by default (full fsck can be very slow)
- Provide detailed report on verification failures with remediation suggestions
- Consider `--check-sample N` option to only verify N random files (faster for large datasets)

**Error Handling**:
```python
class VerificationError(Exception):
    """Base class for verification failures."""
    pass

class AnnexVerificationError(VerificationError):
    """Git-annex integrity check failed."""
    pass

class TreeVerificationError(VerificationError):
    """Directory tree structure verification failed."""
    pass
```

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

3. **Gitattributes & Git Config Propagation** (CRITICAL)
   - `test_split_reconstructs_gitattributes`: **CRITICAL** - Verify .gitattributes reconstructed
     * Parent has root .gitattributes with wildcard rules (*.txt, *)
     * Parent has path-specific rules (data/raw/** annex.largefiles=anything)
     * data/ has .gitattributes with overrides (*.txt eol=crlf)
     * Split data/raw/ into subdataset
     * Verify split dataset has .gitattributes with:
       - Wildcard rules from root and data/ (with precedence)
       - Adjusted path-specific rules (data/raw/** → **)
     * Use `git check-attr` to verify attributes match expected
   - `test_split_gitattributes_wildcard_only`: Simple case with only * rules
     * Should copy parent .gitattributes as-is
   - `test_split_gitattributes_path_adjustment`: Path-specific rule adjustment
     * Verify data/raw/** becomes ** in split dataset
     * Verify data/*.csv is excluded (doesn't apply)
   - `test_split_gitattributes_no_ancestry`: No .gitattributes in parent
     * Split dataset should not have .gitattributes
   - `test_split_gitattributes_precedence`: Per-attribute precedence preserved
     * Root sets eol=lf, subdirectory overrides to eol=crlf
     * Verify subdirectory override is preserved in split
   - `test_split_annex_config_propagation_common`: **CRITICAL** - Test --propagate-annex-config=common
     * Parent has annex.addunlocked=true, annex.backend=SHA256
     * Split with default (common) propagation
     * Verify split dataset has same settings
     * Verify git annex config settings NOT copied (handled by filter-branch)
   - `test_split_annex_config_propagation_all`: Test --propagate-annex-config=all
     * Parent has various annex.* settings
     * Verify all are copied to split dataset
   - `test_split_annex_config_propagation_none`: Test --propagate-annex-config=none
     * Parent has annex.* settings
     * Verify split dataset has NO annex.* config
   - `test_split_annex_config_explicit_list`: Test explicit setting list
     * --propagate-annex-config="annex.addunlocked,annex.backend"
     * Verify only specified settings are propagated
   - `test_split_annex_config_exclude`: Test --exclude-annex-config
     * Propagate common settings but exclude specific one
   - `test_split_annex_config_vs_annex_config`: Verify distinction
     * Set both `git config annex.X=Y` and `git annex config annex.X=Z`
     * Verify git annex config handled by filter-branch
     * Verify git config handled by propagation logic

4. **Content Mode Handling (--content-mode)** (CRITICAL)
   - `test_split_content_mode_nothing`: **CRITICAL** - Default mode, on-demand retrieval
     * Split with --content-mode=nothing (default)
     * Verify content not present in subdataset initially
     * Verify datalad get retrieves from parent
     * Check git annex whereis shows origin
   - `test_split_content_mode_copy`: Copy content to subdataset
     * Parent has annexed content present locally
     * Split with --content-mode=copy
     * Verify content copied to subdataset
     * Verify content still in parent
     * Check storage doubled
   - `test_split_content_mode_move`: Move content to subdataset
     * Parent has annexed content present locally
     * Split with --content-mode=move
     * Verify content moved to subdataset
     * Verify content removed from parent
     * Check parent knows subdataset has content
     * Verify no storage increase
   - `test_split_content_mode_reckless_hardlink`: Hardlink content
     * Parent has annexed content present
     * Split with --content-mode=reckless-hardlink
     * Verify hardlinks created (same inode)
     * Verify no storage duplication
     * Check modifications affect both (WARNING test)
     * Verify requires same filesystem
   - `test_split_content_mode_reckless_ephemeral`: Share annex via symlink
     * Split with --content-mode=reckless-ephemeral
     * Verify .git/annex/objects is symlink to parent
     * Check content accessible in subdataset
     * Verify no independent annex
   - `test_split_content_mode_worktree`: Use git worktree
     * Split with --content-mode=worktree
     * Verify worktree created (not clone)
     * Check shared .git/objects with parent
     * Verify independent working tree
     * Test git-annex compatibility
   - `test_split_content_mode_storage_impact`: Verify storage calculations
     * Test each mode's storage impact matches specification
     * Verify Storage Impact Table accuracy
   - `test_split_content_mode_warnings`: Verify warnings displayed
     * reckless modes should display warnings
     * User should be informed of implications
   - `test_split_content_mode_validation`: Verify filesystem checks
     * hardlink mode should check same filesystem
     * worktree mode should verify git-annex support
   - `test_split_content_mode_mixed_content`: Handle partially present content
     * Parent has some content present, some not
     * Test each mode handles mixed scenario correctly

5. **Nested Subdatasets** (Phase 4 - .gitmodules reconstruction)
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

6. **Edge Cases**
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

7. **Configuration & Options**
   - `test_split_with_cfg_proc`: Apply configuration processors
   - `test_split_dry_run`: Verify no changes made in dry-run mode
   - `test_split_skip_rewrite`: Test incremental mode
   - `test_split_output_path`: Split to alternative location

8. **Post-Split Verification (--check option)** (CRITICAL)
   - `test_split_verification_full`: Default verification runs both annex and tree checks
   - `test_split_verification_annex`: Verify git-annex integrity
     * Run with `--check annex`
     * Verify git annex fsck executes in subdatasets
     * Check all files have known locations (local or remote)
     * Verify location tracking preserved (origin remote configured)
     * Test sample content retrieval from origin
     * Verify parent's annex branch cleaned
   - `test_split_verification_tree`: Verify tree structure matches
     * Run with `--check tree`
     * Capture tree snapshot before split
     * Compare original tree with union of (parent + subdatasets)
     * Verify no files missing
     * Verify no files duplicated across subdatasets
     * Verify parent contains submodule refs, not content
   - `test_split_verification_none`: Skip all verification
     * Run with `--check none`
     * Should complete quickly without running checks
     * Log warning about skipped verification
   - `test_split_verification_fails_on_missing_content`: **CRITICAL**
     * Simulate scenario where annexed content has no known locations
     * Verification should fail with AnnexVerificationError
     * Error message should list affected files
   - `test_split_verification_fails_on_tree_mismatch`: **CRITICAL**
     * Simulate scenario where files are lost during split
     * Verification should fail with TreeVerificationError
     * Error message should list missing files
   - `test_split_verification_report_format`: Verify report structure
     * Check verification results dict has expected keys
     * Verify status booleans are present
     * Check file lists are properly formatted
   - `test_split_verification_partial_failure`: Handle mixed results
     * Some subdatasets pass verification, others fail
     * Should report which subdatasets have issues
     * Provide actionable remediation suggestions

9. **Error Handling**
   - `test_split_missing_dataset`: No dataset found
   - `test_split_permission_error`: Insufficient permissions
   - `test_split_git_annex_unavailable`: Fallback behavior without git-annex

10. **Integration Tests**
   - `test_split_roundtrip`: Split then clone, verify content retrievable
   - `test_split_roundtrip_with_get`: Clone split dataset, run 'datalad get -r'
   - `test_split_with_remotes`: Verify remote operations still work
   - `test_split_workflow_scenario`: Complete realistic workflow
   - `test_split_parent_remains_accessible`: Verify parent dataset can serve content
   - `test_split_chained_retrieval`: Clone of split can retrieve from original via origin chain

11. **Performance Tests** (in `benchmarks/`)
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
