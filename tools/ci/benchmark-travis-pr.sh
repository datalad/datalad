#!/bin/bash
#
# Benchmark a PR (HEAD, a GitHub refs/pull/*/merge commit) against its merge
# target (HEAD^1) with asv.  Results are recorded under refs/bm/pr and
# refs/bm/merge-target, so they can be compared afterwards with
#
#   asv compare refs/bm/merge-target refs/bm/pr
#
# The benchmark suite of the PR is used for both runs, so that benchmarks
# added or modified by the PR get results for the merge target as well, and
# both sides run the same benchmark code.  Afterwards the PR is checked out
# again, with asv.conf.json pointing to the results.  Anything noteworthy
# about the run is written to benchmark-notes.txt, one note per line.
#
# Any arguments are passed to `asv run`, e.g. `-b support.path` to run only
# a subset of the benchmarks.

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
    "benchmark_dir": "$1",
}
EOF
}

# Install the checked out code and point asv at the benchmark suite in $1
prepare_asv () {
    pip install -e .
    git show --no-patch --format="%H (%s)"
    configure_asv "$1"
}

# Exit code of `asv run`: 1 if asv itself failed (e.g. the benchmark suite
# could not be imported), 2 if some benchmarks failed (or if the arguments
# are invalid).  Failed benchmarks are recorded as such and get reported by
# `asv compare`.
run_asv () {
    asv run -E existing --show-stderr --set-commit-hash "$(git rev-parse HEAD)" "$@"
}

pip install asv
asv machine --yes

git update-ref refs/bm/pr HEAD
# We know this is a PR run. The branch is a GitHub refs/pull/*/merge ref, so
# the current target that this PR will be merged into is HEAD^1.
git update-ref refs/bm/merge-target HEAD^1

notes=benchmark-notes.txt
rm -f "$notes"

# Keep a copy of the PR's benchmarks, they are gone after checking out the
# merge target.  Keep the directory name as well: asv imports the suite as a
# package of that name.
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
pr_benchmarks="$tmpdir/benchmarks"
cp -a benchmarks "$pr_benchmarks"

prepare_asv "$pr_benchmarks"
rc=0
run_asv "$@" || rc=$?
case "$rc" in
    0) ;;
    2) echo "W: some benchmarks failed for the PR";;
    *) exit "$rc";;
esac
# `asv compare` takes the units from benchmarks.json, which every `asv run`
# rewrites.  Keep the one for the PR's benchmarks, in case of the fallback
# below.
cp results/benchmarks.json "$tmpdir/"

git checkout --force refs/bm/merge-target
prepare_asv "$pr_benchmarks"
rc=0
run_asv "$@" || rc=$?
case "$rc" in
    0) ;;
    2) echo "W: some benchmarks failed for the merge target," \
            "e.g. since they use functionality introduced by the PR";;
    *)
        note="Benchmarks of the PR could not be imported for the merge target, so those it adds or modifies are not compared.  Import new functionality within benchmarks, not at module level."
        echo "$note" >> "$notes"
        echo "::warning::$note"
        configure_asv benchmarks
        rc=0
        run_asv "$@" || rc=$?
        case "$rc" in
            0|2) ;;
            *) exit "$rc";;
        esac
        ;;
esac

# Leave the PR checked out, with asv configured to compare the results
git checkout --force refs/bm/pr
configure_asv benchmarks
# Merge both, so that also benchmarks only in the fallback run have units
python -c '
import json, sys
merged = json.load(open(sys.argv[1]))
merged.update(json.load(open(sys.argv[2])))
json.dump(merged, open(sys.argv[1], "w"))
' results/benchmarks.json "$tmpdir/benchmarks.json"

asv compare refs/bm/merge-target refs/bm/pr
