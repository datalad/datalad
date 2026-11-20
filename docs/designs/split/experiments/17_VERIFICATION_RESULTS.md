# Experiment 17: Verification Results

## Summary

**Status**: ✅ **COMPLETE SUCCESS** after fixing critical bug

**Date**: 2026-01-17

## Bug Discovery and Fix

### Initial Problem

User discovered that while the parent repository showed 4 commits with changing gitlinks for `data/`, the subdataset itself only had 1 commit:

```bash
# Parent history shows 4 commits
$ git log -p data
commit 1afdaa4... D: Add nested file in data
  diff --git a/data b/data
  -Subproject commit 7ba7b2b...
  +Subproject commit 3a8a506...

commit 7061bd3... C: Update data only
  ...

# But subdataset only has 1 commit!
$ git -C data log --stat
commit 20c188c...  # WRONG - this has root.txt (not filtered!)
  root.txt  | 1 +
  data/file.txt | 1 +
```

### Root Cause

In the commit mapping code (line 94-95 of original script):

```bash
# WRONG - includes ALL refs, both filtered and original
for commit in $(git log --all --format=%H); do
```

This picked up commits from `refs/original/refs/heads/master` (created by git-filter-branch) which were the **original unfiltered commits**, not the filtered ones.

### Fix Applied

Changed to only use the filtered branch:

```bash
# CORRECT - only filtered commits from master branch
for commit in $(git log master --format=%H --reverse); do
    commit_msg=$(git log -1 --format=%s $commit)

    # Match by message prefix
    case "$commit_msg" in
        "A:"*) COMMIT_MAP[A]=$commit ;;
        "B:"*) COMMIT_MAP[B]=$commit ;;
        "C:"*) COMMIT_MAP[C]=$commit ;;
        "D:"*) COMMIT_MAP[D]=$commit ;;
    esac
done
```

Added verification (lines 107-117):

```bash
# Verify these are filtered commits (should only have data/ content)
for label in A B C D; do
    sha=${COMMIT_MAP[$label]}
    if git ls-tree $sha | grep -q "root.txt"; then
        echo "✗ $label ($sha): ERROR - Still has root.txt (not filtered!)"
    else
        echo "✓ $label ($sha): Correctly filtered (no root.txt)"
    fi
done
```

Added comprehensive history verification (lines 413-498):

```bash
# Compare number of commits
orig_commits=$(git log --oneline original-history -- data | wc -l)
sub_commits=$(git -C data log --oneline | wc -l)

# Compare commit messages
# Compare file content at each commit
# Verify subdataset has COMPLETE history
```

## Verification Results (After Fix)

### 1. Commit Count Comparison

```
Original data/ history: 4 commits
Subdataset history: 4 commits
✓ Commit count matches!
```

### 2. Commit Message Comparison

| # | Original (data/) | Subdataset |
|---|------------------|------------|
| 1 | f0295a4 D: Add nested file in data | 3a8a506 D: Add nested file in data |
| 2 | 788efe8 C: Update data only | 7ba7b2b C: Update data only |
| 3 | 03b4d30 B: Update both | 41aab07 B: Update both |
| 4 | 113b838 A: Initial commit | 51f05bf A: Initial commit |

✓ All commit messages match perfectly

### 3. File Content Verification

```
✓ Commit A (113b838 → 51f05bf): file.txt matches
✓ Commit B (03b4d30 → 41aab07): file.txt matches
✓ Commit C (788efe8 → 7ba7b2b): file.txt matches
✓ Commit D (f0295a4 → 3a8a506): file.txt matches
✓ Commit D: subdir/nested.txt matches
```

### 4. Gitlink Verification in Rewritten Commits

All parent commits have proper gitlinks pointing to filtered subdataset commits:

```
✓ 1afea96: gitlink (mode 160000) → 51f05bfdc23710e4abfb4089faaaaef45b61342e (A)
✓ 5d73979: gitlink (mode 160000) → 41aab07a7048c29fa719ba9b5c3497c7e32fd3dd (B)
✓ 7061bd3: gitlink (mode 160000) → 7ba7b2b39d05ae7740e857cc79353bcba0394501 (C)
✓ 1afdaa4: gitlink (mode 160000) → 3a8a50601872ad033123b260df8c715610ffc771 (D)
```

### 5. Commit Mapping Verification

The commit mapping correctly identified filtered commits by message prefix:

```
Building commit map (by commit message from filtered branch):
  A → 51f05bfdc23710e4abfb4089faaaaef45b61342e (A: Initial commit)
  B → 41aab07a7048c29fa719ba9b5c3497c7e32fd3dd (B: Update both)
  C → 7ba7b2b39d05ae7740e857cc79353bcba0394501 (C: Update data only)
  D → 3a8a50601872ad033123b260df8c715610ffc771 (D: Add nested file in data)
```

All commits verified to be filtered (no root.txt):

```
✓ A (51f05bf): Correctly filtered (no root.txt)
✓ B (41aab07): Correctly filtered (no root.txt)
✓ C (7ba7b2b): Correctly filtered (no root.txt)
✓ D (3a8a506): Correctly filtered (no root.txt)
```

## Final Validation

✅ **VERIFICATION SUCCESSFUL!**

- ✓ Subdataset has COMPLETE history (4 commits)
- ✓ All commit messages match original data/ history
- ✓ File content matches at every historical point
- ✓ All gitlinks properly created (mode 160000)
- ✓ Gitlinks point to FILTERED commits (not original)

✅ **Proof of concept VALIDATED - rewrite-parent mode is FEASIBLE!**

## Key Lessons

1. **CRITICAL**: When building commit mappings, MUST use only the filtered branch (`master`), NOT `--all` which includes original refs

2. **CRITICAL**: Always verify subdataset history matches original `git log <subdir>` output:
   - Same number of commits
   - Same commit messages
   - Same file content at each point

3. **Verification is essential**: The bug was only caught by examining the actual subdataset history, not just looking at parent gitlinks

4. **Message-based mapping works**: Using commit message prefixes for mapping is reliable when timestamps might collide

## Implementation Recommendations

For production `rewrite-parent` implementation:

1. **Build commit mapping carefully**:
   ```python
   # After filtering subdataset
   filtered_commits = {}
   for commit in subdataset.iter_commits('master'):
       # Use message prefix or other unique identifier
       filtered_commits[commit.message.split(':')[0]] = commit.hexsha
   ```

2. **Verify mapping is complete**:
   ```python
   assert len(filtered_commits) == expected_count
   ```

3. **Verify each mapped commit is filtered**:
   ```python
   for sha in filtered_commits.values():
       tree = repo.commit(sha).tree
       assert 'root.txt' not in tree  # Should only have subdataset content
   ```

4. **Final verification** (as requested by user):
   ```python
   # Compare subdataset history to original path history
   orig_commits = list(repo.iter_commits('HEAD', paths=[subdir]))
   sub_commits = list(subdataset.iter_commits('master'))
   assert len(orig_commits) == len(sub_commits)
   # Verify messages and content match
   ```

## Files Modified

- `docs/designs/split/experiments/17_simple_rewrite_parent.sh`:
  - Fixed commit mapping (lines 89-117)
  - Added verification section (lines 413-498)

- `docs/designs/split/EXPERIMENT_SUMMARY.md`:
  - Updated verification results
  - Added critical bug documentation

## Location

Experiment results available at: `/tmp/experiment_17_simple_rewrite/parent`

To explore:
```bash
cd /tmp/experiment_17_simple_rewrite/parent

# View rewritten history
git log --oneline

# View gitlinks at each commit
git log -p data

# Verify subdataset history
git -C data log --oneline

# Compare to original
git log --oneline original-history -- data
```
