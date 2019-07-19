#!/bin/bash

set -eu

pip install asv
asv machine --yes
pip install -e .

sed -i -e 's,"branches,//branches,g' -e 's,"pythons,//pythons,g' \
    -e 's,.asv/,travisasv/,g' asv.conf.json
git tag '__bench_target__'
git rev-parse HEAD __bench_target__
asv run -E existing --set-commit-hash $(git rev-parse __bench_target__)

git reset --hard
git checkout origin/master
git rev-parse HEAD __bench_target__
pip install -e .

sed -i -e 's,"branches,//branches,g' -e 's,"pythons,//pythons,g' \
    -e 's,.asv/,travisasv/,g' asv.conf.json
asv run -E existing --set-commit-hash $(git rev-parse origin/master)

asv compare origin/master __bench_target__
