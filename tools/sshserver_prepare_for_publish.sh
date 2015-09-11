#!/bin/sh
#
# This script is intended to be executed on a server; it prepares a simple
# directory structure with repositories for a collection and its handles.
# It initializes them with git and (if available) git-annex. It returns
# a number of useful status messages on the target via stdout.
#
# Usage: ./sshserver_prepare_for_publish /tmp/example democol ds1 ds2
#

set -e
set -u

# TODO:think about different modes to tune accessibility of the published repos
ROOT_PATH=$1
COL_REPO_NAME=$2
shift 2

git_init_options=''
git_annex_init_options=''

printf "## start server capabilities ####\n"
printf "DATALAD_GIT_VERSION: %s DATALAD_END\n" `git --version`
printf "DATALAD_GIT_ANNEX_VERSION: %s DATALAD_END\n" `git annex version`
printf "## end server capabilities ####\n"

mkdir -p "$ROOT_PATH"
cd "$ROOT_PATH"
[ -d "$COL_REPO_NAME" ] && printf "error: target '%s' exists\n" "$COL_REPO_NAME" && exit 1
mkdir -p "$COL_REPO_NAME"
git -C "$COL_REPO_NAME" init $git_init_options
printf "DATALAD_COLLECTION_REPO_%s: init\n" "$COL_REPO_NAME"

for name in "$@"; do
    [ -d "$name" ] && printf "error: target '%s' exists\n" "$name" && exit 1
    mkdir -p "$name"
    git -C "$name" init $git_init_options
    printf "DATALAD_HANDLE_REPO_%s: init DATALAD_END\n" "$name"
    curdir=$PWD
    cd "$name"
    git annex init $git_annex_init_options \
        && printf "DATALAD_HANDLE_REPO_%s: annex_init DATALAD_END\nDATALAD_HANDLE_REPO_INFO_%s: %s DATALAD_END\n" \ "$name" "$name" `git annex info`
        || printf "DATALAD_HANDLE_REPO_%s: annex_init_error DATALAD_END\n" "$name"
    cd "$curdir"
done
