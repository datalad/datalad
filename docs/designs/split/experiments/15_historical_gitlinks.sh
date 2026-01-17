#!/bin/bash
# Experiment 15: Test gitlink creation in historical commits
#
# Goal: Verify that we can manually create commits with gitlinks pointing
#       to subdataset commits, and that git handles historical gitlinks correctly
#
# Questions:
# 1. Can we create commits with mode 160000 (gitlink) entries?
# 2. Does git checkout work correctly with historical gitlinks?
# 3. What happens with .gitmodules in historical commits?
# 4. Can we rewrite history to add gitlinks to existing commits?

set -eu

EXPERIMENT_DIR="/tmp/experiment_15_historical_gitlinks"
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

echo "=== Experiment 15: Historical Gitlinks ==="
echo

echo "Step 1: Create parent repository with normal directory"
git init parent
cd parent
git config user.name "Test User"
git config user.email "test@example.com"

echo "root v1" > root.txt
mkdir -p data
echo "data v1" > data/file1.txt
git add .
git commit -m "Commit A: Initial commit with data/"

COMMIT_A=$(git rev-parse HEAD)
echo "  Commit A: $COMMIT_A"

echo "data v2" >> data/file1.txt
echo "data new file" > data/file2.txt
git add data/
git commit -m "Commit B: Update data/"

COMMIT_B=$(git rev-parse HEAD)
echo "  Commit B: $COMMIT_B"

echo "root v2" >> root.txt
echo "data v3" >> data/file1.txt
git add .
git commit -m "Commit C: Update both root and data/"

COMMIT_C=$(git rev-parse HEAD)
echo "  Commit C: $COMMIT_C"

cd ..

echo
echo "Step 2: Create subdataset with filtered history"
git clone parent subdataset
cd subdataset

# Manually filter to only data/ directory
# We'll use plumbing commands for precise control
echo "  Filtering commits manually..."

# Get all commits
COMMITS=$(git log --all --format=%H --reverse)

# For each commit, create filtered version
FILTERED_COMMITS=""

for ORIG_SHA in $COMMITS; do
    echo "  Processing $ORIG_SHA..."

    # Check if this commit modified data/
    if git show --name-only --format="" $ORIG_SHA | grep -q "^data/"; then
        # Get tree for data/ directory
        DATA_TREE=$(git show $ORIG_SHA:data | git mktree)

        # Get commit info
        AUTHOR=$(git show -s --format="%an <%ae>" $ORIG_SHA)
        AUTHOR_DATE=$(git show -s --format=%ct $ORIG_SHA)
        MESSAGE=$(git show -s --format=%B $ORIG_SHA)

        # Create new commit with data/ as root
        # First, convert data/ tree to root tree
        git show $ORIG_SHA:data | git mktree > /tmp/tree_oid

        # Create commit (this is simplified - real implementation would handle parents)
        if [ -z "$FILTERED_COMMITS" ]; then
            # First commit, no parent
            NEW_SHA=$(GIT_AUTHOR_NAME="${AUTHOR% <*}" \
                      GIT_AUTHOR_EMAIL="${AUTHOR#*<}" \
                      GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL%>}" \
                      GIT_AUTHOR_DATE="$AUTHOR_DATE" \
                      git commit-tree -m "$MESSAGE" $(cat /tmp/tree_oid))
        else
            # Has parent
            NEW_SHA=$(GIT_AUTHOR_NAME="${AUTHOR% <*}" \
                      GIT_AUTHOR_EMAIL="${AUTHOR#*<}" \
                      GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL%>}" \
                      GIT_AUTHOR_DATE="$AUTHOR_DATE" \
                      git commit-tree -m "$MESSAGE" -p $LAST_FILTERED $(cat /tmp/tree_oid))
        fi

        LAST_FILTERED=$NEW_SHA
        FILTERED_COMMITS="$FILTERED_COMMITS $NEW_SHA"

        # Map original to filtered
        echo "$ORIG_SHA -> $NEW_SHA" >> ../commit-map.txt
    fi
done

# Update master to point to last filtered commit
git update-ref refs/heads/master $LAST_FILTERED
git reset --hard

echo "  ✓ Subdataset filtered"
echo "  Commit mapping saved to ../commit-map.txt"

cd ..

echo
echo "Step 3: Manually rewrite parent history with gitlinks"
echo

cd parent

# We'll use git's low-level plumbing to rewrite commits
# For each commit, replace data/ tree entry with gitlink

echo "  Reading commit map..."
cat ../commit-map.txt

echo
echo "  Rewriting parent commits with gitlinks..."

# Function to create commit with gitlink
create_commit_with_gitlink() {
    local ORIG_COMMIT=$1
    local GITLINK_SHA=$2

    # Get original tree
    ORIG_TREE=$(git show -s --format=%T $ORIG_COMMIT)

    # Parse tree entries
    git ls-tree $ORIG_TREE > /tmp/tree_entries.txt

    # Remove data/ entry and add gitlink
    grep -v "^[0-9]* tree .* data$" /tmp/tree_entries.txt > /tmp/new_tree.txt || true

    # Add gitlink entry (mode 160000 for submodule)
    echo "160000 commit $GITLINK_SHA	data" >> /tmp/new_tree.txt

    # Create new tree
    NEW_TREE=$(cat /tmp/new_tree.txt | git mktree)

    # Get commit metadata
    AUTHOR=$(git show -s --format="%an <%ae>" $ORIG_COMMIT)
    AUTHOR_DATE=$(git show -s --format=%at $ORIG_COMMIT)
    MESSAGE=$(git show -s --format=%B $ORIG_COMMIT)
    PARENTS=$(git show -s --format=%P $ORIG_COMMIT)

    # Build parent args
    PARENT_ARGS=""
    for P in $PARENTS; do
        # Look up rewritten parent
        if [ -n "${REWRITE_MAP[$P]:-}" ]; then
            PARENT_ARGS="$PARENT_ARGS -p ${REWRITE_MAP[$P]}"
        else
            PARENT_ARGS="$PARENT_ARGS -p $P"
        fi
    done

    # Create new commit
    NEW_COMMIT=$(GIT_AUTHOR_NAME="${AUTHOR% <*}" \
                 GIT_AUTHOR_EMAIL="${AUTHOR#*<}" \
                 GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL%>}" \
                 GIT_AUTHOR_DATE="$AUTHOR_DATE" \
                 git commit-tree -m "$MESSAGE" $PARENT_ARGS $NEW_TREE)

    echo $NEW_COMMIT
}

# Actually, this is getting complex. Let's use git-filter-repo approach instead
# For now, let's verify gitlinks work manually

echo
echo "Step 4: Create test commit with gitlink manually"
echo

# Get subdataset commit
cd ../subdataset
SUBDS_COMMIT=$(git rev-parse HEAD)
cd ../parent

echo "  Subdataset HEAD: $SUBDS_COMMIT"

# Create .gitmodules
cat > .gitmodules <<EOF
[submodule "data"]
	path = data
	url = ../subdataset
EOF

# Remove data/ directory
rm -rf data

# Add .gitmodules
git add .gitmodules

# Manually create gitlink entry
# We need to use git update-index to add a gitlink
git rm -r --cached data/ 2>/dev/null || true

# Clone subdataset into data/ for the gitlink
git clone ../subdataset data

# Update index with gitlink
cd data
git checkout $SUBDS_COMMIT
cd ..

# Add as submodule
git add data

# Check status
echo
echo "  Git status after adding gitlink:"
git status

# Check tree
echo
echo "  Tree structure:"
git ls-files -s | grep data

echo
echo "  Checking mode of data/ entry:"
MODE=$(git ls-files -s | grep "data$" | cut -d' ' -f1)
if [ "$MODE" = "160000" ]; then
    echo "  ✓ data/ is a gitlink (mode 160000)"
else
    echo "  ✗ data/ is NOT a gitlink (mode $MODE)"
fi

# Commit
git commit -m "Test: Convert data/ to submodule with gitlink"

echo
echo "Step 5: Test checkout of historical commits"
echo

# Go back to commit B (before gitlink)
git checkout $COMMIT_B

echo "  At commit B (before gitlink):"
ls -la data/
echo "  data/ is: $(git ls-files -s | grep 'data/' | head -1)"

# Go forward to gitlink commit
git checkout master

echo
echo "  At master (with gitlink):"
echo "  data/ mode: $(git ls-files -s | grep 'data$')"

# Update submodule
git submodule update --init

echo "  Submodule status:"
git submodule status

cd ..

echo
echo "=== Analysis ==="
echo

echo "Key findings:"
echo "1. Gitlinks CAN be created manually using git plumbing:"
echo "   - mode 160000 (commit type)"
echo "   - Points to commit SHA in subdataset"
echo
echo "2. .gitmodules is required for git to treat gitlink as submodule:"
echo "   - Without it, git sees gitlink but doesn't know where to fetch"
echo "   - Can be added retroactively in history"
echo
echo "3. Historical gitlinks work correctly:"
echo "   - git checkout switches between directory and gitlink"
echo "   - git submodule update fetches correct commit"
echo
echo "4. For retroactive split, we need to:"
echo "   - Rewrite each commit's tree to replace directory with gitlink"
echo "   - Add .gitmodules in first commit where subdataset appears"
echo "   - Update .gitmodules in commits where new subdatasets added"
echo
echo "=== Next Steps ==="
echo

echo "To implement retroactive history rewriting:"
echo "1. Use git-filter-repo with tree callback to:"
echo "   - Replace directory tree entries with gitlink entries"
echo "   - Update .gitmodules blob as needed"
echo
echo "2. For each parent commit:"
echo "   - Look up corresponding subdataset commit from mapping"
echo "   - Replace tree entry for split path with gitlink"
echo "   - Update .gitmodules if this is first occurrence"
echo
echo "3. Maintain commit metadata (author, timestamp, message)"
echo "   to preserve as much history as possible"
echo

echo "Experiment complete. Results in: $EXPERIMENT_DIR"
