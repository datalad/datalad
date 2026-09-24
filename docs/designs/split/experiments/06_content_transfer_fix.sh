#!/bin/bash
# Experiment 6: Content Transfer - Fixing the Critical Issue
# Purpose: Verify that annexed content can be properly transferred to split datasets
# Expected: Split dataset should have access to all annexed content

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp06"
echo "=== Experiment 6: Content Transfer Fix ==="
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

# Step 3: Clone and split - METHOD 1: Without preserving origin
echo -e "\n[Step 3] METHOD 1: Split WITHOUT preserving content link..."
cd "$EXPERIMENT_DIR"
git -c protocol.file.allow=always clone parent-dataset split-no-content
cd split-no-content

git annex filter-branch data/subject01 --include-all-key-information 2>&1 | tail -1
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD 2>&1 | tail -1
git annex dead origin 2>/dev/null || true
git remote rm origin 2>/dev/null || true
git annex forget --force --drop-dead 2>&1 | tail -1

echo "Result - Method 1:"
echo "  Files: $(find . -name '*.dat' -o -name '*.txt' | wc -l)"
echo "  Annexed content present: $(git annex find --in=here | wc -l)"
echo "  Annexed content missing: $(git annex find --not --in=here | wc -l)"

# Step 4: Clone and split - METHOD 2: Preserving origin as source
echo -e "\n[Step 4] METHOD 2: Split WITH preserved content link..."
cd "$EXPERIMENT_DIR"
git -c protocol.file.allow=always clone parent-dataset split-with-source
cd split-with-source

# CRITICAL: Don't mark origin as dead or remove it yet!
git annex filter-branch data/subject01 --include-all-key-information 2>&1 | tail -1
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD 2>&1 | tail -1

# Update the remote URL to point to the original's absolute path
git remote set-url origin "$(realpath "$EXPERIMENT_DIR/parent-dataset")"

# Now try to get the content
echo "Attempting to get content from origin..."
datalad get . 2>&1 || echo "Get may have failed"

echo "Result - Method 2:"
echo "  Files: $(find . -name '*.dat' -o -name '*.txt' | wc -l)"
echo "  Annexed content present: $(git annex find --in=here | wc -l)"
echo "  Annexed content missing: $(git annex find --not --in=here | wc -l)"

if git annex find --in=here | grep -q .; then
    echo "  ✓ SUCCESS: Content was retrieved!"
else
    echo "  ✗ FAILURE: No content retrieved"
fi

# Step 5: Clone and split - METHOD 3: Copy content before filtering
echo -e "\n[Step 5] METHOD 3: Copy annexed objects BEFORE splitting..."
cd "$EXPERIMENT_DIR"
git -c protocol.file.allow=always clone parent-dataset split-copy-objects
cd split-copy-objects

# CRITICAL: Get all content BEFORE filtering
echo "Getting all content before filter..."
git annex get data/subject01/ 2>&1 | tail -3

echo "Content before filtering:"
git annex find --in=here data/subject01/ || echo "None"

# Now filter
git annex filter-branch data/subject01 --include-all-key-information 2>&1 | tail -1
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD 2>&1 | tail -1

# Clean up remote references
git annex dead origin 2>/dev/null || true
git remote rm origin 2>/dev/null || true
git annex forget --force --drop-dead 2>&1 | tail -1

echo "Result - Method 3:"
echo "  Files: $(find . -name '*.dat' -o -name '*.txt' | wc -l)"
echo "  Annexed content present: $(git annex find --in=here | wc -l)"
echo "  Annexed content missing: $(git annex find --not --in=here | wc -l)"

if git annex find --in=here | grep -q .; then
    echo "  ✓ SUCCESS: Content survived filtering!"
    echo "  Content can be accessed:"
    ls -lh *.dat 2>/dev/null || echo "  (no .dat files visible)"
else
    echo "  ✗ FAILURE: Content lost during filtering"
fi

# Step 6: Verify content accessibility
echo -e "\n[Step 6] Final verification across all methods..."
echo ""
echo "METHOD 1 (no source):"
cd "$EXPERIMENT_DIR/split-no-content"
if [ -f data.dat ]; then
    if [ -L data.dat ]; then
        echo "  data.dat: symlink (content not present)"
    else
        echo "  data.dat: $(stat -c%s data.dat 2>/dev/null || stat -f%z data.dat) bytes"
    fi
else
    echo "  data.dat: missing"
fi

echo ""
echo "METHOD 2 (kept source):"
cd "$EXPERIMENT_DIR/split-with-source"
if [ -f data.dat ]; then
    if [ -L data.dat ]; then
        TARGET=$(readlink data.dat)
        if [ -f "$TARGET" ]; then
            echo "  data.dat: symlink → $(stat -c%s "$TARGET" 2>/dev/null || stat -f%z "$TARGET") bytes (✓ accessible)"
        else
            echo "  data.dat: symlink → broken (✗ not accessible)"
        fi
    else
        echo "  data.dat: $(stat -c%s data.dat 2>/dev/null || stat -f%z data.dat) bytes (✓ present)"
    fi
else
    echo "  data.dat: missing"
fi

echo ""
echo "METHOD 3 (copied before filter):"
cd "$EXPERIMENT_DIR/split-copy-objects"
if [ -f data.dat ]; then
    if [ -L data.dat ]; then
        TARGET=$(readlink data.dat)
        if [ -f "$TARGET" ]; then
            echo "  data.dat: symlink → $(stat -c%s "$TARGET" 2>/dev/null || stat -f%z "$TARGET") bytes (✓ accessible)"
        else
            echo "  data.dat: symlink → broken (✗ not accessible)"
        fi
    else
        echo "  data.dat: $(stat -c%s data.dat 2>/dev/null || stat -f%z data.dat) bytes (✓ present)"
    fi
else
    echo "  data.dat: missing"
fi

# Summary
echo -e "\n=== Experiment 6 Complete ==="
echo ""
echo "KEY FINDINGS:"
echo "1. Method 1 (no source): Content is NOT available"
echo "2. Method 2 (kept source): Content SHOULD be retrievable from origin"
echo "3. Method 3 (copy first): Content SHOULD survive the split"
echo ""
echo "RECOMMENDED APPROACH for implementation:"
echo "- MUST copy annexed content BEFORE splitting"
echo "- OR maintain origin as a special remote"
echo "- Simply filtering git history is NOT sufficient!"
