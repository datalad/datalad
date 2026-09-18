#!/bin/bash
#
# Compare git-annex build flavors (standalone bundle, conda-forge, PyPI wheel,
# a static build, ...) on the cost they add to datalad's test battery.
#
# The point of comparison is not git-annex itself -- all flavors ship the same
# Haskell binary for a given version -- but what wraps it.  The upstream
# "standalone" bundle (NeuroDebian's git-annex-standalone deb, conda-forge's
# nodep_* build, datalad-installer's datalad/packages method) reaches the
# binary through `git-annex` (sh) -> `runshell` (sh) -> `bin/git-annex` (sh)
# -> a bundled ld.so, and prepends its own bin/ to PATH so git-annex's own
# `git` calls take another hop.  datalad's tests spawn git-annex ~20k times
# per full run, so that per-spawn cost is not noise.
#
# Usage:
#
#   # fetch the publicly available flavors of one version
#   tools/testing/bench-git-annex-flavors.sh fetch 10.20260316 /tmp/ga
#
#   # benchmark them (plus anything else, e.g. an unpacked static build)
#   tools/testing/bench-git-annex-flavors.sh run \
#       pypi=/tmp/ga/pypi/bin \
#       conda=/tmp/ga/conda/bin \
#       standalone=/tmp/ga/standalone/usr/bin \
#       static=/tmp/ga/static
#
# Each NAME=BINDIR is a directory that gets prepended to PATH; it must contain
# a `git-annex` executable.  Environment knobs for `run`:
#
#   SUBSET   test paths to run   (default: datalad/core + test_annexrepo.py)
#   NPROC    pytest-xdist workers (default: 2, matching .github/workflows/test.yml)
#   STARTUP_REPS  repetitions of the startup micro-benchmark (default: 40)
#
# Note that this measures wall time of a *real* test run, so it wants an
# otherwise idle machine; run-to-run spread of ~5-10% is normal.

set -eu

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

die () { echo "$SCRIPT_NAME: $*" >&2; exit 1; }

usage () {
    sed -n '3,40p' "$0" | sed -e 's/^#//' -e 's/^ //'
    exit "${1:-0}"
}

# --- fetch -----------------------------------------------------------------

fetch () {
    local version="$1" dest="$2"
    mkdir -p "$dest"
    dest="$(cd "$dest" && pwd)"

    echo "### PyPI wheel (github.com/psychoinformatics-de/git-annex-wheel)"
    rm -rf "${dest:?}/pypi"
    python3 -m venv "$dest/pypi"
    # `==$version.*` catches the post-releases the wheel repo publishes, e.g.
    # 10.20260901.post1 where upstream's release is plain 10.20260901.
    "$dest/pypi/bin/pip" install --quiet "git-annex==$version" 2>/dev/null \
        || "$dest/pypi/bin/pip" install --quiet "git-annex==$version.*" \
        || echo "  !! no PyPI wheel for $version (oldest published is 10.20250520b7)"

    echo "### conda-forge nodep build"
    rm -rf "${dest:?}/conda"
    mkdir -p "$dest/conda"
    local conda_pkg="git-annex-$version-nodep_h1234567_0.conda"
    if curl -fsSL -o "$dest/$conda_pkg" \
            "https://conda.anaconda.org/conda-forge/linux-64/$conda_pkg"; then
        ( cd "$dest/conda" && unzip -q -o "$dest/$conda_pkg" \
          && python3 -c '
import glob, tarfile
import zstandard  # pip install zstandard
for f in glob.glob("pkg-*.tar.zst"):
    with open(f, "rb") as fp:
        with zstandard.ZstdDecompressor().stream_reader(fp) as r:
            tarfile.open(fileobj=r, mode="r|").extractall(".")
' && rm -f ./*.tar.zst metadata.json ) \
            || echo "  !! could not unpack $conda_pkg (needs unzip and 'pip install zstandard')" 
    else
        echo "  !! no conda-forge nodep package for $version"
    fi

    echo "### NeuroDebian standalone deb (github.com/datalad/git-annex releases)"
    rm -rf "${dest:?}/standalone"
    mkdir -p "$dest/standalone"
    local deb="git-annex-standalone_$version-1.ndall+1_amd64.deb"
    if curl -fsSL -o "$dest/$deb" \
            "https://github.com/datalad/git-annex/releases/download/$version/${deb//+/%2B}"; then
        ( cd "$dest/standalone" && ar x "$dest/$deb" && tar xf data.tar.* \
          && rm -f data.tar.* control.tar.* debian-binary ) \
            || echo "  !! could not unpack $deb (needs ar and tar)" 
    else
        echo "  !! no standalone deb release for $version"
    fi

    echo
    echo "Flavors fetched into $dest; benchmark them with:"
    echo
    echo "  $0 run \\"
    [ -x "$dest/pypi/bin/git-annex" ]        && echo "      pypi=$dest/pypi/bin \\"
    [ -x "$dest/conda/bin/git-annex" ]       && echo "      conda=$dest/conda/bin \\"
    [ -x "$dest/standalone/usr/bin/git-annex" ] && echo "      standalone=$dest/standalone/usr/bin \\"
    echo "      # static=/path/to/unpacked/static/build"
}

# --- benchmark -------------------------------------------------------------

# Median of N `git-annex version` invocations, in milliseconds.
startup_ms () {
    "$PYTHON" -c '
import statistics, subprocess, sys, time
reps = int(sys.argv[1])
def once():
    t0 = time.perf_counter()
    subprocess.run(["git-annex", "version"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return time.perf_counter() - t0
for _ in range(3):      # warm the page cache
    once()
print("%.1f" % (statistics.median(once() for _ in range(reps)) * 1000))
' "$1"
}

run_flavor () {
    local name="$1" bindir="$2" subset="$3" nproc="$4" startup_reps="$5"
    local home wd shim prog started ended

    home="$(mktemp -d -t "bench-home-$name-XXXXXX")"
    wd="$(mktemp -d -t "bench-wd-$name-XXXXXX")"

    # Put only git-annex's own executables on PATH, not the whole $bindir:
    # a PyPI flavor's $bindir is a virtualenv's bin/, and letting its python3
    # shadow the one running the tests is not part of what we are measuring.
    shim="$(mktemp -d -t "bench-shim-$name-XXXXXX")"
    for prog in git-annex git-annex-shell git-remote-annex \
                git-remote-tor-annex git-remote-p2p-annex; do
        [ -e "$bindir/$prog" ] && ln -s "$bindir/$prog" "$shim/$prog"
    done

    # Everything below runs in a subshell so the exported environment does not
    # leak into the next flavor.
    (
        export HOME="$home"
        export PATH="$shim:$PATH"
        # tests need a git identity, and the fresh $HOME has none
        git config --global user.email "bench@example.com"
        git config --global user.name "Bench"
        # keep the comparison about git-annex, not about sshd or the network
        export DATALAD_TESTS_SSH=0
        export DATALAD_TESTS_NONETWORK=1
        export DATALAD_LOG_LEVEL=ERROR

        echo "### $name -- $(git-annex version | head -1)"
        echo "    startup (median of $startup_reps x 'git-annex version'): $(startup_ms "$startup_reps") ms"

        started="$(date +%s)"
        # shellcheck disable=SC2086  # $subset is a deliberate list of paths
        ( cd "$wd" && "$PYTHON" -m pytest -c "$REPO_ROOT/tox.ini" \
              -q -p no:cacheprovider -n "$nproc" \
              -m "not (integration or usecase or slow or network or turtle)" \
              --report-log="$wd/report.jsonl" \
              $(for m in $subset; do echo "$REPO_ROOT/$m"; done) ) \
            > "$wd/pytest.txt" 2>&1 || true
        ended="$(date +%s)"

        echo "    tests: $((ended - started)) s -- $(tail -1 "$wd/pytest.txt")"
        [ -s "$wd/report.jsonl" ] && "$PYTHON" -c '
import collections, json, statistics, sys
dur = collections.defaultdict(float)
for line in open(sys.argv[1]):
    try:
        d = json.loads(line)
    except ValueError:
        continue
    if d.get("$report_type") == "TestReport":
        dur[d["nodeid"]] += d.get("duration", 0.0)
if dur:
    print("    sum of test durations: %.0f s, median test: %.2f s"
          % (sum(dur.values()), statistics.median(dur.values())))
' "$wd/report.jsonl" || true
    )

    rm -rf "$home" "$wd" "$shim"
}

run () {
    [ $# -gt 0 ] || usage 1
    local subset="${SUBSET:-datalad/core datalad/support/tests/test_annexrepo.py}"
    local PYTHON
    local nproc="${NPROC:-2}"
    local startup_reps="${STARTUP_REPS:-40}"
    local spec name bindir

    # Resolved before any flavor's bin/ goes on PATH, so a virtualenv-based
    # flavor cannot shadow the interpreter that runs the tests.
    PYTHON="${PYTHON:-$(command -v python3)}"
    export PYTHON
    "$PYTHON" -c 'import datalad, pytest, xdist' 2>/dev/null \
        || die "PYTHON=$PYTHON has no datalad[devel]; set PYTHON= to one that does"

    echo "subset : $subset"
    echo "workers: -n $nproc"
    echo
    for spec in "$@"; do
        case "$spec" in
            *=*) ;;
            *) die "expected NAME=BINDIR, got '$spec'" ;;
        esac
        name="${spec%%=*}"
        bindir="${spec#*=}"
        [ -x "$bindir/git-annex" ] || die "$bindir/git-annex is not executable"
        run_flavor "$name" "$bindir" "$subset" "$nproc" "$startup_reps"
        echo
    done
}

# --- main ------------------------------------------------------------------

case "${1:-}" in
    fetch)
        shift
        [ $# -eq 2 ] || usage 1
        fetch "$1" "$2"
        ;;
    run)
        shift
        run "$@"
        ;;
    -h|--help|help|"")
        usage
        ;;
    *)
        die "unknown command '$1' (try --help)"
        ;;
esac
