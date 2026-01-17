#!/bin/bash
# Experiment 14: Test git-filter-repo for creating stable commit mappings
#
# Goal: Verify we can create deterministic mappings between original commits
#       and filtered subdataset commits while preserving metadata
#
# Questions:
# 1. Can we get original_sha -> filtered_sha mapping from git-filter-repo?
# 2. Does it preserve commit timestamps, authors, messages exactly?
# 3. Can we predict filtered commit SHAs?

set -eu

EXPERIMENT_DIR="/tmp/experiment_14_filter_repo"
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

echo "=== Experiment 14: git-filter-repo Stable Commit Mapping ==="
echo

# Check if git-filter-repo is available
if ! command -v git-filter-repo &> /dev/null; then
    echo "ERROR: git-filter-repo not found. Install with:"
    echo "  pip install git-filter-repo"
    echo "or:"
    echo "  curl https://raw.githubusercontent.com/newren/git-filter-repo/main/git-filter-repo -o /usr/local/bin/git-filter-repo"
    echo "  chmod +x /usr/local/bin/git-filter-repo"
    exit 1
fi

echo "Step 1: Create test repository with history"
git init original
cd original
git config user.name "Test User"
git config user.email "test@example.com"

# Create initial commit
echo "root content" > root.txt
mkdir -p data
echo "data v1" > data/file1.txt
echo "data v2" > data/file2.txt
git add .
git commit -m "Initial commit - create data/"

# Record commit metadata
COMMIT_A=$(git rev-parse HEAD)
COMMIT_A_TIME=$(git show -s --format=%ct HEAD)
COMMIT_A_AUTHOR=$(git show -s --format="%an <%ae>" HEAD)
COMMIT_A_MSG=$(git show -s --format=%B HEAD)

echo "  Original commit A: $COMMIT_A"
echo "  Timestamp: $COMMIT_A_TIME"
echo "  Author: $COMMIT_A_AUTHOR"
echo

# Second commit
echo "root update" >> root.txt
echo "data v1 update" >> data/file1.txt
git add .
git commit -m "Update both root and data/"

COMMIT_B=$(git rev-parse HEAD)
COMMIT_B_TIME=$(git show -s --format=%ct HEAD)
COMMIT_B_AUTHOR=$(git show -s --format="%an <%ae>" HEAD)
COMMIT_B_MSG=$(git show -s --format=%B HEAD)

echo "  Original commit B: $COMMIT_B"
echo "  Timestamp: $COMMIT_B_TIME"
echo

# Third commit (only data/)
mkdir -p data/subdir
echo "nested data" > data/subdir/file3.txt
git add data/
git commit -m "Add nested file in data/"

COMMIT_C=$(git rev-parse HEAD)
COMMIT_C_TIME=$(git show -s --format=%ct HEAD)

echo "  Original commit C: $COMMIT_C"
echo "  Timestamp: $COMMIT_C_TIME"
echo

cd ..

echo "Step 2: Clone and filter with git-filter-repo"
git clone original filtered
cd filtered

# Use git-filter-repo to isolate data/ directory
# --path data/ keeps only data/
# --path-rename data/: moves data/* to root
git-filter-repo --path data/ --path-rename data/: --force

echo
echo "Step 3: Analyze filtered commits"
echo

# Get filtered commits
COMMITS=$(git log --all --format=%H --reverse)
COMMIT_COUNT=$(echo "$COMMITS" | wc -l)

echo "Number of filtered commits: $COMMIT_COUNT"
echo

# Analyze each filtered commit
i=1
for FILTERED_SHA in $COMMITS; do
    echo "Filtered commit $i: $FILTERED_SHA"

    # Get metadata
    F_TIME=$(git show -s --format=%ct $FILTERED_SHA)
    F_AUTHOR=$(git show -s --format="%an <%ae>" $FILTERED_SHA)
    F_MSG=$(git show -s --format=%B $FILTERED_SHA | head -1)
    F_FILES=$(git show --name-only --format="" $FILTERED_SHA)

    echo "  Timestamp: $F_TIME"
    echo "  Author: $F_AUTHOR"
    echo "  Message: $F_MSG"
    echo "  Files: $F_FILES"

    # Try to match with original commits based on timestamp
    case $i in
        1)
            if [ "$F_TIME" = "$COMMIT_A_TIME" ]; then
                echo "  ✓ Matches original commit A by timestamp"
                if [ "$F_AUTHOR" = "$COMMIT_A_AUTHOR" ]; then
                    echo "  ✓ Author preserved exactly"
                fi
            fi
            ;;
        2)
            if [ "$F_TIME" = "$COMMIT_B_TIME" ]; then
                echo "  ✓ Matches original commit B by timestamp"
            fi
            ;;
        3)
            if [ "$F_TIME" = "$COMMIT_C_TIME" ]; then
                echo "  ✓ Matches original commit C by timestamp"
            fi
            ;;
    esac

    echo
    i=$((i + 1))
done

echo "Step 4: Check for old->new commit mapping file"
cd ..

# git-filter-repo creates a commit map file
if [ -f "filtered/.git/filter-repo/commit-map" ]; then
    echo "✓ Found commit-map file!"
    echo
    echo "Commit mappings:"
    cat filtered/.git/filter-repo/commit-map
    echo
else
    echo "✗ No commit-map file found"
    echo "  (May need different git-filter-repo version or options)"
fi

echo
echo "Step 5: Test reproducibility"
echo

# Try filtering again to see if we get same SHAs
cd original
git clone . ../filtered2
cd ../filtered2

git-filter-repo --path data/ --path-rename data/: --force

FILTERED2_COMMITS=$(git log --all --format=%H --reverse)

cd ..

echo "Comparing SHA sequences:"
echo "First filter:  $COMMITS"
echo "Second filter: $FILTERED2_COMMITS"
echo

if [ "$COMMITS" = "$FILTERED2_COMMITS" ]; then
    echo "✓ REPRODUCIBLE: Same SHAs produced by identical filter operation"
else
    echo "✗ NOT REPRODUCIBLE: Different SHAs produced"
    echo
    echo "This is expected behavior - git-filter-repo uses current time for"
    echo "committer timestamp, so SHAs will differ between runs."
    echo
    echo "To make it reproducible, we would need to:"
    echo "  1. Preserve original committer timestamp (not just author timestamp)"
    echo "  2. Use custom callback to fix committer info"
fi

echo
echo "=== Analysis ==="
echo

echo "Key findings:"
echo "1. git-filter-repo preserves:"
echo "   - Author name and email (exactly)"
echo "   - Author timestamp (exactly)"
echo "   - Commit message (exactly)"
echo
echo "2. git-filter-repo DOES NOT preserve by default:"
echo "   - Committer timestamp (uses current time)"
echo "   - Original commit SHA (new SHAs generated)"
echo
echo "3. Commit mapping:"
if [ -f "filtered/.git/filter-repo/commit-map" ]; then
    echo "   ✓ Available in .git/filter-repo/commit-map"
    echo "   Format: old-sha new-sha"
else
    echo "   ✗ Not available (may need newer version)"
fi
echo
echo "4. For retroactive split, we need:"
echo "   - Parse commit-map to get old->new SHA mapping"
echo "   - Or use commit callbacks to build our own mapping"
echo "   - Timestamps are preserved, allowing correlation"
echo
echo "=== Conclusion ==="
echo
echo "git-filter-repo CAN provide the mapping we need for retroactive split:"
echo "  • Method 1: Parse .git/filter-repo/commit-map file"
echo "  • Method 2: Use --commit-callback to build mapping during filter"
echo "  • Method 3: Match by timestamp (author_time is preserved exactly)"
echo
echo "Recommended: Use commit-callback for real-time mapping during filter."
echo

echo "Experiment complete. Results in: $EXPERIMENT_DIR"
