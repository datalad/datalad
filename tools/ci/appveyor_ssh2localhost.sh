#!/bin/sh

set -e -u

cat tools/ci/appveyor_ssh_config >> ~/.ssh/config
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
