#!/bin/bash
#
# Provision a macOS (GitHub-hosted) runner for the datalad test suite:
# Homebrew packages, a short socket-path scratch dir, and a local SSH
# server for DATALAD_TESTS_SSH-gated tests to talk to (Linux instead uses
# docker-based SSH targets via tools/ci/prep-travis-forssh.sh -- macOS,
# like Windows, mirrors AppVeyor's approach of SSHing to itself).
set -eo pipefail

brew install exempi

# UNIX domain socket paths (used by git-annex/SSH connection multiplexing)
# are capped at ~104 chars on macOS; keep them under a short, fixed
# directory rather than risking a long $TMPDIR-derived one tripping that
# limit -- same reasoning as AppVeyor's DATALAD_LOCATIONS_SOCKETS setting.
mkdir -p /tmp/dl-sockets
echo "DATALAD_LOCATIONS_SOCKETS=/tmp/dl-sockets" >> "$GITHUB_ENV"

# --- SSH server, for DATALAD_TESTS_SSH ---
# Remote Login is off by default on macOS.
sudo systemsetup -setremotelogin on

mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -f ~/.ssh/id_rsa -N ""
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
cat tools/ci/ssh_config >> ~/.ssh/config
chmod -R go-rwx ~/.ssh

# "datalad-test"/"datalad-test2" are the hostnames the test suite connects
# to (see tools/ci/ssh_config and DATALAD_TESTS_SSH); AppVeyor provided
# these via its `hosts:` config section, GitHub Actions has no equivalent
# so point them at localhost via the hosts file instead.
printf '127.0.0.1 datalad-test\n127.0.0.1 datalad-test2\n' | sudo tee -a /etc/hosts >/dev/null

# Verify the setup before tests rely on it.
ssh -o StrictHostKeyChecking=no localhost exit
ssh -o StrictHostKeyChecking=no datalad-test exit
ssh -o StrictHostKeyChecking=no datalad-test2 exit
