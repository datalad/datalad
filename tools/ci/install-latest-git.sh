#!/bin/bash

set -e -u

# NOTE: Travis already has ppa:git-core/ppa set up.

                     # e.g., Candidate: 1:2.19.1-1~ppa0~ubuntu14.04.1
latest_git_version=$(apt-cache policy git | awk -F'[:-]' '/Candidate/{print $3;}')
                     # e.g., git version 2.19.1
bundled_git_version=$(/usr/lib/git-annex.linux/git --version | awk '{print $3;}')


if [ -z "$bundled_git_version" ]; then
    echo "E: bundled git not found "
    exit 1
elif [ -z "$latest_git_version" ]; then
    echo "E: latest git version could not be determined"
    exit 1
elif [ "$latest_git_version" = "$bundled_git_version" ]; then
    echo "I: latest git version $latest_git_version is same as bundled $bundled_git_version"
    exit 100
else
    sudo apt-get install -y git
fi
