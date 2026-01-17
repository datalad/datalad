#!/bin/bash
# Experiment 8: Complete Split Workflow with Full Subdataset Registration
# Purpose: Test the COMPLETE workflow including parent registration and cleanup
# Expected: Clean git status after split, datalad get -r retrieves all content

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp08"
echo "=== Experiment 8: Complete Split Workflow ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
chmod -R +w "$EXPERIMENT_DIR" 2>/dev/null || true
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Clone the real-world test dataset
echo -e "\n[Step 1] Cloning real-world test dataset..."
datalad clone https://github.com/dandizarrs/3fd86b7a-8a27-4893-8fc2-66e0c9b478bf parent-dataset
cd parent-dataset

echo "Original dataset structure:"
ls -la

echo -e "\nAnnexed files in original (sample):"
git annex find 2>&1 | head -10 || echo "No annexed files found"

# Step 2: Choose a directory to split - use "sorting"
TARGET_DIR="sorting"
echo -e "\n[Step 2] Will split directory: $TARGET_DIR"

if [ ! -d "$TARGET_DIR" ]; then
    echo "ERROR: Directory $TARGET_DIR not found"
    exit 1
fi

echo "Files in target directory (sample):"
find "$TARGET_DIR" -type f 2>/dev/null | head -10

echo "Annexed files in target (sample):"
git annex find "$TARGET_DIR" 2>&1 | head -10 || echo "None"

# Step 3: Record parent state
PARENT_PATH=$(realpath "$EXPERIMENT_DIR/parent-dataset")
echo -e "\n[Step 3] Parent dataset path: $PARENT_PATH"
echo "Git status before split:"
git status --short | head -10

# Step 4: Create the split subdataset
echo -e "\n[Step 4] Creating split subdataset via clone and filter..."
cd "$EXPERIMENT_DIR"

# Clone to create the split
git -c protocol.file.allow=always clone parent-dataset "$TARGET_DIR-split"
cd "$TARGET_DIR-split"

echo "Running git-annex filter-branch..."
git annex filter-branch "$TARGET_DIR" --include-all-key-information --include-all-repo-config 2>&1 | tail -3 || echo "filter-branch completed"

echo "Running git filter-branch to isolate $TARGET_DIR..."
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter "$TARGET_DIR" --prune-empty HEAD 2>&1 | tail -3

echo "Updating origin remote to point to parent..."
git remote set-url origin "$PARENT_PATH"

echo "Cleaning unrelated metadata..."
git annex forget --force --drop-dead 2>&1 | tail -3

SPLIT_PATH=$(realpath "$EXPERIMENT_DIR/$TARGET_DIR-split")
echo "Split subdataset created at: $SPLIT_PATH"

echo "Verifying location tracking..."
git annex whereis 2>&1 | head -5 || echo "No annexed content"

# Step 5: Remove original content from parent and register subdataset
echo -e "\n[Step 5] Removing original content from parent..."
cd "$PARENT_PATH"

# Save current state before removing
datalad save -m "Pre-split state" 2>&1 || echo "Nothing to save"

# Remove the original directory
echo "Removing $TARGET_DIR/ from parent..."
git rm -rf "$TARGET_DIR" 2>&1 || echo "rm completed"
datalad save -m "Remove $TARGET_DIR content (will become subdataset)" 2>&1 || true

# Step 6: Register the split as a subdataset at the original location
echo -e "\n[Step 6] Registering split subdataset at original location..."
# Use file:// URL for local path
datalad install -d . -s "$SPLIT_PATH" --recursive "$TARGET_DIR" 2>&1 || \
    git submodule add "$SPLIT_PATH" "$TARGET_DIR" 2>&1 || \
    echo "Subdataset registration attempted"

# Save the submodule addition
datalad save -m "Add $TARGET_DIR as subdataset" 2>&1 || true

# Step 7: Verify git status
echo -e "\n[Step 7] Verifying git status..."
GIT_STATUS=$(git status --porcelain)
if [ -z "$GIT_STATUS" ]; then
    echo "✓ SUCCESS: Git status is CLEAN"
else
    echo "Git status:"
    git status --short
fi

# Step 8: Verify subdataset structure
echo -e "\n[Step 8] Verifying subdataset structure..."
echo "Subdatasets in parent:"
datalad subdatasets || git submodule status

echo -e "\nChecking if $TARGET_DIR is a subdataset:"
if [ -d "$TARGET_DIR/.git" ] || [ -f "$TARGET_DIR/.git" ]; then
    echo "✓ $TARGET_DIR has .git (is a repository/subdataset)"
else
    echo "✗ $TARGET_DIR does not appear to be a subdataset"
fi

# Step 9: Test recursive content retrieval
echo -e "\n[Step 9] Testing recursive content retrieval..."
echo "Attempting: datalad get -r $TARGET_DIR"
datalad get -r "$TARGET_DIR" 2>&1 | tail -20 || echo "Get completed or failed"

# Step 10: Verify content in subdataset
echo -e "\n[Step 10] Verifying content in subdataset..."
cd "$TARGET_DIR"

echo "Files in subdataset (sample):"
find . -type f ! -path './.git/*' 2>/dev/null | head -10

echo "Annexed content present:"
git annex find --in=here 2>&1 | wc -l || echo "0"

echo "Annexed content NOT present:"
git annex find --not --in=here 2>&1 | wc -l || echo "0"

cd "$PARENT_PATH"

# Step 11: Final verification
echo -e "\n[Step 11] Final verification - git status across hierarchy..."
echo "Parent git status:"
git status --short

if [ -d "$TARGET_DIR" ]; then
    echo -e "\nSubdataset git status:"
    cd "$TARGET_DIR"
    git status --short
    cd "$PARENT_PATH"
fi

# Summary
echo -e "\n=== Experiment 8 Complete ==="
echo ""
echo "VERIFICATION CHECKLIST:"
echo "1. Split subdataset created: $([ -d "$SPLIT_PATH" ] && echo "✓" || echo "✗")"
echo "2. Registered in parent at $TARGET_DIR: $([ -d "$PARENT_PATH/$TARGET_DIR/.git" ] || [ -f "$PARENT_PATH/$TARGET_DIR/.git" ] && echo "✓" || echo "✗")"
echo "3. Original content removed from parent: $(cd "$PARENT_PATH" && [ -z "$(git ls-files "$TARGET_DIR/" 2>/dev/null | grep -v "^$TARGET_DIR\$")" ] && echo "✓" || echo "✗")"
echo "4. Parent git status clean: $(cd "$PARENT_PATH" && [ -z "$(git status --porcelain)" ] && echo "✓" || echo "✗")"
echo "5. Content retrievable in subdataset: TBD (check log above)"
echo ""
echo "Parent dataset: $PARENT_PATH"
echo "Split subdataset source: $SPLIT_PATH"
echo "Subdataset mounted at: $PARENT_PATH/$TARGET_DIR"
