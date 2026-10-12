#!/bin/bash
# Code duplication detection.
# Run via: tox -e duplication
# Requires: npx (Node.js)

set -eu

# Pinned so a new jscpd release can't change behavior or fail CI on an
# otherwise-unchanged commit. Bump deliberately (and re-verify) when needed.
JSCPD_VERSION=5.3.3

if ! command -v npx >/dev/null 2>&1; then
    echo "ERROR: npx not found. Install Node.js to run duplication checks."
    exit 1
fi

echo "=== Code duplication check (jscpd ${JSCPD_VERSION}) ==="
echo

# jscpd reads .jscpd.json for config (threshold, format, ignores, etc.)
npx --yes "jscpd@${JSCPD_VERSION}" datalad
