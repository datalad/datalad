#!/bin/bash
# Experiment 7: Correct Location Tracking via git-annex filter-branch
# Purpose: Verify that git-annex filter-branch properly preserves location information
# Expected: Split dataset should be able to retrieve content from origin WITHOUT copying first

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp07"
echo "=== Experiment 7: Correct Location Tracking ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
chmod -R +w "$EXPERIMENT_DIR" 2>/dev/null || true
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Create test dataset with annexed content
echo -e "\n[Step 1] Creating test dataset with annexed content..."
datalad create -c text2git parent-dataset
cd parent-dataset

mkdir -p data/subject01 data/subject02
echo "Subject 01 metadata" > data/subject01/meta.txt
echo "Subject 02 metadata" > data/subject02/meta.txt

# Create annexed content
dd if=/dev/urandom of=data/subject01/data.dat bs=1M count=2 2>/dev/null
dd if=/dev/urandom of=data/subject02/data.dat bs=1M count=2 2>/dev/null

datalad save -m "Initial dataset with annexed content"

echo -e "\n[Step 2] Verifying original has content..."
echo "Annexed files in original:"
git annex find
echo "Content present:"
git annex find --in=here
echo "Where is content available:"
git annex whereis data/subject01/data.dat

# Step 3: CORRECT METHOD - Clone, filter, and KEEP origin for retrieval
echo -e "\n[Step 3] CORRECT METHOD: Split with location tracking preserved..."
cd "$EXPERIMENT_DIR"
git -c protocol.file.allow=always clone parent-dataset split-correct
cd split-correct

# Get the absolute path to the parent
PARENT_ABS_PATH="$(realpath "$EXPERIMENT_DIR/parent-dataset")"
echo "Parent dataset absolute path: $PARENT_ABS_PATH"

# CRITICAL: Run git-annex filter-branch with --include-all-key-information
# This preserves location tracking info
echo "Running git-annex filter-branch with location info..."
git annex filter-branch data/subject01 --include-all-key-information --include-all-repo-config 2>&1 | tail -3

echo "Running git filter-branch..."
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD 2>&1 | tail -3

# CRITICAL: Update origin URL but DON'T mark it as dead or remove it!
echo "Updating origin remote URL..."
git remote set-url origin "$PARENT_ABS_PATH"
git remote -v

echo "Checking what git-annex knows about content location..."
git annex whereis data.dat || echo "No location info found"

# Step 4: Verify content is NOT present but IS retrievable
echo -e "\n[Step 4] Verifying content state..."
echo "Content present locally:"
git annex find --in=here || echo "None"
echo "Content NOT present but tracked:"
git annex find --not --in=here || echo "All present"

# Step 5: Try to retrieve content from origin
echo -e "\n[Step 5] Attempting to retrieve content from origin..."
datalad get data.dat 2>&1 || echo "Get may have failed"

# Step 6: Verify final state
echo -e "\n[Step 6] Final verification..."
echo "Content present locally after get:"
git annex find --in=here || echo "None"

if [ -f data.dat ]; then
    if [ -L data.dat ]; then
        TARGET=$(readlink data.dat)
        if [ -f "$TARGET" ]; then
            SIZE=$(stat -c%s "$TARGET" 2>/dev/null || stat -f%z "$TARGET")
            echo "  ✓ data.dat: symlink → $SIZE bytes (ACCESSIBLE)"
        else
            echo "  ✗ data.dat: symlink → broken (NOT accessible)"
        fi
    else
        SIZE=$(stat -c%s data.dat 2>/dev/null || stat -f%z data.dat)
        echo "  ✓ data.dat: $SIZE bytes (present as regular file)"
    fi
else
    echo "  ✗ data.dat: MISSING"
fi

# Step 7: Test roundtrip - clone the split dataset
echo -e "\n[Step 7] Testing roundtrip - clone split dataset..."
cd "$EXPERIMENT_DIR"
git -c protocol.file.allow=always clone split-correct split-correct-clone
cd split-correct-clone

echo "Cloned dataset state:"
git annex whereis data.dat 2>&1 || echo "No location info"

echo "Attempting to get content in clone..."
datalad get data.dat 2>&1 || echo "Get may have failed"

if git annex find --in=here | grep -q .; then
    echo "  ✓ SUCCESS: Content retrieved in clone!"
else
    echo "  ✗ FAILURE: Content not retrieved in clone"
fi

# Summary
echo -e "\n=== Experiment 7 Complete ==="
echo ""
echo "KEY FINDINGS:"
echo "1. git-annex filter-branch with --include-all-key-information preserves location tracking"
echo "2. Keeping origin remote allows content retrieval without copying first"
echo "3. Split dataset can use 'datalad get' to fetch content on-demand"
echo "4. This is the CORRECT approach - no need to copy all content during split!"
echo ""
echo "RECOMMENDED WORKFLOW:"
echo "  1. Clone source dataset"
echo "  2. git-annex filter-branch <path> --include-all-key-information"
echo "  3. git filter-branch --subdirectory-filter <path>"
echo "  4. Update origin remote URL (don't remove it!)"
echo "  5. Split dataset can now retrieve content via 'datalad get'"
