#!/bin/bash
#
# Provision a Linux (GitHub-hosted Ubuntu) runner for the datalad test
# suite: NeuroDebian + the APT packages the tests need, and the sudo/git
# tweaks that the "install for a regular user, but be able to run a subset
# of tests under `sudo -E`" setup in test.yml relies on later.
set -eo pipefail

# The ultimate one-liner setup for NeuroDebian repository
bash <(wget -q -O- https://neuro.debian.net/_files/neurodebian-ci-setup.sh)
sudo apt-get update -qq
sudo apt-get install -y eatmydata  # to speedup some installations
tools/ci/prep-travis-forssh.sh
tools/ci/debians_disable_outdated_ssl_cert
# Install various basic dependencies
sudo eatmydata apt-get install -y zip pandoc p7zip-full
# needed for tests of patool compression fall-back solution
sudo eatmydata apt-get install -y xz-utils
sudo eatmydata apt-get install -y shunit2
[ -z "${LC_ALL:-}" ] || sudo eatmydata apt-get install -y locales-all

# We do `sudo pip install` later (see test.yml), and versioneer needs to
# run git; recent git insists on being told it's safe to operate on a
# directory owned by another user (root, in a sudo'ed call) before it will.
sudo git config --global --add safe.directory "$PWD"

# So a later `sudo -E` test run (used to test operation under root) keeps
# PATH pointing at the user-installed location instead of resetting it.
sudo sed -i -e 's/^Defaults.*secure_path.*$//' /etc/sudoers
