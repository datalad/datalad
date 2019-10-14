#!/bin/bash

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
    asv run -E existing --set-commit-hash $(git rev-parse HEAD)
}

pip install asv
asv machine --yes

git update-ref refs/bm/pr HEAD
git update-ref refs/bm/merge-target $(git for-each-ref --count=1 --sort=-creatordate --format='%(objectname)' refs/tags/0.11*)

run_asv

git checkout --force refs/bm/merge-target
run_asv

asv compare refs/bm/merge-target refs/bm/pr
