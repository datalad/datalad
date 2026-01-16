#!/bin/bash
# Experiment 2: Nested Subdataset Handling
# Purpose: Test how filter-branch handles nested subdatasets
# Expected: Subdataset registrations should be preserved or cleanly removed

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp02"
echo "=== Experiment 2: Nested Subdataset Handling ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Create parent dataset
echo -e "\n[Step 1] Creating parent dataset with nested subdatasets..."
datalad create -c text2git parent-dataset
cd parent-dataset

# Create directory structure
mkdir -p data/subject01 data/subject02 code

# Create a subdataset in subject01
echo "Creating nested subdataset in data/subject01/raw..."
datalad create -d . data/subject01/raw
echo "Raw data for subject01" > data/subject01/raw/data.txt
datalad save -d data/subject01/raw -m "Add raw data"

# Create regular files in subject01
echo "Subject 01 - metadata" > data/subject01/metadata.txt

# Create another subdataset at code level
echo "Creating code subdataset..."
datalad create -d . code
echo "print('analysis')" > code/analyze.py
datalad save -d code -m "Add analysis script"

# Create content in subject02
echo "Subject 02 - Session 1" > data/subject02/session1.txt

# Save parent
datalad save -m "Parent dataset with nested subdatasets"

# Step 2: Record initial state
echo -e "\n[Step 2] Recording initial state..."
echo "Subdatasets:"
datalad subdatasets
echo -e "\n.gitmodules content:"
cat .gitmodules
echo -e "\nDirectory structure:"
find data code -type f -o -type d | grep -v '.git' | sort

# Step 3: Clone for filtering (will extract data/subject01)
echo -e "\n[Step 3] Cloning and preparing to filter data/subject01..."
cd "$EXPERIMENT_DIR"
git clone --recursive parent-dataset filtered-with-nested
cd filtered-with-nested

echo "Before filtering - subdatasets:"
git submodule status || echo "No submodules"
ls -la

# Step 4: Test git-annex filter-branch with nested subdataset
echo -e "\n[Step 4] Running git-annex filter-branch for data/subject01..."
if git annex filter-branch data/subject01 --include-all-key-information 2>&1; then
    echo "git-annex filter-branch completed"
else
    echo "WARNING: git-annex filter-branch failed or not available"
fi

# Step 5: Run git filter-branch
echo -e "\n[Step 5] Running git filter-branch --subdirectory-filter..."
# This should extract data/subject01 and its nested subdataset
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD

# Step 6: Analyze what happened to nested subdataset
echo -e "\n[Step 6] Analyzing nested subdataset handling..."
echo "=== RESULTS ==="
echo -e "\nDirectory structure after filtering:"
find . -type f -not -path './.git/*' -not -path '*/.git/*' | sort

echo -e "\n.gitmodules after filtering:"
if [ -f .gitmodules ]; then
    cat .gitmodules
else
    echo ".gitmodules not found"
fi

echo -e "\nGit submodules after filtering:"
git submodule status || echo "No submodules"

echo -e "\nLooking for 'raw' directory:"
if [ -d "raw" ]; then
    echo "✓ raw directory exists"
    if [ -d "raw/.git" ]; then
        echo "✓ raw/.git exists (still a git repository)"
        cd raw
        echo "  Commits in raw subdataset:"
        git log --oneline | head -5
        cd ..
    else
        echo "✗ raw/.git does not exist (no longer a git repository)"
    fi
else
    echo "✗ raw directory does not exist"
fi

echo -e "\nChecking if metadata.txt is present:"
if [ -f "metadata.txt" ]; then
    echo "✓ metadata.txt found"
    cat metadata.txt
else
    echo "✗ metadata.txt not found"
fi

# Step 7: Test Case - What if we want to preserve the subdataset?
echo -e "\n[Step 7] Testing subdataset preservation strategy..."
cd "$EXPERIMENT_DIR"
git clone --recursive parent-dataset test-preserve-subdataset
cd test-preserve-subdataset

echo "Strategy: Keep subdataset reference when filtering parent path"
# The subdataset should end up at ./raw after filtering data/subject01

# First, let's see what .gitmodules looks like
echo "Original .gitmodules:"
cat .gitmodules

git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD

echo -e "\nAfter filtering - .gitmodules:"
if [ -f .gitmodules ]; then
    cat .gitmodules
    # Check if path got updated
    if grep -q "path = raw" .gitmodules; then
        echo "✓ Subdataset path correctly updated to 'raw'"
    elif grep -q "path = data/subject01/raw" .gitmodules; then
        echo "⚠ Subdataset path not updated, still references old path"
    fi
else
    echo "✗ .gitmodules disappeared during filtering"
fi

echo -e "\n=== Experiment 2 Complete ==="
echo "Datasets available at:"
echo "  Original: $EXPERIMENT_DIR/parent-dataset"
echo "  Filtered: $EXPERIMENT_DIR/filtered-with-nested"
echo "  Preserve test: $EXPERIMENT_DIR/test-preserve-subdataset"

# Summary
echo -e "\n=== KEY FINDINGS ==="
echo "1. Check if nested subdatasets survive filter-branch"
echo "2. Check if .gitmodules paths get updated automatically"
echo "3. Determine if manual .gitmodules editing is needed"
echo "4. Assess whether subdatasets need special handling"
