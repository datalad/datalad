#!/bin/bash
# Experiment 11: ReproNim/containers Split - Real-World Nested Subdatasets
# Purpose: Split ReproNim/containers with nested structure
# Target structure:
#   containers/ (parent)
#   ├── images/ (subdataset)
#   │   ├── bids/ (nested under images/)
#   │   ├── repronim/ (nested under images/)
#   │   │   └── .datalad/ (nested under repronim/)
#   └── binds/ (subdataset)

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp11"
echo "=== Experiment 11: ReproNim/containers Split ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
chmod -R +w "$EXPERIMENT_DIR" 2>/dev/null || true
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Clone ReproNim/containers
echo -e "\n[Step 1] Cloning ReproNim/containers..."
datalad clone https://github.com/ReproNim/containers containers
cd containers
PARENT_PATH=$(pwd)

echo "Repository structure:"
ls -la

echo -e "\nExisting subdatasets:"
datalad subdatasets -r || echo "Listing subdatasets..."

# Step 2: Analyze structure
echo -e "\n[Step 2] Analyzing structure for split plan..."
if [ -f .gitmodules ]; then
    echo "Current .gitmodules:"
    cat .gitmodules
else
    echo "No .gitmodules found (no existing subdatasets)"
fi

echo -e "\nDirectories to split:"
echo "  1. images/repronim/.datalad (deepest)"
echo "  2. images/bids"
echo "  3. images/repronim"
echo "  4. images"
echo "  5. binds"

# Step 3: Split in bottom-up order
echo -e "\n[Step 3] Splitting subdatasets (bottom-up)..."

# Track what we split
declare -a SPLIT_DIRS=()

# Helper function to split a directory
split_directory() {
    local TARGET=$1
    local DESCRIPTION=$2

    echo -e "\n--- Splitting $TARGET ($DESCRIPTION) ---"

    cd "$PARENT_PATH"

    # Check if exists
    if [ ! -d "$TARGET" ]; then
        echo "⚠ $TARGET doesn't exist, skipping"
        return 1
    fi

    # Check if already a subdataset
    if [ -d "$TARGET/.git" ] || [ -f "$TARGET/.git" ]; then
        echo "✓ $TARGET is already a subdataset, skipping filter"
        return 0
    fi

    # Save nested subdataset info if it exists
    echo "Checking for nested subdatasets under $TARGET..."
    if [ -f .gitmodules ]; then
        git config -f .gitmodules --get-regexp "submodule\.${TARGET}/" || echo "No nested subdatasets found"
    fi

    # Remove and clone in place
    echo "Removing $TARGET/..."
    rm -rf "$TARGET"

    echo "Cloning into $TARGET/..."
    git -c protocol.file.allow=always clone . "$TARGET" 2>&1 | tail -3

    cd "$TARGET"

    # Filter
    echo "Filtering..."
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
    git submodule add "./$TARGET" "$TARGET" 2>&1 | grep -v "^Cloning" || echo "submodule registered"

    # Check if nested subdatasets survived
    if [ -f "$TARGET/.gitmodules" ]; then
        echo "✓ .gitmodules exists in $TARGET"
        cat "$TARGET/.gitmodules"
    else
        echo "⚠ No .gitmodules in $TARGET (nested subdatasets lost)"
    fi

    SPLIT_DIRS+=("$TARGET")
    return 0
}

# 3a. Try to split deepest first (if they exist as separate entities)
# Note: These might already be subdatasets
split_directory "images/repronim/.datalad" "deepest nested"
split_directory "images/bids" "leaf under images"
split_directory "images/repronim" "nested under images"
split_directory "images" "top-level"
split_directory "binds" "top-level"

# Step 4: Final save
echo -e "\n[Step 4] Final recursive save..."
datalad save -d . -r -m "Split into subdatasets: images/, binds/, and nested" 2>&1 | tail -10 || true

# Step 5: Verify final state
echo -e "\n[Step 5] Final verification..."
echo "Git status:"
git status --short

echo -e "\nSubdatasets (recursive):"
datalad subdatasets -r 2>&1 || git submodule status --recursive

echo -e "\nFinal .gitmodules:"
if [ -f .gitmodules ]; then
    cat .gitmodules
else
    echo "No .gitmodules"
fi

# Step 6: Check each split directory
echo -e "\n[Step 6] Checking split directories..."
for dir in "${SPLIT_DIRS[@]}"; do
    echo -e "\n=== $dir ==="
    if [ -d "$dir" ]; then
        echo "  Exists: ✓"
        if [ -d "$dir/.git" ] || [ -f "$dir/.git" ]; then
            echo "  Is subdataset: ✓"
            if [ -f "$dir/.gitmodules" ]; then
                echo "  Has nested subdatasets: ✓"
                echo "  Nested entries:"
                cat "$dir/.gitmodules"
            else
                echo "  Has nested subdatasets: ✗ (lost during filter)"
            fi
        else
            echo "  Is subdataset: ✗"
        fi
    else
        echo "  Exists: ✗"
    fi
done

# Step 7: Test content retrieval
echo -e "\n[Step 7] Testing content retrieval..."
echo "Attempting: datalad get -r -n ."
datalad get -r -n . 2>&1 | tail -20 || echo "Get completed"

# Final status
echo -e "\n=== Experiment 11 Complete ==="
FINAL_STATUS=$(git status --porcelain)
if [ -z "$FINAL_STATUS" ]; then
    echo "✓ SUCCESS: Git status is CLEAN"
else
    echo "Git status:"
    git status --short
    echo ""
    echo "⚠ Git status is NOT clean - some manual intervention needed"
fi

echo -e "\nResult location: $PARENT_PATH"
echo ""
echo "EXPECTED ISSUES (Phase 4 not implemented):"
echo "  - Nested subdatasets under images/ likely lost"
echo "  - images/.gitmodules will be missing (needs reconstruction)"
echo "  - Manual verification needed for nested structure"
echo ""
echo "To inspect:"
echo "  cd $PARENT_PATH"
echo "  git status"
echo "  datalad subdatasets -r"
