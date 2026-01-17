#!/bin/bash
# Experiment 9: In-Place Split Workflow
# Purpose: Split by cloning directly into target location, filter in place
# Expected: Cleaner workflow, single save at end for all splits

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp09"
echo "=== Experiment 9: In-Place Split (Single Subfolder) ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
chmod -R +w "$EXPERIMENT_DIR" 2>/dev/null || true
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Clone the test dataset
echo -e "\n[Step 1] Cloning test dataset..."
datalad clone https://github.com/dandizarrs/3fd86b7a-8a27-4893-8fc2-66e0c9b478bf parent-dataset
cd parent-dataset

PARENT_PATH=$(pwd)
TARGET_DIR="sorting"

echo "Original structure:"
ls -la | head -15

# Step 2: Test with ONE subfolder first
echo -e "\n[Step 2] Splitting $TARGET_DIR using in-place approach..."

# 2a. Remove the directory (don't commit!)
echo "Removing $TARGET_DIR/ (not committing)..."
rm -rf "$TARGET_DIR"

# 2b. Clone parent into that location
echo "Cloning parent into $TARGET_DIR/..."
git -c protocol.file.allow=always clone . "$TARGET_DIR"
cd "$TARGET_DIR"

# 2c. Filter in place
echo "Filtering to keep only $TARGET_DIR content..."
git annex filter-branch "$TARGET_DIR" --include-all-key-information --include-all-repo-config 2>&1 | tail -3
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter "$TARGET_DIR" --prune-empty HEAD 2>&1 | tail -3

# 2d. Update origin to point to parent
echo "Updating origin remote..."
git remote set-url origin "$PARENT_PATH"

# 2e. Clean metadata
echo "Cleaning metadata..."
git annex forget --force --drop-dead 2>&1 | tail -3

cd "$PARENT_PATH"

# Step 3: Register as submodule
echo -e "\n[Step 3] Registering $TARGET_DIR as submodule..."
git submodule add "./$TARGET_DIR" "$TARGET_DIR" 2>&1 || echo "Submodule add completed"

# Step 4: Save everything in one go
echo -e "\n[Step 4] Saving changes with datalad save -d . -r..."
datalad save -d . -r -m "Split $TARGET_DIR into subdataset" 2>&1 | tail -10

# Step 5: Verify
echo -e "\n[Step 5] Verification..."
echo "Git status:"
git status --short

echo -e "\nSubdatasets:"
datalad subdatasets

echo -e "\nTesting content retrieval..."
datalad get -r "$TARGET_DIR" 2>&1 | tail -10

echo -e "\nContent in subdataset:"
cd "$TARGET_DIR"
echo "Annexed files present: $(git annex find --in=here | wc -l)"
echo "Annexed files missing: $(git annex find --not --in=here | wc -l)"

echo -e "\n=== Test 1 (Single Subfolder) Complete ==="
echo "Result: $([ -z "$(cd "$PARENT_PATH" && git status --porcelain)" ] && echo "✓ CLEAN" || echo "✗ DIRTY")"

# Step 6: Now test with MULTIPLE subfolders
cd "$PARENT_PATH"
echo -e "\n=== Test 2: Multiple Subfolders ==="
echo "[Step 6] Splitting multiple directories: extensions, recording..."

TARGETS=("extensions" "recording")

for TARGET in "${TARGETS[@]}"; do
    echo -e "\n--- Processing $TARGET ---"

    # Remove directory
    echo "Removing $TARGET/..."
    rm -rf "$TARGET"

    # Clone into place
    echo "Cloning parent into $TARGET/..."
    git -c protocol.file.allow=always clone . "$TARGET"
    cd "$TARGET"

    # Filter
    echo "Filtering..."
    git annex filter-branch "$TARGET" --include-all-key-information --include-all-repo-config 2>&1 | tail -2
    git filter-branch --subdirectory-filter "$TARGET" --prune-empty HEAD 2>&1 | tail -2

    # Update origin
    git remote set-url origin "$PARENT_PATH"

    # Clean metadata
    git annex forget --force --drop-dead 2>&1 | tail -2

    cd "$PARENT_PATH"

    # Register submodule
    echo "Registering $TARGET as submodule..."
    git submodule add "./$TARGET" "$TARGET" 2>&1 || echo "Submodule registered"
done

# Single save for all changes
echo -e "\n[Step 7] Saving all changes with single datalad save -d . -r..."
datalad save -d . -r -m "Split extensions and recording into subdatasets" 2>&1 | tail -10

# Verify
echo -e "\n[Step 8] Final verification..."
echo "Git status:"
git status --short

echo -e "\nAll subdatasets:"
datalad subdatasets

echo -e "\nTesting recursive get on all subdatasets..."
datalad get -r . 2>&1 | tail -20

echo -e "\n=== Test 2 (Multiple Subfolders) Complete ==="
for TARGET in "${TARGETS[@]}"; do
    if [ -d "$TARGET" ]; then
        cd "$TARGET"
        PRESENT=$(git annex find --in=here 2>/dev/null | wc -l)
        MISSING=$(git annex find --not --in=here 2>/dev/null | wc -l)
        echo "$TARGET: $PRESENT present, $MISSING missing"
        cd "$PARENT_PATH"
    fi
done

echo -e "\nFinal git status:"
git status --short
FINAL_STATUS=$(git status --porcelain)
if [ -z "$FINAL_STATUS" ]; then
    echo "✓ SUCCESS: All changes saved, git status CLEAN"
else
    echo "⚠ WARNING: git status not clean"
fi

echo -e "\n=== Experiment 9 Complete ==="
echo "Datasets split: sorting, extensions, recording"
echo "All registered as subdatasets: $(datalad subdatasets | wc -l) subdatasets"
echo "Parent dataset: $PARENT_PATH"
