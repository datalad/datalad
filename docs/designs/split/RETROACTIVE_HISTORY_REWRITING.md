# Retroactive History Rewriting for Split - Design Document

> **IMPLEMENTATION STATUS**: ✅ **IMPLEMENTED** (top-level paths only)
>
> This design has been implemented as the `--mode=rewrite-parent` option in `datalad split`.
> Implementation uses manual git commit-tree approach (as validated in Experiment 17).
> See `datalad/distribution/split.py:_apply_rewrite_parent_simple()` and `_rewrite_history_with_commit_tree()`.
>
> **Current Limitation**: Only supports **top-level directories** (e.g., `data/`).
> Nested paths (e.g., `data/logs/`) require recursive tree manipulation - see Future Work section below.
> Experiments 18-19 validated nested support works; integration pending.

## Problem Statement

With the default `split-top` mode, `datalad split` rewrites history **independently** in each created subdataset, but does NOT rewrite the parent dataset's history. This means:

- **Subdataset**: Has clean history with only commits affecting its files
- **Parent**: Retains original commit history + new commit marking the split
- **No linkage**: Original parent commits don't reference the subdataset commits

Result: The repository structure appears as though the split happened at a single point in time, not as if subdatasets existed from the beginning.

## Desired Outcome

Make it appear as though subdatasets existed from the very beginning of the parent's history, with:

1. **Retroactive subdataset references**: Every commit in parent history that touched files in the split directory should reference the corresponding subdataset commit
2. **Proper gitlink commits**: Parent commits should have gitlinks (160000 mode entries) pointing to subdataset commits instead of tree entries
3. **Consistent history graph**: Parent and subdataset histories should be properly linked through the entire timeline

## Approach: Coordinated History Rewriting

### Phase 1: Map Commits Affecting Split Path

For each path being split:

1. **Identify relevant commits**: Walk parent's history and find all commits that:
   - Modified files under the split path
   - Are ancestors of HEAD
   - Are in topological order (parents before children)

2. **Build commit mapping**:
   ```python
   commit_map = {
       'parent_sha': {
           'split_path1': ['file1.txt', 'subdir/file2.txt'],  # Files touched
           'split_path2': ['data.csv']
       }
   }
   ```

### Phase 2: Rewrite Subdataset History with Stable SHAs

Currently: `git filter-branch --subdirectory-filter` creates new commits with new SHAs.

**Problem**: Parent needs to reference these commits, but SHAs are unpredictable.

**Solution**: Use `git filter-repo` or custom approach to:

1. Filter subdataset history
2. **Maintain commit timestamp and author** from original commits
3. Create deterministic mapping: `original_commit_sha -> subdataset_commit_sha`

```python
# For each original commit that touched split path
subdataset_sha_map = {}
for original_commit in commits_affecting_path:
    # Create filtered commit in subdataset
    filtered_commit = filter_tree_to_subdir(
        original_commit,
        path=split_path,
        preserve_metadata=True  # Same timestamp, author, message
    )
    subdataset_sha_map[original_commit.sha] = filtered_commit.sha
```

### Phase 3: Rewrite Parent History with Gitlinks

Walk through parent history in topological order, rewriting each commit:

```python
def rewrite_parent_commit(original_commit, split_paths):
    """Rewrite commit to replace directory trees with gitlinks."""

    new_tree = original_commit.tree.copy()

    for split_path in split_paths:
        if original_commit touched split_path:
            # Get corresponding subdataset commit
            subdataset_commit = subdataset_sha_map[original_commit.sha][split_path]

            # Remove tree entry for directory
            remove_tree_entry(new_tree, split_path)

            # Add gitlink (mode 160000) pointing to subdataset
            add_gitlink(new_tree, split_path, subdataset_commit.sha)

            # Update .gitmodules if this is the first commit affecting this path
            if is_first_commit_for_path(original_commit, split_path):
                update_gitmodules(new_tree, split_path)

    # Create new commit with rewritten tree
    new_commit = create_commit(
        tree=new_tree,
        parents=rewritten_parent_commits,
        author=original_commit.author,
        timestamp=original_commit.timestamp,
        message=original_commit.message
    )

    return new_commit
```

### Phase 4: Handle .gitmodules Evolution

Track when each subdataset path first appears in history:

```python
gitmodules_history = {}

for commit in topological_order(parent_commits):
    for split_path in split_paths:
        if is_first_commit_affecting(commit, split_path):
            # Add entry to .gitmodules for this commit and all descendants
            gitmodules_history[commit.sha] = {
                split_path: {
                    'path': split_path,
                    'url': f'./{split_path}',  # Relative URL
                }
            }
```

## Implementation Strategy

### Option A: Use git-filter-repo (Recommended)

`git-filter-repo` is the modern replacement for `git-filter-branch` with powerful features:

```python
import git_filter_repo as fr

# 1. Create subdataset with filtered history
def create_subdataset_with_history(parent_repo, split_path):
    # Clone parent
    subdataset_repo = clone(parent_repo, split_path)

    # Filter to only include split_path
    args = fr.FilteringOptions.parse_args([
        '--path', split_path,
        '--path-rename', f'{split_path}/:',  # Move to root
        '--force'
    ])
    fr.RepoFilter(args).run()

    # Build commit mapping: original -> filtered
    return build_commit_map(parent_repo, subdataset_repo, split_path)

# 2. Rewrite parent history with gitlinks
def rewrite_parent_with_gitlinks(parent_repo, split_paths, commit_maps):

    def blob_callback(blob, callback_metadata):
        # Modify .gitmodules content
        if blob.original_name == b'.gitmodules':
            # Update with subdataset entries
            pass

    def commit_callback(commit, callback_metadata):
        # Modify tree to replace directories with gitlinks
        tree_entries = parse_tree(commit.get_tree())

        for split_path in split_paths:
            if split_path in tree_entries:
                # Replace tree entry with gitlink
                subdataset_commit = commit_maps[split_path].get(commit.original_id)
                if subdataset_commit:
                    tree_entries[split_path] = fr.GitLink(
                        mode=b'160000',
                        sha=subdataset_commit.encode()
                    )

        commit.file_changes = rebuild_tree(tree_entries)

    args = fr.FilteringOptions.parse_args(['--force'])
    filter = fr.RepoFilter(
        args,
        blob_callback=blob_callback,
        commit_callback=commit_callback
    )
    filter.run()
```

### Option B: Manual Low-Level Approach

Use GitPython or dulwich for fine-grained control:

```python
from dulwich import porcelain
from dulwich.objects import Commit, Tree

def rewrite_commit_tree(repo, commit_sha, split_paths, subdataset_shas):
    """Rewrite a commit's tree to use gitlinks instead of tree entries."""

    commit = repo[commit_sha]
    tree = repo[commit.tree]

    # Build new tree with gitlinks
    new_entries = []
    for entry in tree.items():
        path, mode, sha = entry

        if path in split_paths:
            # Replace tree entry with gitlink (mode 160000)
            subdataset_sha = subdataset_shas[path][commit_sha]
            new_entries.append((path, 0o160000, subdataset_sha))
        else:
            new_entries.append((path, mode, sha))

    # Create new tree object
    new_tree = Tree()
    new_tree.items = new_entries
    new_tree_sha = repo.object_store.add_object(new_tree)

    # Create new commit with new tree
    new_commit = Commit()
    new_commit.tree = new_tree_sha
    new_commit.parents = [rewritten_parent_shas]  # Already rewritten parents
    new_commit.author = commit.author
    new_commit.committer = commit.committer
    new_commit.commit_time = commit.commit_time
    new_commit.author_time = commit.author_time
    new_commit.message = commit.message

    new_commit_sha = repo.object_store.add_object(new_commit)
    return new_commit_sha
```

## Corner Cases and Failure Conditions

### 1. Path Changes Type (Directory ↔ File)

**Scenario**: A path that becomes a subdataset was previously a file (or vice versa).

```
commit A: data.txt (file)
commit B: rm data.txt; mkdir data/; add data/file1.txt
commit C: split data/ -> subdataset
```

**Problem**: Cannot have both a file and gitlink at same path.

**Solution**: **FAIL** with clear error message:
```
Error: Cannot split 'data' - path changed from file to directory in history:
  - Commit abc123: data.txt (file)
  - Commit def456: data/ (directory)

This would create an inconsistent history. Options:
  1. Split from commit def456 onwards (use --start-commit=def456)
  2. Rename the file in older commits before splitting
```

### 2. Merge Commits with Conflicting Paths

**Scenario**: Merge commit where split path has conflicts.

```
branch A: data/file1.txt = "version A"
branch B: data/file1.txt = "version B"
merge M: resolved conflict in data/file1.txt
```

**Problem**: Merge commit references two parent subdataset commits that may conflict.

**Solution**: **Preserve merge structure** in subdataset:
```python
if commit.is_merge():
    # Subdataset should also have a merge commit
    subdataset_parents = [
        subdataset_sha_map[parent_sha]
        for parent_sha in commit.parents
    ]

    # Create merge commit in subdataset
    subdataset_merge = create_merge_commit(
        parents=subdataset_parents,
        tree=filtered_tree,
        message=commit.message
    )
```

### 3. Commits Affecting Multiple Split Paths

**Scenario**: Single commit modifies files in multiple directories being split.

```
commit A: Modified data1/file.txt AND data2/file.txt
split: data1/ -> subdataset1, data2/ -> subdataset2
```

**Solution**: **Create separate commits** in each subdataset:
```python
for split_path in split_paths:
    if commit_affects_path(commit, split_path):
        create_filtered_commit_in_subdataset(
            commit,
            split_path,
            timestamp=commit.timestamp,  # Same timestamp
            message=f"{commit.message}\n\n(Split from {commit.sha[:8]})"
        )
```

### 4. Empty Commits (No Changes to Split Path)

**Scenario**: Commit exists in parent but doesn't touch split path.

```
commit A: Modified root/file.txt (not in split path)
commit B: Modified data/file.txt (in split path)
```

**Solution**: **Skip in subdataset**, but maintain in parent:
```python
if not commit_affects_split_path(commit, split_path):
    # No entry in subdataset for this commit
    # Parent commit still exists, just doesn't update gitlink
    pass
```

### 5. Renamed/Moved Directories

**Scenario**: Split directory was previously at different path.

```
commit A: old_location/file.txt
commit B: git mv old_location new_location
commit C: split new_location/ -> subdataset
```

**Solution**: **FAIL** or **track renames**:

Option 1: **FAIL**
```
Error: Split path 'new_location' was previously at 'old_location' (commit abc123).
Retroactive split would lose history before rename.

Options:
  1. Use --follow-renames to track history through renames
  2. Split from commit abc123 onwards (use --start-commit=abc123)
```

Option 2: **Track renames** (advanced):
```python
path_history = track_path_renames(split_path)
# path_history = [
#     (commit_A, 'old_location'),
#     (commit_B, 'new_location'),
# ]

for commit in history:
    current_path = get_path_at_commit(split_path, commit)
    filter_using_path(commit, current_path)
```

## New Command Parameter

Add parameter to control history rewriting mode:

```python
rewrite_parent_history=Parameter(
    args=("--rewrite-parent-history",),
    action='store_true',
    doc="""Rewrite parent dataset history to make it appear as though
    subdatasets existed from the beginning. This creates gitlinks in
    historical commits pointing to corresponding subdataset commits.

    WARNING: This rewrites ALL commits in the parent's history, changing
    their SHAs. All clones must be re-created. Only use if you fully
    understand the implications.

    The operation will FAIL if:
    - Split path changed from file to directory (or vice versa)
    - History is too complex to rewrite safely

    Default: False (current behavior - only create new commit marking split)
    """)
```

## Testing Strategy

### Test Cases

1. **Simple linear history**:
   ```
   A - B - C - D  (master)
       |   └── modifies data/
       └── creates data/

   After split with --rewrite-parent-history:
   A - B' - C' - D'  (master, new SHAs)
       |    └── gitlink data -> c'
       └── gitlink data -> b'

   data (subdataset):
   b' - c'  (filtered commits)
   ```

2. **Merge commits**:
   ```
   A - B - D - F  (master)
    \     /
     C - E      (branch)

   Both branches modify data/, merge at F

   Result: Subdataset should also have merge
   ```

3. **Multiple split paths**:
   ```
   Commit modifies both data1/ and data2/
   Result: One commit in each subdataset
   ```

4. **Error cases**:
   - Path was file, then directory
   - Directory renamed
   - Complex conflicts

## Implementation Phases

### Phase 1: Basic Retroactive Split (MVP)
- Linear history only
- Single split path
- No renames, no type changes
- Fail on merge commits (for simplicity)

### Phase 2: Merge Support
- Handle merge commits properly
- Create merge commits in subdatasets
- Link through entire graph

### Phase 3: Multiple Paths
- Split multiple paths simultaneously
- Handle commits affecting multiple paths
- Coordinate .gitmodules updates

### Phase 4: Advanced Features
- Track renames with --follow-renames
- Handle type changes with --force-type-change
- Interactive mode to resolve conflicts

## References

- [git-filter-repo documentation](https://github.com/newren/git-filter-repo)
- [Git Internals - Git Objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)
- [Gitlinks and Submodules](https://git-scm.com/docs/gitmodules)
- [Git Filter-Branch Alternatives](https://github.com/newren/git-filter-repo#why-filter-repo-instead-of-other-alternatives)

## Experiments Needed

1. **Experiment 14**: Test `git-filter-repo` for creating stable commit mappings
   - Can we get deterministic SHA mappings?
   - How to preserve commit metadata exactly?

2. **Experiment 15**: Test gitlink creation in historical commits
   - Manually create commits with gitlinks
   - Verify git handles historical gitlinks correctly
   - Test checkout of old commits with subdatasets

3. **Experiment 16**: Test merge commit rewriting
   - Create test repo with merges affecting split path
   - Rewrite both parent and subdataset
   - Verify merge structure preserved

4. **Experiment 17**: Test failure cases
   - File → directory type change
   - Directory rename
   - Verify detection and error messages

## Decision Points

**Q1**: Should we use `git-filter-repo` or implement manually?
- **Recommendation**: Start with `git-filter-repo` - it's battle-tested and handles edge cases

**Q2**: Should retroactive rewriting be default or opt-in?
- **Recommendation**: **OPT-IN** (`--rewrite-parent-history`) because:
  - Changes all parent commit SHAs (breaking)
  - Complex operation with failure modes
  - Current behavior is safer and faster

**Q3**: How to handle path renames?
- **Recommendation**: Phase 1 should **FAIL** on renames, add `--follow-renames` in Phase 4

**Q4**: What to do with empty commits (no changes to split path)?
- **Recommendation**: Skip in subdataset, preserve in parent (don't update gitlink)

## Success Criteria

A retroactive split is successful if:

1. ✅ `git log` in subdataset shows only commits that modified its files
2. ✅ `git log` in parent shows same commits, but with gitlinks instead of tree entries
3. ✅ Checking out any historical commit in parent and running `git submodule update` successfully checks out corresponding subdataset state
4. ✅ All merge commits preserved with correct merge structure
5. ✅ `.gitmodules` appears in parent history at the point when subdataset path first appears
6. ✅ `git fsck` passes on both parent and subdataset
7. ✅ Content is identical at HEAD before and after split

## Implementation Status

✅ **Completed:**
1. ✅ Experiments 14-15: Validated git-filter-repo and manual gitlink approaches
2. ✅ Experiment 17: Validated simple rewrite-parent with git commit-tree (top-level only)
3. ✅ Experiments 18-19: Validated nested rewrite-parent with 3+ levels of nesting
4. ✅ Implemented `--mode=rewrite-parent` for top-level directories
5. ✅ Added comprehensive integration tests (3 tests, all passing)
6. ✅ Created `split_helpers_nested.py` module (349 lines, ready for integration)

## Future Work

### TODO: Nested Path Support for Rewrite-Parent Mode

**Priority**: High
**Effort**: 8-12 hours
**Status**: Experimentally validated, implementation ready

**Current Limitation:**

The `--mode=rewrite-parent` implementation only supports **top-level directories** (paths without slashes, e.g., `data/`). Nested paths like `data/logs/` or `images/adswa/` fail with:

```
NotImplementedError: Rewrite-parent mode does not yet support nested paths like 'data/logs/'.
```

**Why:**

The `git mktree` command only accepts single-level path entries. For nested paths, we need recursive tree manipulation:
1. Parse path into components (e.g., `['data', 'logs']`)
2. Build intermediate trees bottom-up
3. Replace deepest entry with gitlink
4. Propagate modified trees upward to root

**Solution:**

Integrate the existing `split_helpers_nested` module:

**Files Ready:**
- `datalad/distribution/split_helpers_nested.py` (349 lines) - Complete nested setup implementation
- `docs/designs/split/experiments/18_nested_rewrite_parent.sh` - Validation script (3+ levels tested)
- `docs/designs/split/experiments/NESTED_SUBDATASET_SETUP_PROCEDURE.md` - Complete procedure

**Integration Steps:**

1. **Extend tree building** in `_rewrite_history_with_commit_tree()`:
   ```python
   def _build_tree_with_nested_gitlink(parent_repo, orig_tree, path_components, gitlink_sha):
       """Recursively build tree with gitlink at nested path.

       For path 'data/logs/', components are ['data', 'logs']:
       1. Get 'data' tree from orig_tree
       2. Build new 'logs' tree with gitlink
       3. Build new 'data' tree containing new 'logs' tree
       4. Return new 'data' tree SHA to add to root
       """
   ```

2. **Post-rewrite setup** using `split_helpers_nested`:
   ```python
   from datalad.distribution.split_helpers_nested import setup_nested_subdatasets

   # After rewriting history
   setup_nested_subdatasets(
       parent_ds=ds,
       split_paths=['data/logs/', 'data/'],  # Bottom-up order
       filtered_repos={...},
       commit_maps={...}
   )
   ```

3. **Critical 3-step setup** (from experiments):
   - Step 1: Clone filtered repositories to their paths
   - Step 2: Checkout commits matching gitlinks
   - Step 3: **Initialize submodules** (often forgotten!)

**Testing Plan:**

Add integration tests:
```python
def test_rewrite_parent_mode_nested_2_levels():
    """Test rewrite-parent with data/logs/ structure."""

def test_rewrite_parent_mode_nested_3_levels():
    """Test rewrite-parent with data/logs/subds/ structure."""
```

**Validation:**

Experiments 18-19 successfully tested:
- 3+ levels of nesting (`data/logs/subds/`)
- Proper gitlink chains throughout history
- Correct commit filtering at each level
- Submodule initialization at all levels

**See:**
- `docs/designs/split/experiments/18_VERIFICATION_RESULTS.md` - Complete validation results
- `docs/designs/split/SPLIT_MODES.md` - Updated with limitation and future work section
