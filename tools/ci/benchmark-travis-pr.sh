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

pip install asv
asv machine --yes
pip install -e .

configure_asv
git tag '__bench_target__'
git rev-parse HEAD __bench_target__
asv run -E existing --set-commit-hash $(git rev-parse __bench_target__)

git reset --hard
git checkout origin/master
git rev-parse HEAD __bench_target__
pip install -e .

configure_asv
asv run -E existing --set-commit-hash $(git rev-parse origin/master)

asv compare origin/master __bench_target__
