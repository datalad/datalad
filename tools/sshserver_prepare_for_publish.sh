#!/bin/sh
#
# This script is intended to be execute on a server and prepares a simple
# directory structure with repositories for a collection an its handles.
# It initializes them with git and (if available) with git-annex. It returns
# a number of useful status messages on the target via stdout.
#
# Usage: ./sshserver_prepare_for_publish /tmp/example democol ds1 ds2
#

set -e
set -u

# XXX think about different modes to tune accessibility of the published
# repos
rootpath=$1
shift;
colreponame=$1
shift;

git_init_options=""
git_annex_init_options=""

printf "## start server capabilities ####\n"
printf "DATALAD_GIT_VERSION: $(git --version) DATALAD_END\n"
printf "DATALAD_GIT_ANNEX_VERSION: $(git annex version) DATALAD_END\n"
printf "## end server capabilities ####\n"


mkdir -p "$rootpath"
cd "$rootpath"
[ -d "$colreponame" ] && printf "error: target exists\n" && exit 1
mkdir -p "$colreponame"
git -C "$colreponame" init $git_init_options
printf "DATALAD_COLLECTION_REPO_$colreponame: init\n"

for name in "$@"; do
	[ -d "$name" ] && printf "error: target exists\n" && exit 1
	mkdir -p "$name"
	git -C "$name" init $git_init_options
	printf "DATALAD_HANDLE_REPO_$name: init DATALAD_END\n"
	curdir=${PWD}
	cd "$name"
	git annex init $git_annex_init_options \
		&& printf "DATALAD_HANDLE_REPO_$name: annex_init DATALAD_END\nDATALAD_HANDLE_REPO_INFO_$name: $(git annex info) DATALAD_END\n" \
		|| printf "DATALAD_HANDLE_REPO_$name: annex_init_error DATALAD_END\n"
	cd "${curdir}"
done
