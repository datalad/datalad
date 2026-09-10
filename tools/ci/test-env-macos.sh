#!/bin/bash
#
# Provision a macOS (GitHub-hosted) runner for the datalad test suite.
set -eo pipefail

brew install exempi

# UNIX domain socket paths (used by git-annex/SSH connection multiplexing)
# are capped at ~104 chars on macOS; keep them under a short, fixed
# directory rather than risking a long $TMPDIR-derived one tripping that
# limit -- same reasoning as AppVeyor's DATALAD_LOCATIONS_SOCKETS setting.
mkdir -p /tmp/dl-sockets
echo "DATALAD_LOCATIONS_SOCKETS=/tmp/dl-sockets" >> "$GITHUB_ENV"
