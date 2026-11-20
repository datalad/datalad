#!/bin/bash
# Experiment 16: Rewrite Parent Mode with Nested Subdatasets
#
# Goal: Test rewrite-parent mode with nested subdataset structures
#       to ensure gitlinks and .gitmodules are correct at all levels
#
# Scenario:
#   parent/
#     ├── root.txt
#     ├── data/
#     │   ├── file1.txt
#     │   └── subjects/
#     │       ├── sub01/
#     │       │   └── data.txt
#     │       └── sub02/
#     │           └── data.txt
#     └── analysis/
#         └── results.txt
#
# Split plan:
#   1. Split data/subjects/sub01 into subdataset
#   2. Split data/subjects/sub02 into subdataset
#   3. Split data/subjects into subdataset (now contains sub01 and sub02 as subdatasets)
#   4. Rewrite parent history to make structure retroactive
#
# Questions:
#   1. Can we maintain nested .gitmodules correctly?
#   2. Do gitlinks work at multiple levels?
#   3. How to handle commits that span multiple nesting levels?
#   4. What order should we filter (bottom-up)?

set -eu

EXPERIMENT_DIR="/tmp/experiment_16_rewrite_nested"
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

echo "=== Experiment 16: Rewrite Parent with Nested Subdatasets ==="
echo

echo "Step 1: Create parent repository with nested structure"
git init parent
cd parent
git config user.name "Test User"
git config user.email "test@example.com"

# Commit A: Initial structure
echo "root v1" > root.txt
mkdir -p data/subjects/sub01 data/subjects/sub02 analysis
echo "data v1" > data/file1.txt
echo "sub01 v1" > data/subjects/sub01/data.txt
echo "sub02 v1" > data/subjects/sub02/data.txt
echo "analysis v1" > analysis/results.txt

git add .
git commit -m "A: Initial commit with nested structure"
COMMIT_A=$(git rev-parse HEAD)
COMMIT_A_TIME=$(git show -s --format=%ct HEAD)

echo "  Commit A: $COMMIT_A"
echo "  Structure created with nested directories"
echo

# Commit B: Update files at multiple levels
echo "root v2" >> root.txt
echo "data v2" >> data/file1.txt
echo "sub01 v2" >> data/subjects/sub01/data.txt

git add .
git commit -m "B: Update files at root, data, and sub01 levels"
COMMIT_B=$(git rev-parse HEAD)
COMMIT_B_TIME=$(git show -s --format=%ct HEAD)

echo "  Commit B: $COMMIT_B"
echo "  Updated across multiple levels"
echo

# Commit C: Add nested file
mkdir -p data/subjects/sub01/session1
echo "session data" > data/subjects/sub01/session1/scan.txt

git add .
git commit -m "C: Add nested directory in sub01"
COMMIT_C=$(git rev-parse HEAD)
COMMIT_C_TIME=$(git show -s --format=%ct HEAD)

echo "  Commit C: $COMMIT_C"
echo "  Added deeper nesting"
echo

# Commit D: Update sub02
echo "sub02 v2" >> data/subjects/sub02/data.txt
echo "analysis v2" >> analysis/results.txt

git add .
git commit -m "D: Update sub02 and analysis"
COMMIT_D=$(git rev-parse HEAD)
COMMIT_D_TIME=$(git show -s --format=%ct HEAD)

echo "  Commit D: $COMMIT_D"
echo

cd ..

echo "Step 2: Create filtered subdatasets (bottom-up order)"
echo

# 2a: Filter sub01
echo "  Filtering data/subjects/sub01..."
git clone parent sub01
cd sub01

# Filter to only data/subjects/sub01
git filter-branch --subdirectory-filter data/subjects/sub01 --prune-empty HEAD

echo "    sub01 filtered commits:"
git log --oneline --all
echo

# Build commit mapping for sub01
declare -A SUB01_MAP
while read line; do
    orig_time=$(echo "$line" | cut -d' ' -f1)
    filtered_sha=$(echo "$line" | cut -d' ' -f2)

    # Match by timestamp (approximation)
    case $orig_time in
        $COMMIT_A_TIME) SUB01_MAP[A]=$filtered_sha ;;
        $COMMIT_B_TIME) SUB01_MAP[B]=$filtered_sha ;;
        $COMMIT_C_TIME) SUB01_MAP[C]=$filtered_sha ;;
    esac
done < <(git log --all --format="%ct %H")

cd ..

# 2b: Filter sub02
echo "  Filtering data/subjects/sub02..."
git clone parent sub02
cd sub02

git filter-branch --subdirectory-filter data/subjects/sub02 --prune-empty HEAD

echo "    sub02 filtered commits:"
git log --oneline --all
echo

declare -A SUB02_MAP
while read line; do
    orig_time=$(echo "$line" | cut -d' ' -f1)
    filtered_sha=$(echo "$line" | cut -d' ' -f2)

    case $orig_time in
        $COMMIT_A_TIME) SUB02_MAP[A]=$filtered_sha ;;
        $COMMIT_D_TIME) SUB02_MAP[D]=$filtered_sha ;;
    esac
done < <(git log --all --format="%ct %H")

cd ..

# 2c: Filter data/subjects (will contain sub01 and sub02 as subdatasets)
echo "  Filtering data/subjects..."
git clone parent subjects
cd subjects

git filter-branch --subdirectory-filter data/subjects --prune-empty HEAD

echo "    subjects filtered commits:"
git log --oneline --all
echo

# For this intermediate level, we need to:
# 1. Keep the directory structure but replace sub01/ and sub02/ with gitlinks

echo "    Converting sub01/ and sub02/ to gitlinks in subjects/"

# This is the tricky part - we need to rewrite the tree of each commit
# to replace directories with gitlinks

# For now, let's just note what needs to happen:
echo "    TODO: Rewrite trees to convert subdirectories to gitlinks"
echo "    - Each commit needs sub01/ → gitlink to sub01 commit"
echo "    - Each commit needs sub02/ → gitlink to sub02 commit"
echo "    - .gitmodules needs to be added"
echo

cd ..

# 2d: Filter data/ (will contain subjects as subdataset)
echo "  Filtering data/..."
git clone parent data
cd data

git filter-branch --subdirectory-filter data --prune-empty HEAD

echo "    data/ filtered commits:"
git log --oneline --all
echo

cd ..

echo
echo "Step 3: Analyze what parent history rewriting needs to do"
echo

cd parent

echo "For each commit in parent history, need to:"
echo

echo "Commit A ($COMMIT_A):"
echo "  Current tree structure:"
git ls-tree -r $COMMIT_A | grep -E "data/|analysis" | head -10
echo
echo "  Should become (after rewrite):"
echo "    160000 commit ${SUB01_MAP[A]:-<sub01-A>}   data/subjects/sub01"
echo "    160000 commit ${SUB02_MAP[A]:-<sub02-A>}   data/subjects/sub02"
echo "    100644 blob   <data-tree>                  data/file1.txt"
echo "    100644 blob   <analysis-tree>              analysis/results.txt"
echo "    100644 blob   <gitmodules>                 .gitmodules"
echo

echo "Commit B ($COMMIT_B):"
echo "  Affected paths: root.txt, data/file1.txt, data/subjects/sub01/data.txt"
echo "  Should have:"
echo "    - Updated root.txt blob"
echo "    - Updated data/file1.txt blob"
echo "    - Updated gitlink for sub01 → ${SUB01_MAP[B]:-<sub01-B>}"
echo "    - Unchanged gitlink for sub02"
echo

echo "Commit C ($COMMIT_C):"
echo "  Affected paths: data/subjects/sub01/session1/scan.txt"
echo "  Should have:"
echo "    - Updated gitlink for sub01 → ${SUB01_MAP[C]:-<sub01-C>}"
echo "    - Unchanged gitlink for sub02"
echo

echo "Commit D ($COMMIT_D):"
echo "  Affected paths: analysis/results.txt, data/subjects/sub02/data.txt"
echo "  Should have:"
echo "    - Updated analysis/results.txt blob"
echo "    - Updated gitlink for sub02 → ${SUB02_MAP[D]:-<sub02-D>}"
echo "    - Unchanged gitlink for sub01"
echo

cd ..

echo
echo "Step 4: Test manual tree rewriting (proof of concept)"
echo

cd parent

echo "  Creating test commit with gitlinks manually..."

# Get current tree
CURRENT_TREE=$(git write-tree)

# Extract tree entries (excluding data/ subtree)
git ls-tree $CURRENT_TREE | grep -v "^[0-9]* tree .* data$" > /tmp/tree_entries.txt
git ls-tree $CURRENT_TREE | grep -v "^[0-9]* tree .* analysis$" >> /tmp/tree_entries_filtered.txt 2>/dev/null || true

# Add gitlinks manually (using plumbing)
# Note: This is simplified - real implementation would need to recursively handle nested structure

echo "  Tree entries before rewrite:"
git ls-tree $CURRENT_TREE | head -10

# For a full implementation, we would:
# 1. Walk the tree recursively
# 2. For each directory being split (data/subjects/sub01, data/subjects/sub02, etc.)
# 3. Replace tree entry with gitlink (mode 160000)
# 4. Update .gitmodules blob

echo
echo "  Manual tree rewriting would involve:"
echo "    1. git mktree < modified_entries.txt"
echo "    2. git commit-tree -m 'message' -p <parent> <new-tree>"
echo "    3. Repeat for entire history"
echo

cd ..

echo
echo "=== Key Findings ==="
echo

echo "1. NESTED SUBDATASET CHALLENGES:"
echo "   - Must process bottom-up (deepest subdatasets first)"
echo "   - Each level needs its own .gitmodules"
echo "   - Gitlinks must be updated when child subdatasets change"
echo

echo "2. COMMIT MAPPING COMPLEXITY:"
echo "   - Need to track: original_commit → subdataset_commit for EACH subdataset"
echo "   - Example: Commit A has THREE mappings:"
echo "     - A → sub01 commit a1"
echo "     - A → sub02 commit a2"
echo "     - A → subjects commit (which itself references a1 and a2)"
echo

echo "3. TREE REWRITING REQUIREMENTS:"
echo "   - Can't just use git-filter-branch (operates on whole repo)"
echo "   - Need custom tree manipulation:"
echo "     a. Read original tree"
echo "     b. Replace specific paths with gitlinks"
echo "     c. Add/update .gitmodules blob"
echo "     d. Create new tree"
echo "     e. Create new commit with new tree"
echo

echo "4. .GITMODULES EVOLUTION:"
echo "   - Commit A: Add entries for sub01, sub02"
echo "   - Intermediate commits: Update gitlinks but .gitmodules unchanged"
echo "   - If new subdatasets added later: Update .gitmodules"
echo

echo "5. ORDER OF OPERATIONS:"
echo "   - Bottom-up is CRITICAL:"
echo "     1. Filter sub01 and sub02 (deepest)"
echo "     2. Create subjects with sub01/sub02 as subdatasets"
echo "     3. Create data with subjects as subdataset"
echo "     4. Rewrite parent to have data as subdataset"
echo

echo "6. VERIFICATION NEEDED:"
echo "   - At each historical commit:"
echo "     git checkout <commit>"
echo "     git submodule update --init --recursive"
echo "   - Should reconstruct the exact tree that existed at that point"
echo

echo
echo "=== Recommended Implementation Approach ==="
echo

echo "Use git-filter-repo with callbacks:"
echo

cat << 'PYTHON_CODE'
import git_filter_repo as fr

class NestedSubdatasetRewriter:
    def __init__(self, split_paths, commit_maps):
        """
        split_paths: ['data/subjects/sub01', 'data/subjects/sub02', ...]
        commit_maps: {
            'data/subjects/sub01': {orig_sha: filtered_sha, ...},
            'data/subjects/sub02': {orig_sha: filtered_sha, ...},
        }
        """
        self.split_paths = sorted(split_paths, key=lambda x: -x.count('/'))
        self.commit_maps = commit_maps

    def commit_callback(self, commit, metadata):
        # Get original tree
        tree = parse_tree(commit.tree)

        # Process each split path (deepest first)
        for split_path in self.split_paths:
            # Check if this commit affected this path
            if path_in_tree(tree, split_path):
                # Get corresponding subdataset commit
                subdataset_commit = self.commit_maps[split_path].get(
                    commit.original_id
                )

                if subdataset_commit:
                    # Replace tree entry with gitlink
                    tree = replace_with_gitlink(
                        tree,
                        split_path,
                        subdataset_commit
                    )

        # Update .gitmodules
        gitmodules_content = build_gitmodules(self.split_paths)
        tree = add_blob(tree, '.gitmodules', gitmodules_content)

        # Rebuild commit with new tree
        commit.file_changes = rebuild_tree(tree)

# Usage:
rewriter = NestedSubdatasetRewriter(
    split_paths=[
        'data/subjects/sub01',
        'data/subjects/sub02',
    ],
    commit_maps={
        'data/subjects/sub01': sub01_map,
        'data/subjects/sub02': sub02_map,
    }
)

filter = fr.RepoFilter(
    args,
    commit_callback=rewriter.commit_callback
)
filter.run()
PYTHON_CODE

echo
echo "=== Next Steps for Full Implementation ==="
echo

echo "1. Implement tree manipulation functions:"
echo "   - parse_tree(tree_sha) → tree_dict"
echo "   - replace_with_gitlink(tree_dict, path, commit_sha)"
echo "   - build_gitmodules(split_paths) → blob_content"
echo "   - rebuild_tree(tree_dict) → new_tree_sha"
echo

echo "2. Build commit mapping for all subdatasets:"
echo "   - Filter each subdataset (bottom-up)"
echo "   - Map original commit → filtered commit by timestamp/message"
echo "   - Store mapping: {path: {orig_sha: filtered_sha}}"
echo

echo "3. Rewrite parent history:"
echo "   - Use git-filter-repo with commit callback"
echo "   - For each commit, update tree with gitlinks"
echo "   - Add/update .gitmodules as needed"
echo

echo "4. Handle corner cases:"
echo "   - Commits that don't affect split paths (skip gitlink update)"
echo "   - Commits that add new subdatasets (update .gitmodules)"
echo "   - Merge commits (preserve merge structure)"
echo

echo "5. Verify results:"
echo "   - git fsck (no dangling references)"
echo "   - Checkout each commit and verify submodule update works"
echo "   - Compare trees: original vs rewritten (should be equivalent)"
echo

echo
echo "Experiment complete. Results in: $EXPERIMENT_DIR"
echo
echo "Key insight: Nested subdatasets are feasible but require careful"
echo "bottom-up processing and precise tree manipulation at each level."
