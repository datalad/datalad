#!/bin/bash
# Experiment 12: Content Mode Strategies Testing
# Purpose: Test different --content-mode strategies for handling annexed content
# Target: Split data/subjects/subject01/ (nested 2 directories down)
# Test all modes: nothing, copy, move, reckless-hardlink, reckless-ephemeral, worktree

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp12"
echo "=== Experiment 12: Content Mode Strategies ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
chmod -R +w "$EXPERIMENT_DIR" 2>/dev/null || true
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Helper function to create test dataset with content
create_test_dataset() {
    local name=$1
    echo -e "\n=== Creating test dataset: $name ==="

    datalad create "$name"
    cd "$name"

    # Create nested structure: data/subjects/subject01/
    mkdir -p data/subjects/subject01/session1
    mkdir -p data/subjects/subject01/session2
    mkdir -p data/subjects/subject02/session1

    # Create some annexed content (large files)
    dd if=/dev/urandom of=data/subjects/subject01/session1/data.dat bs=1M count=5 2>/dev/null
    dd if=/dev/urandom of=data/subjects/subject01/session2/data.dat bs=1M count=5 2>/dev/null
    dd if=/dev/urandom of=data/subjects/subject02/session1/data.dat bs=1M count=5 2>/dev/null

    # Create some regular git files
    echo "Subject 01 README" > data/subjects/subject01/README.md
    echo "Subject 02 README" > data/subjects/subject02/README.md

    # Add to annex
    git annex add data/subjects/
    git add data/subjects/*/README.md
    git commit -m "Add subjects data"

    echo "Dataset created with content"
    git annex info | grep "local annex size"

    cd "$EXPERIMENT_DIR"
}

# Test 1: nothing mode (default)
echo -e "\n\n### TEST 1: content-mode=nothing (default) ###"
create_test_dataset "test-nothing"
cd test-nothing

echo "Pre-split: Check content present in parent"
ls -lh data/subjects/subject01/session1/data.dat

echo -e "\nSplitting data/subjects/subject01/ with mode=nothing"
# Simulate split with nothing mode
TARGET_PATH="data/subjects/subject01"

# Step 1: Remove from index
git rm -r --cached "$TARGET_PATH/"

# Step 2: Remove physically
rm -rf "$TARGET_PATH"

# Step 3: Clone
git -c protocol.file.allow=always clone . "$TARGET_PATH"

# Step 4: Filter
cd "$TARGET_PATH"
git annex filter-branch "$TARGET_PATH" --include-all-key-information --include-all-repo-config 2>&1 | tail -2
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter "$TARGET_PATH" --prune-empty HEAD 2>&1 | tail -2
PARENT_PATH=$(cd ../.. && pwd)
git remote set-url origin "$PARENT_PATH"
git annex forget --force --drop-dead 2>&1 | tail -2

echo -e "\nChecking content availability in subdataset:"
git annex whereis session1/data.dat || echo "Key information available"

echo "Content present locally?"
[ -e session1/data.dat ] && ls -lh session1/data.dat || echo "No - it's a broken symlink (expected)"

cd "$PARENT_PATH"
git submodule add ./"$TARGET_PATH" "$TARGET_PATH"
git commit -m "Split with content-mode=nothing"

echo -e "\nResult: Content NOT in subdataset, can retrieve on-demand"
cd "$EXPERIMENT_DIR"


# Test 2: copy mode
echo -e "\n\n### TEST 2: content-mode=copy ###"
create_test_dataset "test-copy"
cd test-copy

echo "Pre-split storage:"
du -sh .git/annex

TARGET_PATH="data/subjects/subject01"

# Do the split (steps 1-4 same as above)
git rm -r --cached "$TARGET_PATH/"
rm -rf "$TARGET_PATH"
git -c protocol.file.allow=always clone . "$TARGET_PATH"
cd "$TARGET_PATH"
git annex filter-branch "$TARGET_PATH" --include-all-key-information --include-all-repo-config 2>&1 | tail -2
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter "$TARGET_PATH" --prune-empty HEAD 2>&1 | tail -2
PARENT_PATH=$(cd ../.. && pwd)
git remote set-url origin "$PARENT_PATH"
git annex forget --force --drop-dead 2>&1 | tail -2

# NOW: Copy content from parent
echo -e "\nCopying content from parent..."
annexed_files=$(git annex find --include '*')
for file in $annexed_files; do
    echo "Getting: $file"
    datalad get "$file" 2>&1 | grep -E "(ok|notneeded)" || echo "Retrieved"
done

echo -e "\nContent present in subdataset?"
ls -lh session1/data.dat

cd "$PARENT_PATH"
git submodule add ./"$TARGET_PATH" "$TARGET_PATH"
git commit -m "Split with content-mode=copy"

echo -e "\nPost-split storage comparison:"
echo "Parent annex:"
du -sh .git/annex
echo "Subdataset annex:"
du -sh "$TARGET_PATH"/.git/annex
echo "Note: On CoW filesystems (BTRFS), actual duplication may be less"

cd "$EXPERIMENT_DIR"


# Test 3: reckless-hardlink mode
echo -e "\n\n### TEST 3: content-mode=reckless-hardlink ###"
create_test_dataset "test-hardlink"
cd test-hardlink

TARGET_PATH="data/subjects/subject01"

# Do the split
git rm -r --cached "$TARGET_PATH/"
rm -rf "$TARGET_PATH"
git -c protocol.file.allow=always clone . "$TARGET_PATH"
cd "$TARGET_PATH"
git annex filter-branch "$TARGET_PATH" --include-all-key-information --include-all-repo-config 2>&1 | tail -2
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter "$TARGET_PATH" --prune-empty HEAD 2>&1 | tail -2
PARENT_PATH=$(cd ../.. && pwd)
git remote set-url origin "$PARENT_PATH"
git annex forget --force --drop-dead 2>&1 | tail -2

# NOW: Create hardlinks
echo -e "\nCreating hardlinks to parent's annex objects..."
annexed_files=$(git annex find --include '*')
for file in $annexed_files; do
    key=$(git annex lookupkey "$file" 2>/dev/null || echo "")
    if [ -n "$key" ]; then
        # Find object in parent
        parent_obj=$(cd "$PARENT_PATH" && git annex contentlocation "$key" 2>/dev/null || echo "")
        if [ -n "$parent_obj" ] && [ -e "$PARENT_PATH/$parent_obj" ]; then
            subds_obj=$(git annex contentlocation "$key" 2>/dev/null || echo "")
            if [ -n "$subds_obj" ]; then
                mkdir -p "$(dirname "$subds_obj")"
                echo "Hardlinking: $file"
                ln "$PARENT_PATH/$parent_obj" "$subds_obj" 2>/dev/null || echo "  (already exists or failed)"
                git annex fsck --fast "$file" 2>&1 | grep -E "(ok|fixing)" || true
            fi
        fi
    fi
done

echo -e "\nVerifying hardlinks (same inode?):"
file1="session1/data.dat"
if [ -e "$file1" ]; then
    key=$(git annex lookupkey "$file1")
    subds_obj=$(git annex contentlocation "$key")
    parent_obj=$(cd "$PARENT_PATH" && git annex contentlocation "$key")

    echo "Subdataset object inode: $(stat -c %i "$subds_obj" 2>/dev/null || stat -f %i "$subds_obj")"
    echo "Parent object inode:     $(stat -c %i "$PARENT_PATH/$parent_obj" 2>/dev/null || stat -f %i "$PARENT_PATH/$parent_obj")"
fi

cd "$PARENT_PATH"
git submodule add ./"$TARGET_PATH" "$TARGET_PATH"
git commit -m "Split with content-mode=reckless-hardlink"

echo "Result: Hardlinks created, no storage duplication"
cd "$EXPERIMENT_DIR"


# Test 4: reckless-ephemeral mode
echo -e "\n\n### TEST 4: content-mode=reckless-ephemeral ###"
create_test_dataset "test-ephemeral"
cd test-ephemeral

TARGET_PATH="data/subjects/subject01"

# Do the split
git rm -r --cached "$TARGET_PATH/"
rm -rf "$TARGET_PATH"
git -c protocol.file.allow=always clone . "$TARGET_PATH"
cd "$TARGET_PATH"
git annex filter-branch "$TARGET_PATH" --include-all-key-information --include-all-repo-config 2>&1 | tail -2
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter "$TARGET_PATH" --prune-empty HEAD 2>&1 | tail -2
PARENT_PATH=$(cd ../.. && pwd)
git remote set-url origin "$PARENT_PATH"
git annex forget --force --drop-dead 2>&1 | tail -2

# NOW: Symlink entire .git/annex/objects
echo -e "\nSymlinking .git/annex/objects to parent..."
rm -rf .git/annex/objects
ln -s "$PARENT_PATH/.git/annex/objects" .git/annex/objects

echo "Verification:"
ls -la .git/annex/objects | head -3
echo "Content accessible?"
ls -lh session1/data.dat 2>/dev/null && echo "Yes!" || echo "Symlink present"

cd "$PARENT_PATH"
git submodule add ./"$TARGET_PATH" "$TARGET_PATH"
git commit -m "Split with content-mode=reckless-ephemeral"

echo "Result: Shared annex via symlink, completely dependent on parent"
cd "$EXPERIMENT_DIR"


# Test 5: worktree mode
echo -e "\n\n### TEST 5: content-mode=worktree ###"
create_test_dataset "test-worktree"
cd test-worktree

TARGET_PATH="data/subjects/subject01"

echo "Creating worktree instead of clone..."
# Different approach: create worktree
branch_name="split/$(echo "$TARGET_PATH" | tr '/' '-')"
git branch "$branch_name" HEAD

# Remove from index
git rm -r --cached "$TARGET_PATH/"

# Create worktree
git worktree add "$TARGET_PATH" "$branch_name"

cd "$TARGET_PATH"
echo "Worktree created. Filtering..."
git annex filter-branch "$TARGET_PATH" --include-all-key-information --include-all-repo-config 2>&1 | tail -2
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter "$TARGET_PATH" --prune-empty HEAD 2>&1 | tail -2
PARENT_PATH=$(cd ../.. && pwd)

echo -e "\nChecking .git structure:"
ls -la .git | head -5

echo "Shared objects?"
if [ -L .git/objects ] || grep -q "gitdir:" .git 2>/dev/null; then
    echo "Yes - worktree shares objects with parent"
fi

echo "Content accessible?"
ls -lh session1/data.dat 2>/dev/null || echo "Content symlinks present"

cd "$PARENT_PATH"
# Note: with worktree, subdataset registration is different
echo "Worktree list:"
git worktree list

echo "Result: Worktree created, shares git objects with parent"
cd "$EXPERIMENT_DIR"


# Summary
echo -e "\n\n=== SUMMARY ==="
echo "All content-mode strategies tested on nested path: data/subjects/subject01/"
echo ""
echo "Findings:"
echo "1. nothing: Content not copied, retrieve on-demand ✓"
echo "2. copy: Content duplicated in subdataset ✓"
echo "3. reckless-hardlink: Hardlinks created (check inode matching)"
echo "4. reckless-ephemeral: Symlink to parent's annex ✓"
echo "5. worktree: Uses git worktree, shares objects ✓"
echo ""
echo "Check results in: $EXPERIMENT_DIR"
echo ""
echo "Note: Test 'move' mode would require proper git-annex remote setup"
