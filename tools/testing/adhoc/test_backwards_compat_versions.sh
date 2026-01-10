#!/bin/bash
# Test backwards compatibility: older datalad should be able to rerun
# commits created by newer datalad with "versions" field in run record.
#
# Usage: ./test_backwards_compat_versions.sh [OLD_DATALAD_VERSION]
# Default OLD_DATALAD_VERSION is 1.0.0

set -eu

OLD_VERSION="${1:-1.0.0}"
TESTDIR=$(mktemp -d)
CURRENT_DIR=$(pwd)

cleanup() {
    echo "Cleaning up $TESTDIR"
    # Need to make annexed files writable before removal
    chmod -R +w "$TESTDIR" 2>/dev/null || true
    rm -rf "$TESTDIR"
}
trap cleanup EXIT

echo "=== Backwards Compatibility Test for 'versions' field ==="
echo "Testing that datalad $OLD_VERSION can rerun commits from current version"
echo "Test directory: $TESTDIR"
echo

cd "$TESTDIR"

# Create virtual environments
echo "--- Creating venvs ---"
uv venv venv-current
uv venv venv-old

# Install current datalad (development version)
echo "--- Installing current datalad from $CURRENT_DIR ---"
uv pip install -p venv-current/bin/python -e "$CURRENT_DIR"

# Install old datalad
echo "--- Installing datalad==$OLD_VERSION ---"
uv pip install -p venv-old/bin/python "datalad==$OLD_VERSION"

# Show versions
echo "--- Installed versions ---"
echo "Current:"
venv-current/bin/python -c "import datalad; print(f'  datalad {datalad.__version__}')"
echo "Old:"
venv-old/bin/python -c "import datalad; print(f'  datalad {datalad.__version__}')"
echo

# Create test dataset with current datalad
echo "--- Creating test dataset with current datalad ---"
mkdir testds && cd testds
../venv-current/bin/datalad create -f .
echo "initial content" > input.txt
../venv-current/bin/datalad save -m "Add input file"

# Run a command with version capture enabled (default)
# Use -i for input and -o for output to properly handle annexed files
echo "--- Running command with version capture (current datalad) ---"
../venv-current/bin/datalad run -m "Test command with versions" \
    -i input.txt -o output.txt \
    "cat input.txt > output.txt && echo 'processed' >> output.txt"

# Show the run record
echo "--- Run record in commit message ---"
git log -1 --format="%B" | head -20
echo "..."
echo

# Verify versions field is present
if git log -1 --format="%B" | grep -q '"versions"'; then
    echo "✓ 'versions' field is present in run record"
else
    echo "✗ 'versions' field NOT found in run record"
    exit 1
fi
echo

# Now test with old datalad
echo "--- Testing rerun with datalad $OLD_VERSION ---"

# First, check if old datalad can at least parse the commit
echo "Attempting 'datalad rerun --report' with old version..."
if ../venv-old/bin/datalad rerun --report HEAD 2>&1; then
    echo "✓ Old datalad can report on the run commit"
else
    echo "⚠ Old datalad failed to report (may be expected)"
fi
echo

# Save the run commit hash before reset
RUN_COMMIT=$(git rev-parse HEAD)

# Reset to before the run and try actual rerun
echo "Resetting to parent commit and attempting actual rerun..."
git reset --hard HEAD~1

# Remove output file if it exists
rm -f output.txt

echo "Attempting to rerun commit $RUN_COMMIT with old datalad..."
if ../venv-old/bin/datalad rerun "$RUN_COMMIT" 2>&1; then
    echo "✓ Old datalad successfully reran the command!"
    echo
    echo "--- Resulting commit message ---"
    git log -1 --format="%B" | head -20
else
    EXITCODE=$?
    echo "✗ Old datalad FAILED to rerun (exit code: $EXITCODE)"
    echo
    echo "This may indicate a backwards compatibility issue!"
    exit 1
fi

echo
echo "=== SUCCESS: Backwards compatibility test PASSED ==="
echo "datalad $OLD_VERSION can rerun commits with 'versions' field"
