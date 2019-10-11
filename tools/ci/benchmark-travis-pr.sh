#!/bin/bash

# could be "setup", "run" or "compare" or empty (runs all)
action="$1"

set -eu

if [ "$TRAVIS_PULL_REQUEST" = "false" ]
then
    echo "I: skipping benchmarks for non-PR branch"
    exit 0
fi

configure_asv () {
    cat << EOF > asv.conf.json
{
    "version": 1,
    "repo": ".",
    "branches": ["HEAD"],
    "environment_type": "virtualenv",
}
EOF
}

run_asv () {
    pip install -e .
    git show --no-patch --format="%H (%s)"
    configure_asv
    asv run -E existing --set-commit-hash "$(git rev-parse HEAD)"
}

#
# High level actions
#

setup () {
    pip install asv
    asv machine --yes
}

run () {
    git update-ref refs/bm/pr HEAD
    # We know this is a PR run. The branch is a GitHub refs/pull/*/merge ref, so
    # the current target that this PR will be merged into is HEAD^1.
    git update-ref refs/bm/merge-target HEAD^1

    run_asv

    git checkout --force refs/bm/merge-target
    run_asv
}

compare () {
    asv compare refs/bm/merge-target refs/bm/pr
}

case "$action" in
    '') setup && run && compare;;
    *) eval "$action";;
esac