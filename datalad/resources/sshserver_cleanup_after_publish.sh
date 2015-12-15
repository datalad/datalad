#!/bin/sh
#
# This script is intended to be executed on a server;
# After the publishing of a collection, which was prepared by the corresponding
# sshserver_prepare_for_publish script, this script just checks out the master
# branches of the published repositories. It is called the same way as the
# preparation script
#
# Usage: ./sshserver_cleanup_after_publish /tmp/example democol ds1 ds2
#

set -e
set -u

ROOT_PATH=$1
COL_REPO_NAME=$2
shift 2


cd "$ROOT_PATH"
git -C "$COL_REPO_NAME" checkout -q master
printf "DATALAD_COLLECTION_REPO_%s: checkout_master DATALAD_END\n" "$COL_REPO_NAME"

for name in "$@"; do
    curdir=$PWD
    cd "$name"
    git checkout -q master
    printf "DATALAD_HANDLE_REPO_%s: checkout_master DATALAD_END\n" "$name"
    # call init to do things like enabling special remotes
    git annex init
    printf "DATALAD_HANDLE_REPO_%s: annex_init DATALAD_END\n" "$name"
    # TODO: getting the content may be an option instead.
    git annex get . || true
    printf "DATALAD_HANDLE_REPO_%s: annex_get_all DATALAD_END\n" "$name"
    cd "$curdir"
done