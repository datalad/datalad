#!/bin/sh

set -eu

MIN_VERSION="$(perl -ne 'print $1 if /^ *GIT_MIN_VERSION = "(\S+)"$/' datalad/support/gitrepo.py)"
if test -z "$MIN_VERSION"
then
    echo "Failed to extract minimum git version" >&2
    exit 1
fi

target_dir="$PWD/git-src"
git clone https://github.com/git/git "$target_dir"
cd "$target_dir"
git checkout "refs/tags/v$MIN_VERSION"
make --jobs 2
./git version
