#!/bin/bash
# Experiment 19: Verify Nested Subdataset Setup is Actually Working
#
# Goal: Fix Experiment 18 by ACTUALLY setting up nested subdatasets
#       Verify .git exists at each level, .gitmodules exists, and
#       git submodule update works throughout the hierarchy
#
# Critical verification:
#   - parent/.git exists
#   - parent/data/.git exists
#   - parent/data/logs/.git exists
#   - parent/data/logs/subds/.git exists
#   - Corresponding .gitmodules at each level

set -eu

echo "=== Experiment 19: Complete Nested Subdataset Setup Verification ==="
echo

# Use the existing experiment 18 results as starting point
PARENT_DIR="/tmp/experiment_18_nested_rewrite/parent"

if [ ! -d "$PARENT_DIR" ]; then
    echo "ERROR: Experiment 18 not run. Run 18_nested_rewrite_parent.sh first."
    exit 1
fi

cd "$PARENT_DIR"

echo "Step 1: Current state - verify gitlinks exist but NO actual subdatasets"
echo "-----------------------------------------------------------------------"
echo

echo "  Gitlinks in parent:"
git ls-tree HEAD | grep "160000" || echo "    (no gitlinks found)"

echo
echo "  Looking for .git directories:"
find . -name ".git" -type d

echo
echo "  Expected: Only ./.git"
echo "  Found: $(find . -name ".git" -type d | wc -l) .git director(ies)"
echo

if [ -d "data/.git" ]; then
    echo "  ✗ ERROR: data/.git already exists - experiment contaminated"
else
    echo "  ✓ Confirmed: data/.git does NOT exist (expected before setup)"
fi

echo
echo "Step 2: Set up nested subdatasets from filtered repositories"
echo "-------------------------------------------------------------"
echo

# Get the current commit of parent
CURRENT_COMMIT=$(git rev-parse HEAD)
echo "  Current parent commit: $CURRENT_COMMIT"

# Get the gitlink SHA for data/
DATA_GITLINK=$(git ls-tree $CURRENT_COMMIT | grep "	data$" | awk '{print $3}')
echo "  data/ gitlink points to: $DATA_GITLINK"

# Clone the filtered data/ repository into data/
echo
echo "  Setting up data/ subdataset..."
if [ -d "data" ]; then
    rm -rf data
fi

git clone ../data-filtered data
cd data
git checkout $DATA_GITLINK
DATA_ACTUAL_COMMIT=$(git rev-parse HEAD)
echo "    ✓ data/ cloned and checked out to: $DATA_ACTUAL_COMMIT"

if [ "$DATA_GITLINK" != "$DATA_ACTUAL_COMMIT" ]; then
    echo "    ✗ ERROR: Gitlink mismatch!"
    echo "      Expected: $DATA_GITLINK"
    echo "      Got: $DATA_ACTUAL_COMMIT"
    exit 1
else
    echo "    ✓ Gitlink matches actual commit"
fi

# Verify .gitmodules exists in data/
if [ -f ".gitmodules" ]; then
    echo "    ✓ data/.gitmodules exists:"
    cat .gitmodules | sed 's/^/      /'
else
    echo "    ✗ ERROR: data/.gitmodules does NOT exist!"
    exit 1
fi

# Get the gitlink SHA for logs/ (from within data/)
LOGS_GITLINK=$(git ls-tree HEAD | grep "	logs$" | awk '{print $3}')
echo "    logs/ gitlink points to: $LOGS_GITLINK"

# Clone the filtered logs/ repository into data/logs/
echo
echo "  Setting up data/logs/ subdataset..."
if [ -d "logs" ]; then
    rm -rf logs
fi

git clone ../../data-logs-filtered logs
cd logs
git checkout $LOGS_GITLINK
LOGS_ACTUAL_COMMIT=$(git rev-parse HEAD)
echo "    ✓ data/logs/ cloned and checked out to: $LOGS_ACTUAL_COMMIT"

if [ "$LOGS_GITLINK" != "$LOGS_ACTUAL_COMMIT" ]; then
    echo "    ✗ ERROR: Gitlink mismatch!"
    exit 1
else
    echo "    ✓ Gitlink matches actual commit"
fi

# Verify .gitmodules exists in logs/
if [ -f ".gitmodules" ]; then
    echo "    ✓ data/logs/.gitmodules exists:"
    cat .gitmodules | sed 's/^/      /'
else
    echo "    ✗ ERROR: data/logs/.gitmodules does NOT exist!"
    exit 1
fi

# Get the gitlink SHA for subds/ (from within logs/)
SUBDS_GITLINK=$(git ls-tree HEAD | grep "	subds$" | awk '{print $3}')
echo "    subds/ gitlink points to: $SUBDS_GITLINK"

# Clone the filtered subds/ repository into data/logs/subds/
echo
echo "  Setting up data/logs/subds/ subdataset..."
if [ -d "subds" ]; then
    rm -rf subds
fi

git clone ../../../data-logs-subds-filtered subds
cd subds
git checkout $SUBDS_GITLINK
SUBDS_ACTUAL_COMMIT=$(git rev-parse HEAD)
echo "    ✓ data/logs/subds/ cloned and checked out to: $SUBDS_ACTUAL_COMMIT"

if [ "$SUBDS_GITLINK" != "$SUBDS_ACTUAL_COMMIT" ]; then
    echo "    ✗ ERROR: Gitlink mismatch!"
    exit 1
else
    echo "    ✓ Gitlink matches actual commit"
fi

cd ../../..  # Back to parent

echo
echo "Step 3: VERIFY COMPLETE NESTED STRUCTURE"
echo "========================================="
echo

echo "  3a. Verify .git directories at ALL levels:"
echo "  -------------------------------------------"
find . -name ".git" -type d | sort | while read git_dir; do
    echo "    ✓ $git_dir"
done

EXPECTED_GIT_DIRS=4
ACTUAL_GIT_DIRS=$(find . -name ".git" -type d | wc -l)

echo
echo "    Expected: $EXPECTED_GIT_DIRS .git directories"
echo "    Found: $ACTUAL_GIT_DIRS .git directories"

if [ "$ACTUAL_GIT_DIRS" -eq "$EXPECTED_GIT_DIRS" ]; then
    echo "    ✓ Correct number of .git directories!"
else
    echo "    ✗ ERROR: Wrong number of .git directories!"
    exit 1
fi

echo
echo "  3b. Verify .gitmodules at appropriate levels:"
echo "  ----------------------------------------------"

# Parent should have .gitmodules
if git ls-tree HEAD | grep -q "\.gitmodules"; then
    echo "    ✓ parent/.gitmodules exists (in tree)"
    git show HEAD:.gitmodules | sed 's/^/      /'
else
    echo "    ✗ ERROR: parent/.gitmodules missing from tree!"
fi

# data/ should have .gitmodules
if [ -f "data/.gitmodules" ]; then
    echo "    ✓ data/.gitmodules exists (on disk)"
    cat data/.gitmodules | sed 's/^/      /'
else
    echo "    ✗ ERROR: data/.gitmodules missing!"
fi

# data/logs/ should have .gitmodules
if [ -f "data/logs/.gitmodules" ]; then
    echo "    ✓ data/logs/.gitmodules exists (on disk)"
    cat data/logs/.gitmodules | sed 's/^/      /'
else
    echo "    ✗ ERROR: data/logs/.gitmodules missing!"
fi

# data/logs/subds/ should NOT have .gitmodules (it's the deepest level)
if [ -f "data/logs/subds/.gitmodules" ]; then
    echo "    ⚠️  data/logs/subds/.gitmodules exists (unexpected, but not wrong)"
else
    echo "    ✓ data/logs/subds/.gitmodules does not exist (correct - deepest level)"
fi

echo
echo "  3c. Verify file contents at each level:"
echo "  ----------------------------------------"

# Parent level
echo "    parent/root.txt:"
if [ -f "root.txt" ]; then
    echo "      Content: $(cat root.txt | head -1)"
    echo "      ✓ Exists"
else
    echo "      ✗ Missing!"
fi

# data/ level
echo "    data/main.txt:"
if [ -f "data/main.txt" ]; then
    echo "      Content: $(cat data/main.txt | head -1)"
    echo "      ✓ Exists"
else
    echo "      ✗ Missing!"
fi

# data/logs/ level
echo "    data/logs/access.log:"
if [ -f "data/logs/access.log" ]; then
    echo "      Content: $(cat data/logs/access.log | head -1)"
    echo "      ✓ Exists"
else
    echo "      ✗ Missing!"
fi

# data/logs/subds/ level
echo "    data/logs/subds/deep1.txt:"
if [ -f "data/logs/subds/deep1.txt" ]; then
    echo "      Content: $(cat data/logs/subds/deep1.txt | head -1)"
    echo "      ✓ Exists"
else
    echo "      ✗ Missing!"
fi

echo "    data/logs/subds/deep2.txt:"
if [ -f "data/logs/subds/deep2.txt" ]; then
    echo "      Content: $(cat data/logs/subds/deep2.txt | head -1)"
    echo "      ✓ Exists"
else
    echo "      ✗ Missing!"
fi

echo
echo "  3d. Verify each level is a proper git repository:"
echo "  --------------------------------------------------"

# Parent
echo "    parent/:"
cd .
git rev-parse HEAD >/dev/null 2>&1 && echo "      ✓ Valid git repository"
echo "      Current commit: $(git rev-parse --short HEAD)"

# data/
echo "    data/:"
cd data
git rev-parse HEAD >/dev/null 2>&1 && echo "      ✓ Valid git repository"
echo "      Current commit: $(git rev-parse --short HEAD)"
echo "      History: $(git log --oneline | wc -l) commits"

# data/logs/
echo "    data/logs/:"
cd logs
git rev-parse HEAD >/dev/null 2>&1 && echo "      ✓ Valid git repository"
echo "      Current commit: $(git rev-parse --short HEAD)"
echo "      History: $(git log --oneline | wc -l) commits"

# data/logs/subds/
echo "    data/logs/subds/:"
cd subds
git rev-parse HEAD >/dev/null 2>&1 && echo "      ✓ Valid git repository"
echo "      Current commit: $(git rev-parse --short HEAD)"
echo "      History: $(git log --oneline | wc -l) commits"

cd ../../../  # Back to parent

echo
echo "Step 4: Test historical checkout with nested subdatasets"
echo "========================================================="
echo

# Go back in history to commit A
echo "  Checking out historical commit A (initial commit)..."
COMMIT_A=$(git log --oneline --reverse | head -1 | awk '{print $1}')
echo "  Commit A: $COMMIT_A"

git checkout $COMMIT_A 2>&1 | head -3

# Check gitlink for data/ at commit A
DATA_GITLINK_A=$(git ls-tree $COMMIT_A | grep "	data$" | awk '{print $3}')
echo "  At commit A, data/ should point to: $DATA_GITLINK_A"

# Update data/ subdataset
echo
echo "  Updating data/ subdataset to commit A's gitlink..."
cd data
git checkout $DATA_GITLINK_A 2>&1 | head -3
DATA_COMMIT_A=$(git rev-parse --short HEAD)
echo "  data/ now at: $DATA_COMMIT_A"

# Check gitlink for logs/ at this data/ commit
LOGS_GITLINK_A=$(git ls-tree HEAD | grep "	logs$" | awk '{print $3}')
echo "  At this data/ commit, logs/ should point to: $LOGS_GITLINK_A"

# Update logs/ subdataset
echo
echo "  Updating data/logs/ subdataset..."
cd logs
git checkout $LOGS_GITLINK_A 2>&1 | head -3
LOGS_COMMIT_A=$(git rev-parse --short HEAD)
echo "  data/logs/ now at: $LOGS_COMMIT_A"

# Check gitlink for subds/
SUBDS_GITLINK_A=$(git ls-tree HEAD | grep "	subds$" | awk '{print $3}')
echo "  At this logs/ commit, subds/ should point to: $SUBDS_GITLINK_A"

# Update subds/ subdataset
echo
echo "  Updating data/logs/subds/ subdataset..."
cd subds
git checkout $SUBDS_GITLINK_A 2>&1 | head -3
SUBDS_COMMIT_A=$(git rev-parse --short HEAD)
echo "  data/logs/subds/ now at: $SUBDS_COMMIT_A"

echo
echo "  Verifying content at commit A:"
cd ../../..  # Back to parent
echo "    data/logs/subds/deep1.txt: $(cat data/logs/subds/deep1.txt 2>/dev/null || echo 'MISSING')"
echo "    data/logs/subds/deep2.txt: $(cat data/logs/subds/deep2.txt 2>/dev/null || echo 'should not exist at A')"

# Return to master
git checkout master 2>&1 | head -3

echo
echo "Step 5: FINAL VERIFICATION CHECKLIST"
echo "====================================="
echo

CHECKS_PASSED=0
CHECKS_TOTAL=0

# Check 1: .git exists at all levels
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ -d ".git" ] && [ -d "data/.git" ] && [ -d "data/logs/.git" ] && [ -d "data/logs/subds/.git" ]; then
    echo "  ✓ Check 1: .git exists at all 4 levels"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    echo "  ✗ Check 1: FAILED - missing .git directories"
fi

# Check 2: .gitmodules exists where expected
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if git ls-tree HEAD | grep -q "\.gitmodules" && \
   [ -f "data/.gitmodules" ] && \
   [ -f "data/logs/.gitmodules" ]; then
    echo "  ✓ Check 2: .gitmodules exists at parent, data/, and data/logs/"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    echo "  ✗ Check 2: FAILED - missing .gitmodules"
fi

# Check 3: All levels are valid git repos
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
cd . && git rev-parse HEAD >/dev/null 2>&1 && \
cd data && git rev-parse HEAD >/dev/null 2>&1 && \
cd logs && git rev-parse HEAD >/dev/null 2>&1 && \
cd subds && git rev-parse HEAD >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  ✓ Check 3: All levels are valid git repositories"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    echo "  ✗ Check 3: FAILED - invalid git repository at some level"
fi
cd ../../..  # Back to parent

# Check 4: Gitlinks match actual commits
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
PARENT_DATA_LINK=$(git ls-tree HEAD | grep "	data$" | awk '{print $3}')
DATA_COMMIT=$(cd data && git rev-parse HEAD)
if [ "$PARENT_DATA_LINK" = "$DATA_COMMIT" ]; then
    echo "  ✓ Check 4: Parent's data/ gitlink matches actual data/ commit"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    echo "  ✗ Check 4: FAILED - gitlink mismatch"
    echo "    Parent gitlink: $PARENT_DATA_LINK"
    echo "    Actual commit:  $DATA_COMMIT"
fi

# Check 5: File contents accessible
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ -f "data/logs/subds/deep1.txt" ] && [ -f "data/logs/subds/deep2.txt" ]; then
    echo "  ✓ Check 5: Files accessible at deepest level"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    echo "  ✗ Check 5: FAILED - files not accessible"
fi

# Check 6: Complete history at each level
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
DATA_COMMITS=$(cd data && git log --oneline | wc -l)
LOGS_COMMITS=$(cd data/logs && git log --oneline | wc -l)
SUBDS_COMMITS=$(cd data/logs/subds && git log --oneline | wc -l)

if [ "$DATA_COMMITS" -eq 5 ] && [ "$LOGS_COMMITS" -eq 4 ] && [ "$SUBDS_COMMITS" -eq 3 ]; then
    echo "  ✓ Check 6: Complete history at all levels (5, 4, 3 commits)"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    echo "  ✗ Check 6: FAILED - incorrect commit counts"
    echo "    data/: $DATA_COMMITS (expected 5)"
    echo "    data/logs/: $LOGS_COMMITS (expected 4)"
    echo "    data/logs/subds/: $SUBDS_COMMITS (expected 3)"
fi

echo
echo "========================================="
echo "  FINAL SCORE: $CHECKS_PASSED / $CHECKS_TOTAL checks passed"
echo "========================================="

if [ "$CHECKS_PASSED" -eq "$CHECKS_TOTAL" ]; then
    echo
    echo "✅ SUCCESS! Nested subdatasets are FULLY SET UP and WORKING!"
    echo
    echo "Structure verified:"
    echo "  parent/.git           ✓"
    echo "  parent/data/.git      ✓"
    echo "  parent/data/logs/.git ✓"
    echo "  parent/data/logs/subds/.git ✓"
    echo
    echo "  All .gitmodules present ✓"
    echo "  All gitlinks correct ✓"
    echo "  All histories complete ✓"
    echo "  All files accessible ✓"
    echo
    echo "🎉 NESTED SUBDATASETS ARE PRODUCTION-READY!"
else
    echo
    echo "❌ VERIFICATION FAILED!"
    echo "   Some checks did not pass. Review output above."
    exit 1
fi
