#!/bin/bash
# Experiment 3: Git-Annex Metadata Cleanup Verification
# Purpose: Verify that git annex forget properly cleans up metadata
# Expected: .log.met and .log.web files should be reduced, only relevant keys remain

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp03"
echo "=== Experiment 3: Git-Annex Metadata Cleanup ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Step 1: Create dataset with many annexed files
echo -e "\n[Step 1] Creating dataset with annexed content..."
datalad create source-dataset
cd source-dataset

# Create multiple directories with annexed content
for subject in 01 02 03; do
    mkdir -p "data/subject${subject}"
    for session in 1 2 3; do
        # Create some annexed files
        dd if=/dev/urandom of="data/subject${subject}/session${session}.dat" bs=1M count=2 2>/dev/null
        echo "Metadata for subject${subject} session${session}" > "data/subject${subject}/session${session}.txt"
    done
done

datalad save -m "Add multiple subjects with annexed content"

# Add some web URLs for some files (to populate .log.web)
git annex addurl --file data/subject01/remote.txt https://example.com/data1.txt --relaxed || echo "addurl skipped"
git annex addurl --file data/subject02/remote.txt https://example.com/data2.txt --relaxed || echo "addurl skipped"
datalad save -m "Add some web URLs" || echo "No changes to save"

# Step 2: Examine git-annex branch before filtering
echo -e "\n[Step 2] Examining git-annex branch BEFORE filtering..."
git checkout git-annex 2>/dev/null || echo "No git-annex branch yet"
if [ $? -eq 0 ]; then
    echo "Files in git-annex branch:"
    find . -name "*.log*" -type f | wc -l
    echo "Total size of .log files:"
    find . -name "*.log*" -type f -exec du -ch {} + | tail -1

    # Sample some log content
    echo -e "\nSample .log.met file:"
    find . -name "*.log.met" -type f | head -1 | xargs head -5 2>/dev/null || echo "No .log.met files"

    echo -e "\nSample .log.web file:"
    find . -name "*.log.web" -type f | head -1 | xargs cat 2>/dev/null || echo "No .log.web files"

    git checkout master 2>/dev/null || git checkout main
fi

# Count keys before filtering
echo -e "\nKeys in repository before filtering:"
git annex info --fast 2>/dev/null || echo "No annex info available"

# Step 3: Clone and filter for subject01 only
echo -e "\n[Step 3] Cloning and filtering for subject01..."
cd "$EXPERIMENT_DIR"
git clone source-dataset filtered-subject01
cd filtered-subject01

# Record pre-filter git-annex branch
echo "Git-annex branch commits before filtering:"
git log --oneline git-annex | head -10

# Step 4: Run filter-branch WITHOUT git annex forget
echo -e "\n[Step 4] Running filter-branch WITHOUT git annex forget..."
cd "$EXPERIMENT_DIR"
git clone source-dataset test-no-forget
cd test-no-forget

git annex filter-branch data/subject01 --include-all-key-information 2>&1 || echo "filter-branch failed"
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD
git annex dead origin 2>/dev/null || echo "Could not mark origin dead"
git remote rm origin

echo "Analyzing WITHOUT git annex forget:"
git checkout git-annex 2>/dev/null
if [ $? -eq 0 ]; then
    echo "Number of .log files:"
    find . -name "*.log*" -type f | wc -l
    echo "Size of .log files:"
    find . -name "*.log*" -type f -exec du -ch {} + 2>/dev/null | tail -1

    # Check if logs for OTHER subjects still exist
    echo -e "\nLooking for subject02/subject03 references in logs:"
    if grep -r "subject02\|subject03" . 2>/dev/null | head -5; then
        echo "⚠ Found references to other subjects (metadata not cleaned)"
    else
        echo "✓ No references to other subjects found"
    fi
    git checkout master 2>/dev/null || git checkout main
fi

# Step 5: Run filter-branch WITH git annex forget
echo -e "\n[Step 5] Running filter-branch WITH git annex forget..."
cd "$EXPERIMENT_DIR/filtered-subject01"

git annex filter-branch data/subject01 --include-all-key-information 2>&1 || echo "filter-branch failed"
git filter-branch --subdirectory-filter data/subject01 --prune-empty HEAD
git annex dead origin 2>/dev/null || echo "Could not mark origin dead"
git remote rm origin

echo "Running git annex forget --force --drop-dead..."
git annex forget --force --drop-dead 2>&1

echo "Analyzing WITH git annex forget:"
git checkout git-annex 2>/dev/null
if [ $? -eq 0 ]; then
    echo "Number of .log files:"
    find . -name "*.log*" -type f | wc -l
    echo "Size of .log files:"
    find . -name "*.log*" -type f -exec du -ch {} + 2>/dev/null | tail -1

    echo -e "\nLooking for subject02/subject03 references in logs:"
    if grep -r "subject02\|subject03" . 2>/dev/null | head -5; then
        echo "⚠ Still found references to other subjects"
    else
        echo "✓ No references to other subjects (metadata properly cleaned)"
    fi
    git checkout master 2>/dev/null || git checkout main
fi

# Step 6: Compare results
echo -e "\n[Step 6] Comparing results..."
echo "=== SIZE COMPARISON ==="

cd "$EXPERIMENT_DIR"
ORIGINAL_GIT_SIZE=$(du -sb source-dataset/.git | cut -f1)
NO_FORGET_SIZE=$(du -sb test-no-forget/.git | cut -f1)
WITH_FORGET_SIZE=$(du -sb filtered-subject01/.git | cut -f1)

echo "Original .git size:     $(du -sh source-dataset/.git | cut -f1) ($ORIGINAL_GIT_SIZE bytes)"
echo "Without forget:         $(du -sh test-no-forget/.git | cut -f1) ($NO_FORGET_SIZE bytes)"
echo "With forget:            $(du -sh filtered-subject01/.git | cut -f1) ($WITH_FORGET_SIZE bytes)"

WITHOUT_FORGET_REDUCTION=$(( 100 - (NO_FORGET_SIZE * 100 / ORIGINAL_GIT_SIZE) ))
WITH_FORGET_REDUCTION=$(( 100 - (WITH_FORGET_SIZE * 100 / ORIGINAL_GIT_SIZE) ))
FORGET_BENEFIT=$(( WITH_FORGET_REDUCTION - WITHOUT_FORGET_REDUCTION ))

echo -e "\nReduction without forget: ${WITHOUT_FORGET_REDUCTION}%"
echo "Reduction with forget:    ${WITH_FORGET_REDUCTION}%"
echo "Additional benefit:       ${FORGET_BENEFIT}%"

# Step 7: Verify file availability
echo -e "\n[Step 7] Verifying file availability in filtered dataset..."
cd filtered-subject01

echo "Files in filtered dataset:"
find . -type f -not -path './.git/*' | sort

echo -e "\nChecking if annexed files are still accessible:"
for file in session*.dat; do
    if [ -f "$file" ]; then
        echo -n "  $file: "
        if git annex info "$file" 2>/dev/null | grep -q "present"; then
            echo "✓ accessible"
        else
            echo "⚠ metadata exists but may not be accessible"
        fi
    fi
done

echo -e "\n=== Experiment 3 Complete ==="
echo "Datasets available at:"
echo "  Original:        $EXPERIMENT_DIR/source-dataset"
echo "  Without forget:  $EXPERIMENT_DIR/test-no-forget"
echo "  With forget:     $EXPERIMENT_DIR/filtered-subject01"

echo -e "\n=== KEY FINDINGS ==="
echo "1. Measure actual size reduction from git annex forget"
echo "2. Verify unwanted metadata is removed"
echo "3. Confirm wanted files remain accessible"
echo "4. Assess cost/benefit of forget operation"
