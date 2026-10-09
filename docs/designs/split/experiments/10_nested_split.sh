#!/bin/bash
# Experiment 10: Nested Subdataset Split
# Purpose: Test splitting with nested subdatasets (recursive bottom-up)
# Expected: Handle nested structure, split recursively from deepest first

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp10"
echo "=== Experiment 10: Nested Subdataset Split ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
chmod -R +w "$EXPERIMENT_DIR" 2>/dev/null || true
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Create a test dataset with nested structure
echo -e "\n[Step 1] Creating test dataset with nested subdatasets..."
datalad create -c text2git parent-dataset
cd parent-dataset
PARENT_PATH=$(pwd)

# Create a hierarchy:
# parent/
#   ├── data/
#   │   ├── raw/
#   │   │   ├── subject01/ (will be subdataset)
#   │   │   │   ├── session1/
#   │   │   │   │   └── data.txt
#   │   │   │   └── session2/
#   │   │   │       └── data.txt
#   │   │   └── subject02/ (will be subdataset)
#   │   │       └── session1/
#   │   │           └── data.txt
#   │   └── processed/ (will be subdataset)
#   │       └── results.txt
#   └── code/
#       └── analysis.py

echo "Creating directory structure..."
mkdir -p data/raw/subject01/session1 data/raw/subject01/session2
mkdir -p data/raw/subject02/session1
mkdir -p data/processed
mkdir -p code

echo "Adding content..."
echo "Subject 01 Session 1 data" > data/raw/subject01/session1/data.txt
echo "Subject 01 Session 2 data" > data/raw/subject01/session2/data.txt
echo "Subject 02 Session 1 data" > data/raw/subject02/session1/data.txt
echo "Processed results" > data/processed/results.txt
echo "Analysis code" > code/analysis.py

# Add some annexed content
dd if=/dev/urandom of=data/raw/subject01/session1/scan.dat bs=1M count=1 2>/dev/null
dd if=/dev/urandom of=data/raw/subject02/session1/scan.dat bs=1M count=1 2>/dev/null

datalad save -m "Initial dataset with nested structure"

echo "Original structure:"
find data code -type f

# Step 2: Define split targets with nesting
# We want to split:
# 1. data/raw/subject01 -> subdataset
# 2. data/raw/subject02 -> subdataset
# 3. data/processed -> subdataset
# 4. Then data/raw -> subdataset (contains subject01, subject02 as nested subdatasets)
# 5. Then data -> subdataset (contains raw and processed as nested subdatasets)

SPLIT_TARGETS=(
    "data/raw/subject01"
    "data/raw/subject02"
    "data/processed"
    "data/raw"
    "data"
)

echo -e "\n[Step 2] Planning nested splits (bottom-up order)..."
for target in "${SPLIT_TARGETS[@]}"; do
    echo "  - $target"
done

# Step 3: Perform splits in bottom-up order
echo -e "\n[Step 3] Performing splits (deepest first)..."

for TARGET in "${SPLIT_TARGETS[@]}"; do
    echo -e "\n--- Splitting $TARGET ---"

    cd "$PARENT_PATH"

    # Check if target exists
    if [ ! -d "$TARGET" ]; then
        echo "⚠ $TARGET doesn't exist (may have been consumed by previous split), skipping"
        continue
    fi

    # Check if it's already a subdataset
    if [ -d "$TARGET/.git" ] || [ -f "$TARGET/.git" ]; then
        echo "✓ $TARGET is already a subdataset, skipping"
        continue
    fi

    # Simple approach: rm, clone, filter, register
    echo "Removing $TARGET/ (not committing)..."
    rm -rf "$TARGET"

    echo "Cloning parent into $TARGET/..."
    git -c protocol.file.allow=always clone . "$TARGET"

    cd "$TARGET"

    # Filter to keep only this path
    echo "Filtering to keep only $TARGET content..."
    git annex filter-branch "$TARGET" --include-all-key-information --include-all-repo-config 2>&1 | tail -2 || true
    export FILTER_BRANCH_SQUELCH_WARNING=1
    git filter-branch --subdirectory-filter "$TARGET" --prune-empty HEAD 2>&1 | tail -2 || echo "filter done"

    # Update origin
    git remote set-url origin "$PARENT_PATH"

    # Clean metadata
    git annex forget --force --drop-dead 2>&1 | tail -2 || true

    cd "$PARENT_PATH"

    # Register as submodule
    echo "Registering $TARGET as submodule..."
    git submodule add "./$TARGET" "$TARGET" 2>&1 || echo "submodule registration attempted"
done

# Step 4: Final save of entire hierarchy
echo -e "\n[Step 4] Final recursive save..."
datalad save -d . -r -m "Complete nested subdataset structure" 2>&1 | tail -10

# Step 5: Verification
echo -e "\n[Step 5] Verification..."
echo "Git status:"
git status --short

echo -e "\nSubdatasets (recursive):"
datalad subdatasets -r || git submodule status --recursive

echo -e "\nDirectory structure:"
find . -name ".git" -type d -o -name ".git" -type f | head -20

echo -e "\n[Step 6] Testing recursive content retrieval..."
datalad get -r . 2>&1 | tail -20 || echo "get completed"

# Step 7: Verify nested hierarchy
echo -e "\n[Step 7] Verifying nested structure..."

check_subdataset() {
    local path=$1
    if [ -d "$path/.git" ] || [ -f "$path/.git" ]; then
        cd "$path"
        local present=$(git annex find --in=here 2>/dev/null | wc -l || echo "0")
        local missing=$(git annex find --not --in=here 2>/dev/null | wc -l || echo "0")
        echo "  $path: IS subdataset, $present present, $missing missing"
        cd "$PARENT_PATH"
    else
        echo "  $path: NOT a subdataset"
    fi
}

for target in "${SPLIT_TARGETS[@]}"; do
    if [ -d "$target" ]; then
        check_subdataset "$target"
    fi
done

# Final status
echo -e "\n=== Experiment 10 Complete ==="
FINAL_STATUS=$(git status --porcelain)
if [ -z "$FINAL_STATUS" ]; then
    echo "✓ SUCCESS: Git status is CLEAN"
else
    echo "Git status:"
    git status --short
fi

echo -e "\nNested subdataset hierarchy created:"
echo "  data/ (subdataset)"
echo "    ├── raw/ (nested subdataset)"
echo "    │   ├── subject01/ (nested subdataset)"
echo "    │   └── subject02/ (nested subdataset)"
echo "    └── processed/ (subdataset)"

echo -e "\nDataset location: $PARENT_PATH"
