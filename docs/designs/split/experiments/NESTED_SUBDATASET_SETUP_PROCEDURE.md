# Complete Nested Subdataset Setup Procedure

## Critical Discovery

After rewriting parent history with gitlinks, you **MUST** properly set up the subdatasets. This involves THREE distinct steps:

1. **Clone** the filtered subdatasets into their paths
2. **Checkout** the correct commits (matching gitlinks)
3. **Initialize** the submodules in git config

**Missing step 3 will result in uninitialized submodules** (shown with `-` prefix in `git submodule status`).

## Complete Setup Procedure

### Phase 1: Rewrite History with Gitlinks

```bash
# Already done by rewrite-parent implementation
# - Filter all subdatasets (bottom-up)
# - Build commit mappings
# - Rewrite intermediate levels with child gitlinks
# - Rewrite parent with top-level gitlinks
# Result: Parent history has gitlinks, .gitmodules in trees
```

### Phase 2: Set Up Physical Subdatasets

For each split path (deepest first):

```bash
# Example for data/logs/subds/ (deepest level)

# Get the gitlink SHA for this path from its parent level
cd parent/data/logs
SUBDS_GITLINK=$(git ls-tree HEAD | grep "	subds$" | awk '{print $3}')

# Clone the filtered repository
git clone /path/to/data-logs-subds-filtered subds

# Checkout the correct commit
cd subds
git checkout $SUBDS_GITLINK

# Verify
if [ "$(git rev-parse HEAD)" != "$SUBDS_GITLINK" ]; then
    echo "ERROR: Gitlink mismatch!"
    exit 1
fi
```

Repeat for each level:
- `data/logs/subds/` (deepest)
- `data/logs/`
- `data/`

### Phase 3: Initialize Submodules in Git Config

**CRITICAL:** After physical setup, initialize submodules at each level:

```bash
# At parent level
cd parent
git submodule init      # Adds [submodule "data"] to .git/config
git submodule sync      # Syncs URLs

# At data/ level
cd data
git submodule init      # Adds [submodule "logs"] to data/.git/config
git submodule sync

# At data/logs/ level
cd logs
git submodule init      # Adds [submodule "subds"] to data/logs/.git/config
git submodule sync

cd ../../..  # Back to parent
```

### Phase 4: Verification

After complete setup, verify ALL aspects:

```bash
# 1. Check .git directories exist
find . -name ".git" -type d
# Expected: ./.git, ./data/.git, ./data/logs/.git, ./data/logs/subds/.git

# 2. Check .gitmodules files
find . -name ".gitmodules" -type f
# Expected: ./.gitmodules, ./data/.gitmodules, ./data/logs/.gitmodules

# 3. Check submodule initialization (NO '-' prefix!)
git submodule status --recursive
# Expected output (note: SPACE before SHA, not '-'):
#  7e364c2... data (...)
#  33d7de1... data/logs (...)
#  97efb9b... data/logs/subds (...)

# 4. Check .git/config entries
grep '\[submodule' .git/config
grep '\[submodule' data/.git/config
grep '\[submodule' data/logs/.git/config
# Each should have appropriate [submodule "..."] section

# 5. Verify gitlinks match actual commits
PARENT_DATA=$(git ls-tree HEAD | grep "	data$" | awk '{print $3}')
ACTUAL_DATA=$(cd data && git rev-parse HEAD)
[ "$PARENT_DATA" = "$ACTUAL_DATA" ] && echo "✓ data/ OK" || echo "✗ data/ FAIL"

# 6. Test submodule update
git submodule update --init --recursive
# Should succeed without errors
```

## What Each Step Does

### Step 1: `git clone`
- Creates `.git` directory
- Populates git objects
- Creates working directory files

### Step 2: `git checkout <sha>`
- Updates HEAD to specific commit
- Updates working directory to match

### Step 3: `git submodule init`
- Reads `.gitmodules` from current commit
- Writes `[submodule "..."]` section to `.git/config`
- Marks submodule as "initialized"

### Step 4: `git submodule sync`
- Updates URLs in `.git/config` to match `.gitmodules`
- Ensures consistency

## Common Mistakes

### ❌ WRONG: Skip submodule init

```bash
# Clone and checkout only
git clone filtered data
cd data && git checkout $SHA

# Result: git submodule status shows '-' prefix
# git submodule update will fail or behave incorrectly
```

### ❌ WRONG: Only init at parent level

```bash
# Only initialize at parent
cd parent
git submodule init

# Nested levels (data/, data/logs/) NOT initialized!
# Their submodules will show '-' prefix
```

### ✅ CORRECT: Initialize at ALL levels

```bash
# Initialize at each level
cd parent && git submodule init && git submodule sync
cd data && git submodule init && git submodule sync
cd logs && git submodule init && git submodule sync
cd ../../..
```

## Implementation Checklist

For `datalad split --mode=rewrite-parent` implementation:

```python
def setup_nested_subdatasets(parent_path, split_paths, filtered_repos, commit_maps):
    """
    Set up physical subdatasets after rewriting parent history.

    CRITICAL: Must initialize submodules at each level!
    """
    # Sort paths deepest first
    paths = sorted(split_paths, key=lambda p: -p.count('/'))

    for path in paths:
        # Get parent directory
        parent_dir = os.path.dirname(path) or '.'
        parent_repo_path = os.path.join(parent_path, parent_dir)

        # Get gitlink SHA from parent's tree
        gitlink_sha = get_gitlink_sha(parent_repo_path, os.path.basename(path))

        # Clone filtered repository
        subds_path = os.path.join(parent_path, path)
        clone_repository(filtered_repos[path], subds_path)

        # Checkout correct commit
        checkout_commit(subds_path, gitlink_sha)

        # CRITICAL: Initialize submodule in parent's .git/config
        subprocess.run(
            ['git', 'submodule', 'init'],
            cwd=parent_repo_path,
            check=True
        )
        subprocess.run(
            ['git', 'submodule', 'sync'],
            cwd=parent_repo_path,
            check=True
        )

    # Final verification
    verify_all_aspects(parent_path, split_paths)

def verify_all_aspects(parent_path, split_paths):
    """Verify complete nested subdataset setup."""
    checks = []

    # 1. .git directories
    for path in split_paths:
        git_dir = os.path.join(parent_path, path, '.git')
        checks.append(('git_dir', path, os.path.isdir(git_dir)))

    # 2. Submodule initialization (no '-' prefix)
    result = subprocess.run(
        ['git', 'submodule', 'status', '--recursive'],
        cwd=parent_path,
        capture_output=True,
        text=True
    )
    for line in result.stdout.split('\n'):
        if line.strip():
            checks.append(('initialized', line, not line.startswith('-')))

    # 3. .git/config entries
    for path in split_paths:
        parent_dir = os.path.dirname(path) or '.'
        config_path = os.path.join(parent_path, parent_dir, '.git/config')
        with open(config_path) as f:
            content = f.read()
            submod_name = os.path.basename(path)
            checks.append(('config', path, f'[submodule "{submod_name}"]' in content))

    # 4. Gitlinks match actual commits
    for path in split_paths:
        parent_dir = os.path.dirname(path) or '.'
        gitlink = get_gitlink_sha(os.path.join(parent_path, parent_dir),
                                  os.path.basename(path))
        actual = get_commit_sha(os.path.join(parent_path, path))
        checks.append(('gitlink_match', path, gitlink == actual))

    # Report failures
    failures = [c for c in checks if not c[2]]
    if failures:
        raise ValueError(f"Verification failed: {failures}")

    return True
```

## Summary

Complete nested subdataset setup requires:

1. ✅ Clone filtered repos to correct paths
2. ✅ Checkout commits matching gitlinks
3. ✅ **Initialize submodules at EACH level** (often forgotten!)
4. ✅ Verify all aspects (8-point checklist)

**Missing step 3 will result in incomplete setup** where:
- Gitlinks exist in trees ✓
- `.gitmodules` files exist ✓
- `.git` directories exist ✓
- **But submodules NOT initialized** ✗ (`-` prefix in status)
- `git submodule update` may fail or behave incorrectly ✗

Always verify with `git submodule status --recursive` - **no `-` prefix should appear**!
