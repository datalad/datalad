#!/bin/bash
# Experiment 5: Real-World Dataset Validation
# Purpose: Test split workflow on real dataset with nested structure and validate full content retrieval
# Expected: Split dataset should allow complete content retrieval via datalad get

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp05"
echo "=== Experiment 5: Real-World Dataset Validation ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
chmod -R +w "$EXPERIMENT_DIR" 2>/dev/null || true
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Create a realistic test dataset with nested structure
echo -e "\n[Step 1] Creating realistic test dataset with nested structure..."
datalad create -c text2git parent-dataset
cd parent-dataset

# Create a complex directory structure similar to real neuroscience datasets
mkdir -p data/raw/subject01/{func,anat}
mkdir -p data/raw/subject02/{func,anat}
mkdir -p data/derivatives/subject01
mkdir -p code/analysis

# Add some files with content
echo "Subject 01 functional scan" > data/raw/subject01/func/scan1.txt
echo "Subject 01 anatomical scan" > data/raw/subject01/anat/anat1.txt
echo "Subject 02 functional scan" > data/raw/subject02/func/scan1.txt
echo "Subject 02 anatomical scan" > data/raw/subject02/anat/anat1.txt

# Create annexed content
dd if=/dev/urandom of=data/raw/subject01/func/bold.nii.gz bs=1M count=2 2>/dev/null
dd if=/dev/urandom of=data/raw/subject01/anat/T1w.nii.gz bs=1M count=1 2>/dev/null
dd if=/dev/urandom of=data/raw/subject02/func/bold.nii.gz bs=1M count=2 2>/dev/null

# Add analysis script
echo "#!/usr/bin/env python3" > code/analysis/process.py
echo "print('Processing data')" >> code/analysis/process.py

# Create a nested subdataset
echo "Creating nested subdataset in data/derivatives..."
datalad create -d . data/derivatives/analysis-v1
echo "Derivative data" > data/derivatives/analysis-v1/results.txt
datalad save -d data/derivatives/analysis-v1 -m "Add results"

datalad save -m "Complete dataset with nested subdataset"

# Step 2: Record initial state
echo -e "\n[Step 2] Recording initial state..."
echo "Directory structure:"
find data code -type f | sort
echo -e "\nSubdatasets:"
datalad subdatasets || echo "No subdatasets"
echo -e "\nAnnexed files:"
git annex find || echo "No annexed files"

# Step 3: Test basic split on subject01
echo -e "\n[Step 3] Splitting data/raw/subject01 into subdataset..."
cd "$EXPERIMENT_DIR"
git -c protocol.file.allow=always clone parent-dataset split-subject01
cd split-subject01

# Run the split workflow
echo "Running git-annex filter-branch..."
git annex filter-branch data/raw/subject01 --include-all-key-information 2>&1 | tail -3

echo "Running git filter-branch..."
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter data/raw/subject01 --prune-empty HEAD 2>&1 | tail -3

echo "Cleaning up..."
git annex dead origin 2>/dev/null || true
git remote rm origin 2>/dev/null || true
git annex forget --force --drop-dead 2>&1 | tail -3

# Step 4: CRITICAL - Verify content is accessible
echo -e "\n[Step 4] VERIFYING CONTENT ACCESSIBILITY..."
echo "Files in split dataset:"
find . -type f -not -path './.git/*' | sort

echo -e "\nChecking annexed file status:"
git annex find --not --in=here || echo "No annexed files missing content"

echo -e "\nAttempting to get all annexed content:"
if git annex find --not --in=here | grep -q .; then
    echo "⚠️ Some annexed files are not present locally"
    echo "Files that need to be retrieved:"
    git annex find --not --in=here
    echo -e "\nAttempting datalad get..."
    # This will fail because we don't have the original remote anymore
    datalad get . 2>&1 || echo "Expected failure - no remote available"
else
    echo "✓ All annexed content is present"
fi

echo -e "\nVerifying file content integrity:"
for file in func/bold.nii.gz anat/T1w.nii.gz; do
    if [ -f "$file" ]; then
        SIZE=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null)
        echo "  $file: $SIZE bytes"
        if [ "$SIZE" -gt 0 ]; then
            echo "    ✓ File has content"
        else
            echo "    ✗ File is empty!"
        fi
    fi
done

# Step 5: Test roundtrip - can we clone and get content?
echo -e "\n[Step 5] Testing roundtrip (clone split dataset)..."
cd "$EXPERIMENT_DIR"

# First, create a "remote" by copying the split dataset
cp -r split-subject01 split-subject01-remote

# Now clone from it
git -c protocol.file.allow=always clone split-subject01-remote split-subject01-clone
cd split-subject01-clone

echo "Cloned dataset contents:"
ls -la

echo -e "\nAnnexed files status in clone:"
git annex find --not --in=here || echo "All content present"

echo -e "\nAttempting to get all content in clone:"
datalad get -r . 2>&1 || echo "Get completed or failed"

echo "Final verification:"
for file in func/bold.nii.gz anat/T1w.nii.gz; do
    if [ -f "$file" ]; then
        if [ -L "$file" ]; then
            echo "  $file: ✓ symlink exists"
            if git annex whereis "$file" >/dev/null 2>&1; then
                echo "    ✓ git-annex knows where to find it"
            else
                echo "    ✗ git-annex doesn't know where it is"
            fi
        else
            SIZE=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null)
            echo "  $file: ✓ $SIZE bytes (content present)"
        fi
    else
        echo "  $file: ✗ MISSING"
    fi
done

# Step 6: Summary
echo -e "\n=== Experiment 5 Complete ==="
echo "Datasets available at:"
echo "  Original: $EXPERIMENT_DIR/parent-dataset"
echo "  Split: $EXPERIMENT_DIR/split-subject01"
echo "  Remote: $EXPERIMENT_DIR/split-subject01-remote"
echo "  Clone: $EXPERIMENT_DIR/split-subject01-clone"

echo -e "\n=== KEY FINDINGS ==="
echo "1. Can split dataset be created successfully?"
echo "2. Is annexed content accessible in split dataset?"
echo "3. Can split dataset be cloned?"
echo "4. Can content be retrieved via datalad get?"
echo "5. Does the split dataset maintain file availability information?"
