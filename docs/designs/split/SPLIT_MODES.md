# Split Modes - Detailed Design

This document describes the four operation modes for `datalad split` and how they handle parent dataset history.

## Overview

The `--mode` parameter controls how parent history is handled after splitting:

| Mode | Parent History | Subdataset History | Use Case | Destructive? |
|------|---------------|-------------------|----------|--------------|
| **split-top** | Preserved + new commit | Filtered | Default - safest | No |
| **truncate-top** | Orphan commit only | Filtered | Fresh start, no history | Yes |
| **truncate-top-graft** | Orphan + grafted | Filtered | Fresh start + optional history | Yes |
| **rewrite-parent** | Fully rewritten | Filtered | Retroactive split | Yes |

## Mode 1: split-top (Default)

### Description

Creates subdatasets with filtered history, adds a new commit to parent marking the split. **Parent history is NOT rewritten.**

### Behavior

```
Before split:
  A - B - C - D  (master, has data/ directory)

After split with --mode=split-top:
  A - B - C - D - E  (master, E = "Split data/ into subdataset")
                  └── data/ (submodule gitlink in E only)

  data/ subdataset:
  a - b - c - d  (filtered commits from A,B,C,D affecting data/)
```

### Characteristics

- ✅ **Safest**: No history rewriting, all original commits preserved
- ✅ **Fast**: Only filters subdataset, no parent rewriting
- ✅ **Non-destructive**: Can be easily reverted by removing submodule and checking out parent state before split
- ❌ **History inconsistency**: Original commits (A-D) still reference data/ as regular files, not as subdataset
- ❌ **No retroactive view**: Can't see subdataset structure in historical commits

### Implementation

```python
def perform_split_top_mode(ds, target_path, ...):
    """Current implementation - create subdataset and commit."""

    # 1. Remove from parent index
    ds.repo.call_git(['rm', '-r', '--cached', f'{target_path}/'])

    # 2. Remove physically
    shutil.rmtree(target_path)

    # 3. Create subdataset (clone/worktree/reckless)
    create_subdataset(ds, target_path, clone_mode, ...)

    # 4. Filter subdataset history
    filter_subdataset(target_path, ...)

    # 5. Register as submodule
    ds.repo.call_git(['submodule', 'add', f'./{target_path}', target_path])

    # 6. Commit in parent
    ds.save(message=f"Split {target_path} into subdataset")
```

### Use Cases

- Default for most users
- When you want to preserve all parent history unchanged
- When multiple people have clones of the repository
- When you want the split to be easily reversible

## Mode 2: truncate-top

### Description

Creates subdatasets with filtered history, but **discards all parent history**, creating an orphan commit.

### Behavior

```
Before split:
  A - B - C - D  (master, has data/ directory)

After split with --mode=truncate-top:
  E  (master, orphan commit with no parents)
  └── data/ (submodule gitlink)

  Commits A, B, C, D are unreferenced (can be garbage collected)

  data/ subdataset:
  a - b - c - d  (filtered commits)
```

### Characteristics

- ✅ **Clean slate**: No historical baggage
- ✅ **Smaller repository**: After cleanup, unreferenced commits are removed
- ✅ **Consistent structure**: Only one commit, subdataset exists from the start
- ❌ **Destroys history**: All prior commits are lost (unless --cleanup=none)
- ❌ **Breaking change**: Anyone with clones must re-clone

### Implementation

```python
def perform_truncate_top_mode(ds, target_path, ...):
    """Create orphan commit discarding all history."""

    # 1-4: Same as split-top (create and filter subdataset)
    create_and_filter_subdataset(ds, target_path, ...)

    # 5. Get current tree state
    current_tree = ds.repo.call_git(['write-tree']).strip()

    # 6. Create orphan commit (no parents)
    message = f"Split {target_path} into subdataset\n\nAll prior history truncated."

    orphan_commit = ds.repo.call_git([
        'commit-tree',
        '-m', message,
        current_tree
    ]).strip()

    # 7. Force-update branch to orphan commit
    current_branch = ds.repo.get_active_branch()
    ds.repo.call_git(['update-ref', f'refs/heads/{current_branch}', orphan_commit])

    # 8. Reset to orphan commit
    ds.repo.call_git(['reset', '--hard'])
```

### Use Cases

- Starting fresh with a reorganized structure
- Repository has grown too large due to history
- History is not valuable (e.g., experimental repository)
- Creating a clean release point

### Warnings

User must confirm they understand:
```
WARNING: This will DELETE ALL HISTORY in the parent repository!

Current history:
  - 1234 commits
  - Earliest: 2020-01-15 (5 years ago)
  - Latest: 2025-01-17

After truncate-top:
  - 1 commit (orphan)
  - All history removed

This operation:
  ✗ CANNOT be undone without a backup
  ✗ Requires all users to re-clone
  ✗ Breaks all existing references

Type 'DELETE HISTORY' to confirm: ____
```

## Mode 3: truncate-top-graft

### Description

Like `truncate-top`, but preserves full history in a separate branch and uses `git replace` to graft it, allowing optional access to full history.

### Behavior

```
Before split:
  A - B - C - D  (master)

After split with --mode=truncate-top-graft:
  E  (master, orphan commit)
  └── data/ (submodule gitlink)

  A - B - C - D - E'  (master-split-full, preserved full history)

  git replace refs:
  E --> E'  (grafts full history to orphan commit)

  When viewed with git replace:
  A - B - C - D - E  (appears as continuous history)
```

### Characteristics

- ✅ **Clean default view**: Only one commit visible by default
- ✅ **Full history available**: Can access via `git log --no-replace-objects` or checking out `{branch}-split-full`
- ✅ **Best of both worlds**: Clean for daily use, history available when needed
- ❌ **Replace objects complexity**: Users must understand git replace mechanism
- ❌ **Larger .git**: Full history still stored (but can be in separate clone)

### Implementation

```python
def perform_truncate_top_graft_mode(ds, target_path, ...):
    """Create orphan commit with grafted full history."""

    # 1-4: Create and filter subdataset
    create_and_filter_subdataset(ds, target_path, ...)

    # 5. Save current branch and HEAD
    current_branch = ds.repo.get_active_branch()
    old_head = ds.repo.get_hexsha()

    # 6. Create preservation branch with full history
    full_history_branch = f"{current_branch}-split-full"
    ds.repo.call_git(['branch', full_history_branch, old_head])

    # 7. Create orphan commit (same as truncate-top)
    current_tree = ds.repo.call_git(['write-tree']).strip()

    message = f"""Split {target_path} into subdataset

Orphan commit with no direct parents.
Full history preserved in branch: {full_history_branch}

Use 'git log --no-replace-objects' to see only this commit.
Use 'git log' (default) to see grafted full history.
"""

    orphan_commit = ds.repo.call_git([
        'commit-tree',
        '-m', message,
        current_tree
    ]).strip()

    # 8. Update current branch to orphan
    ds.repo.call_git(['update-ref', f'refs/heads/{current_branch}', orphan_commit])

    # 9. Create graft using git replace
    # Makes orphan_commit appear to have old_head as parent
    ds.repo.call_git(['replace', '--graft', orphan_commit, old_head])

    # 10. Reset working tree
    ds.repo.call_git(['reset', '--hard'])

    lgr.info(f"Full history preserved in branch: {full_history_branch}")
    lgr.info(f"Graft created: {orphan_commit[:8]} appears to have parent {old_head[:8]}")
```

### Git Replace Mechanism

```bash
# View orphan commit only (no graft)
git log --no-replace-objects

# View with grafted history (default)
git log

# View full history branch
git log master-split-full

# Remove graft (shows orphan again)
git replace -d <orphan-commit>

# Export/import replace refs (for sharing)
git push origin refs/replace/*
git fetch origin refs/replace/*:refs/replace/*
```

### Use Cases

- Want clean current state but preserve history for reference
- Large repository where most users don't need full history
- Creating a "release" version with optional development history
- Regulatory/compliance requires history preservation but want clean daily use

### Notes

- Replace refs are local by default (must be explicitly pushed/fetched)
- Can create multiple grafts for different historical views
- Graft can be removed at any time to see true orphan commit

## Mode 4: rewrite-parent

### Description

Rewrites entire parent history to make subdatasets appear as if they existed from the beginning, with proper gitlinks throughout history.

See **[RETROACTIVE_HISTORY_REWRITING.md](RETROACTIVE_HISTORY_REWRITING.md)** for complete design.

### Behavior

```
Before split:
  A - B - C - D  (master)
  └── all commits have data/ as regular tree entries

After split with --mode=rewrite-parent:
  A' - B' - C' - D'  (master, ALL commits have NEW SHAs)
   └── all commits have data/ as gitlink (mode 160000)

  data/ subdataset:
  a - b - c - d  (filtered commits)

  Parent commit mapping:
  A -> A' (A' has gitlink to commit 'a')
  B -> B' (B' has gitlink to commit 'b')
  C -> C' (C' has gitlink to commit 'c')
  D -> D' (D' has gitlink to commit 'd')
```

### Characteristics

- ✅ **Consistent history**: Subdatasets appear throughout entire history
- ✅ **Historical correctness**: `git checkout` any commit works with subdatasets
- ✅ **Proper structure**: .gitmodules appears in history when subdatasets first appear
- ❌ **Changes ALL SHAs**: Every commit in parent gets new SHA
- ❌ **Breaking change**: All clones must be re-created
- ❌ **Complex operation**: Can fail on complex histories (merges, renames, etc.)

### Implementation

See RETROACTIVE_HISTORY_REWRITING.md for detailed implementation using `git-filter-repo` or manual approach.

### Use Cases

- Want historical accuracy (subdatasets should have always existed)
- Repository will be archived/released and structure should be "correct"
- Creating reference implementation for others to clone
- Willing to accept breaking change for historical consistency

### Implementation Status

> **Implementation Status**: ✅ **FULLY IMPLEMENTED** (including nested paths)

**Nested Path Support** (v2.0):

The `--mode=rewrite-parent` now supports both **top-level** and **nested paths** using recursive tree building:

**All of these work:**
```bash
datalad split --mode=rewrite-parent data/              # ✓ Top-level directory
datalad split --mode=rewrite-parent images/adswa/      # ✓ Nested path (adswa/ becomes subdataset, images/ stays directory)
datalad split --mode=rewrite-parent data/logs/raw/     # ✓ Deeply nested path
```

**Important distinction:**
- `split images/adswa/` → Creates **1 subdataset** (only adswa/), images/ stays a regular directory
- `split images/ images/adswa/` → Creates **nested subdatasets** (images/ is subdataset containing adswa/ subdataset)

**How it works:**

The implementation uses bottom-up recursive tree building to handle nested paths:

1. Parse path into components (e.g., `'data/logs/'` → `['data', 'logs']`)
2. Navigate down tree hierarchy: root → data/ → logs/
3. Build new data/ tree with logs/ replaced by gitlink (160000 mode)
4. Build new root tree with data/ replaced by modified data/ tree (stays regular tree, NOT gitlink)
5. Create commit with new root tree

Only the specified path becomes a subdataset; parent directories remain regular trees.

Algorithm validated in Experiment 20 and implemented in `_build_tree_with_nested_gitlink()`.

**Technical Solution:**

Git's `mktree` command only accepts single-level paths without slashes. For nested paths, the implementation:
- Uses `git ls-tree` to navigate down the tree hierarchy
- Builds intermediate trees from deepest level upward
- Each level uses `git mktree` only on single-level entries (no slashes)
- Returns modified root tree with nested gitlink incorporated

### Current Limitations

**Post-Rewrite Setup** (Partial Implementation):

The tree building and history rewriting fully support nested paths. However, the post-rewrite subdataset setup currently uses a simplified approach:

**What works:**
- ✅ History rewriting with nested gitlinks throughout all commits
- ✅ Correct tree structures with gitlinks at arbitrary nesting depths
- ✅ Filtered subdataset repositories in correct locations
- ✅ Basic .gitmodules entries

**What's TODO:**
- ⏳ Full 3-step nested subdataset initialization (clone → checkout → submodule init)
- ⏳ .gitmodules placement at parent directory level (currently at root)
- ⏳ Verification of submodule status (`git submodule status` should not show '-' prefix)

For production use with complex nested hierarchies, the `split_helpers_nested` module integration provides complete setup.

### Future Work

**TODO: Complete split_helpers_nested Integration** (Priority: Medium, Effort: 2-4 hours)

Integrate the full 3-step setup procedure for nested subdatasets:

**Experimental Validation:**
- ✅ Experiments 16-19 successfully validated nested rewrite-parent with 3+ nesting levels
- ✅ `split_helpers_nested.py` (349 lines) implements complete nested setup procedure
- ✅ Production-ready approach documented in `experiments/NESTED_SUBDATASET_SETUP_PROCEDURE.md`

**Remaining Implementation Tasks:**
1. ✅ ~~Extend `_rewrite_history_with_commit_tree()` to handle recursive tree manipulation~~ DONE
2. ✅ ~~For nested paths, build intermediate trees bottom-up before creating commit~~ DONE
3. ⏳ Integrate `split_helpers_nested.setup_nested_subdatasets()` for post-rewrite setup
4. ⏳ Add 3-step setup: clone → checkout → submodule init (critical!)
5. ⏳ Process multiple nested paths in bottom-up order (deepest first)

**Key Technical Requirement:**

The experiments revealed that proper nested subdataset setup requires THREE steps (not two!):
1. Clone filtered repositories to their paths ✅ (basic version done)
2. Checkout commits matching gitlinks in parent ✅ (basic version done)
3. **Initialize submodules in .git/config** ⏳ (needs split_helpers_nested integration)

Missing step 3 results in uninitialized submodules (shown with '-' prefix in `git submodule status`).

**Testing:**
- ✅ Add integration test for nested path (`images/adswa/`) - single subdataset at nested location
- ⏳ Add integration test for deeply nested path (`data/logs/raw/`) - single subdataset 3+ directories deep
- ⏳ Add integration test for true nested subdatasets (split both parent and child paths)
- ⏳ Verify gitlink placement throughout history at correct tree levels
- ⏳ Verify submodule initialization for nested subdatasets

**See Also:**
- `datalad/distribution/split_helpers_nested.py` - Implementation ready for integration
- `docs/designs/split/experiments/18_VERIFICATION_RESULTS.md` - Validated true nested subdatasets (data/ → logs/ → subds/)
- `docs/designs/split/experiments/NESTED_SUBDATASET_SETUP_PROCEDURE.md` - Complete 3-step procedure
- `docs/designs/split/experiments/20_nested_tree_building_experiment.sh` - Tree building algorithm validation

## Cleanup Operations

The `--cleanup` parameter controls post-split cleanup to reclaim disk space.

### Cleanup Levels

#### none (default)

No cleanup performed. Safest option.

- Unreferenced commits remain in `.git/objects/`
- Reflog entries preserved
- Annex objects remain even if unused

**Use when:**
- Want to keep ability to recover
- Unsure if operation was successful
- Need to verify results first

#### reflog

Expire reflog entries for removed history.

```bash
git reflog expire --expire=now --all
```

- Removes reflog entries pointing to old commits
- Makes old commits eligible for garbage collection
- **Does not** actually remove objects yet

**Use when:**
- Using truncate-top or rewrite-parent modes
- Want to prevent accidental recovery of old commits
- Preparing for garbage collection

#### gc

Run git garbage collection to remove unreferenced objects.

```bash
git gc --aggressive --prune=now
```

- Removes unreferenced objects from `.git/objects/`
- Repacks remaining objects for efficiency
- Reclaims disk space

**Use when:**
- After reflog expiration
- Want to actually reclaim space
- Sure the operation was successful

#### annex

Clean up unused git-annex objects.

```bash
git annex unused
git annex drop --unused --force
```

- Identifies annex objects not referenced by any commits
- Drops unused objects from local annex
- Reclaims `.git/annex/objects/` space

**Use when:**
- Repository uses git-annex
- After truncate-top or rewrite-parent (old commits reference annex objects)
- Want to reclaim annex storage

#### all

Performs all cleanup operations in order:

1. Expire reflog
2. Run git gc
3. Clean annex (if present)

**Use when:**
- Certain operation was successful
- Want maximum space reclamation
- Not planning to recover old history

### Cleanup Timing

```python
def perform_cleanup(ds, cleanup_level, is_annex):
    """Perform cleanup operations based on level."""

    if cleanup_level == 'none':
        return

    actions = []

    if cleanup_level in ('reflog', 'all'):
        actions.append('reflog')

    if cleanup_level in ('gc', 'all'):
        actions.append('gc')

    if cleanup_level in ('annex', 'all') and is_annex:
        actions.append('annex')

    for action in actions:
        if action == 'reflog':
            lgr.info("Expiring reflog entries...")
            ds.repo.call_git(['reflog', 'expire', '--expire=now', '--all'])

        elif action == 'gc':
            lgr.info("Running garbage collection...")
            ds.repo.call_git(['gc', '--aggressive', '--prune=now'])

        elif action == 'annex':
            lgr.info("Cleaning unused annex objects...")
            # List unused
            unused_output = ds.repo.call_annex(['unused'])

            # Drop unused
            if 'unused' in unused_output.lower():
                ds.repo.call_annex(['drop', '--unused', '--force'])
```

### Space Reclamation Examples

```bash
# Example repository before split (100 commits, 50MB annex):
.git/objects/: 10MB
.git/annex/objects/: 50MB
Total: 60MB

# After split with --mode=truncate-top --cleanup=none:
.git/objects/: 10MB (old commits still present)
.git/annex/objects/: 50MB (old annex objects still present)
Total: 60MB (no savings)

# After split with --mode=truncate-top --cleanup=all:
.git/objects/: 100KB (only orphan commit + subdataset metadata)
.git/annex/objects/: 5MB (only objects referenced by orphan commit)
Total: 5.1MB (91% savings!)
```

## Mode Comparison Matrix

| Feature | split-top | truncate-top | truncate-top-graft | rewrite-parent |
|---------|-----------|--------------|-------------------|----------------|
| Parent history preserved | ✅ Yes | ❌ No | ⚠️ Separate branch | ⚠️ Rewritten |
| Parent commit SHAs change | ❌ No | ✅ Yes (orphan) | ✅ Yes (orphan) | ✅ Yes (all) |
| Subdatasets in old commits | ❌ No | N/A | N/A | ✅ Yes |
| Breaking change | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| Space savings (with cleanup) | None | High | Medium | Low |
| Complexity | Low | Low | Medium | High |
| Risk of failure | Low | Low | Low | Medium-High |
| Recommended for | Default | Fresh start | Best of both | Historians |

## Mode Selection Guide

### Use split-top (default) when:
- ✅ First time using split
- ✅ Multiple users have clones
- ✅ Want safest option
- ✅ History is valuable
- ✅ Want reversible operation

### Use truncate-top when:
- ✅ History is not needed
- ✅ Want smallest possible repository
- ✅ Starting fresh project phase
- ✅ Repository is too large due to history
- ❌ But be sure you don't need history!

### Use truncate-top-graft when:
- ✅ Want clean current state
- ✅ But want history accessible if needed
- ✅ Daily users don't need history
- ✅ Occasional deep dives into history
- ✅ Compliance requires history preservation

### Use rewrite-parent when:
- ✅ Want historically correct structure
- ✅ Creating canonical/reference repository
- ✅ Willing to accept breaking change
- ✅ Repository has simple linear history
- ❌ History has complex merges/renames (may fail)

## Safety Recommendations

1. **Always create a backup** before using any mode other than split-top
   ```bash
   git clone /path/to/dataset /backup/dataset
   ```

2. **Test with --dry-run** first
   ```bash
   datalad split --mode=truncate-top --dry-run data/
   ```

3. **Start with --cleanup=none**, verify, then run cleanup separately
   ```bash
   # First run
   datalad split --mode=truncate-top --cleanup=none data/

   # Verify results...

   # Then cleanup
   datalad split --mode=truncate-top --cleanup=all data/  # Will skip if already split
   ```

4. **For destructive modes, require explicit confirmation**
   - User must type exact phrase (not just 'yes')
   - Display what will be lost
   - Show space that will be reclaimed

## Examples

### Example 1: Default safe split
```bash
datalad split data/subjects/sub01
# Mode: split-top (default)
# Cleanup: none (default)
# Result: Subdataset created, parent history unchanged
```

### Example 2: Fresh start with cleanup
```bash
datalad split --mode=truncate-top --cleanup=all data/subjects/sub01
# Creates orphan commit, removes all history
# Reclaims maximum space
```

### Example 3: Clean view with history preservation
```bash
datalad split --mode=truncate-top-graft data/subjects/sub01

# View current (clean)
git log
# Shows: orphan commit (appears to have full history via graft)

# View only orphan
git log --no-replace-objects
# Shows: single orphan commit

# View full preserved history
git log master-split-full
# Shows: complete original history
```

### Example 4: Retroactive split
```bash
datalad split --mode=rewrite-parent data/subjects/sub01
# Rewrites ALL parent commits
# All SHAs change
# Subdatasets appear throughout history
```

## Implementation Notes

Each mode requires different implementation:

- **split-top**: Current implementation (already done)
- **truncate-top**: Add orphan commit creation
- **truncate-top-graft**: Add branch preservation + git replace
- **rewrite-parent**: Use git-filter-repo or custom tree rewriting (see RETROACTIVE_HISTORY_REWRITING.md)

Cleanup is orthogonal and works with all modes.

## Testing Strategy

Each mode needs comprehensive tests:

1. **Functional tests**:
   - Verify correct behavior
   - Check subdataset created properly
   - Validate parent state

2. **History tests**:
   - Verify commit graph structure
   - Check SHAs (changed vs unchanged)
   - Validate gitlinks at expected points

3. **Cleanup tests**:
   - Measure space before/after
   - Verify objects removed
   - Check annex cleanup

4. **Recovery tests**:
   - For split-top: verify reversibility
   - For others: verify backup can restore

5. **Edge case tests**:
   - Empty history
   - Single commit
   - Complex merges (should fail for rewrite-parent)
   - Multiple split paths
