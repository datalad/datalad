#!/bin/bash
# Experiment 1: Basic Filter Branch Test
# Purpose: Test basic git filter-branch + git-annex filter-branch workflow
# Expected: Resulting repo should only contain files from subdirectory, with cleaned metadata

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp01"
echo "=== Experiment 1: Basic Filter Branch ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Create a test dataset with multiple directories
echo -e "\n[Step 1] Creating test dataset..."
datalad create -c text2git source-dataset
cd source-dataset

# Create directory structure
mkdir -p data/subject01 data/subject02 code
echo "Subject 01 - Session 1" > data/subject01/session1.txt
echo "Subject 01 - Session 2" > data/subject01/session2.txt
echo "Subject 02 - Session 1" > data/subject02/session1.txt
echo "Analysis script" > code/analyze.py

# Create some annexed content
mkdir -p data/subject01/large
dd if=/dev/urandom of=data/subject01/large/file1.dat bs=1M count=5 2>/dev/null
dd if=/dev/urandom of=data/subject02/large/file2.dat bs=1M count=5 2>/dev/null

# Save everything
datalad save -m "Initial dataset with multiple subjects"

# Step 2: Record initial state
echo -e "\n[Step 2] Recording initial state..."
echo "Git repo size:"
du -sh .git
echo -e "\nGit-annex branch size:"
du -sh .git/annex 2>/dev/null || echo "N/A"
echo -e "\nFiles in dataset:"
find data code -type f
echo -e "\nGit log:"
git log --oneline --all
echo -e "\nKeys in git-annex:"
git annex info --fast 2>/dev/null || echo "N/A"

# Step 3: Clone for filtering
echo -e "\n[Step 3] Cloning dataset for filtering..."
cd "$EXPERIMENT_DIR"
git clone source-dataset filtered-subject01
cd filtered-subject01

# Step 4: Run git-annex filter-branch FIRST
echo -e "\n[Step 4] Running git-annex filter-branch..."
# Filter to only include keys from data/subject01
if git annex filter-branch data/subject01 --include-all-key-information --include-all-repo-config --include-global-config 2>&1; then
    echo "git-annex filter-branch completed successfully"
else
    echo "WARNING: git-annex filter-branch failed or not available"
fi

# Step 5: Run git filter-branch to extract subdirectory
echo -e "\n[Step 5] Running git filter-branch..."
# Use subdirectory-filter to make data/subject01 the root
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD

# Step 6: Clean up remote references
echo -e "\n[Step 6] Cleaning up remote references..."
if git annex dead origin 2>/dev/null; then
    echo "Marked origin as dead"
else
    echo "WARNING: Could not mark origin as dead (git-annex may not be initialized)"
fi
git remote rm origin || echo "No origin remote to remove"

# Step 7: Forget dead repositories
echo -e "\n[Step 7] Running git annex forget..."
if git annex forget --force --drop-dead 2>&1; then
    echo "git annex forget completed"
else
    echo "WARNING: git annex forget failed or not available"
fi

# Step 8: Analyze results
echo -e "\n[Step 8] Analyzing results..."
echo "=== RESULTS ==="
echo -e "\nDirectory contents:"
ls -la
echo -e "\nFiles in filtered repo:"
find . -type f -not -path './.git/*' | sort
echo -e "\nGit log after filtering:"
git log --oneline --all
echo -e "\nGit repo size after filtering:"
du -sh .git
echo -e "\nGit-annex branch after filtering:"
git log --oneline git-annex 2>/dev/null | head -5 || echo "N/A"

# Step 9: Verify file availability
echo -e "\n[Step 9] Verifying file availability..."
if [ -f "large/file1.dat" ]; then
    echo "large/file1.dat found"
    git annex info large/file1.dat 2>/dev/null || echo "Not tracked by git-annex"
fi
if [ -f "session1.txt" ]; then
    echo "session1.txt found"
    cat session1.txt
fi

# Step 10: Check for unwanted content
echo -e "\n[Step 10] Checking for unwanted content..."
if [ -f "session1.txt" ] && [ -f "session2.txt" ]; then
    echo "✓ Expected subject01 files present"
else
    echo "✗ WARNING: Expected files missing"
fi

if find . -name "subject02" -o -name "analyze.py" | grep -q .; then
    echo "✗ WARNING: Unwanted files from other directories still present!"
    find . -name "subject02" -o -name "analyze.py"
else
    echo "✓ No unwanted files from other directories"
fi

# Step 11: Compare sizes
echo -e "\n[Step 11] Size comparison..."
ORIGINAL_SIZE=$(du -sb "$EXPERIMENT_DIR/source-dataset/.git" | cut -f1)
FILTERED_SIZE=$(du -sb .git | cut -f1)
REDUCTION=$(( 100 - (FILTERED_SIZE * 100 / ORIGINAL_SIZE) ))
echo "Original .git size: $(du -sh "$EXPERIMENT_DIR/source-dataset/.git" | cut -f1)"
echo "Filtered .git size: $(du -sh .git | cut -f1)"
echo "Size reduction: ~${REDUCTION}%"

echo -e "\n=== Experiment 1 Complete ==="
echo "Filtered dataset available at: $EXPERIMENT_DIR/filtered-subject01"
echo "Original dataset available at: $EXPERIMENT_DIR/source-dataset"
