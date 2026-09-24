# Speeding up the DataLad test battery

Status: **proposal / measurements only** — nothing in CI or in the tests is
changed by this document.  It targets the CI as it now stands on `maint`,
i.e. after [PR #7933](https://github.com/datalad/datalad/pull/7933) merged the
Windows/macOS jobs into the single `test.yml` + `tools/ci/test-jobs.yml`
specification and retired AppVeyor.

All numbers below were measured, either from the GitHub Actions API for a real
nightly run, or locally in a 4-vCPU / 16 GB Linux container on the #7933 tree.
Where something could not be measured it says so.

---

## 1. TL;DR

The test battery is not slow because of a handful of slow tests.  It is slow
because of a large number of *uniformly* medium-cost tests, each of which
spawns a lot of `git` and `git-annex` processes — plus a shockingly expensive
CI setup step.  Measured on `datalad/core` + `test_annexrepo.py`
(263 collected, 278 including parametrization, non-slow selection):

| measure                                                       | value                   |
| ------------------------------------------------------------- | ----------------------- |
| sum of test durations                                         | 924 s                   |
| median test                                                   | 2.4 s                   |
| tests ≥ 10 s                                                  | 10 (14 % of the total)  |
| tests in the 2–10 s band                                      | 146 (74 % of the total) |
| `git-annex` process spawns, `test_create.py` alone (33 tests) | 561                     |
| `git` process spawns, same module                             | 2405                    |

So ~17 `git-annex` and ~73 `git` process spawns *per test*.  Anything that
makes one process spawn cheaper is multiplied by ~20 000 `git-annex` and
~95 000 `git` spawns per full run.

Three findings, in order of payoff:

1. **The git-annex build flavor is worth 2.3–3.9× of real test wall time.**
   The "standalone" builds (NeuroDebian `.deb`, conda-forge `nodep`) wrap the
   binary in two shell scripts plus a custom `ld.so`
   invocation, and shadow the system `git` with a bundled one behind another
   shim.  The PyPI wheel (`pip install git-annex`, maintained by Michael
   Hanke) is a plain dynamically linked binary.  Same git-annex version,
   same 263 tests: **10 min 15 s (conda) / 7 min 45 s (standalone deb) →
   3 min 19 s**.  A statically linked build (kyleam's) measures the same as
   the wheel exec'd directly, so it is the *wrapper*, not the linking, that
   costs — see §3.3.
2. **`Install git-annex` costs 196 job-minutes per nightly run** — 24 % of all
   CI minutes — almost entirely because the default
   `_DL_ANNEX_INSTALL_SCENARIO` pins a 2023-vintage miniconda
   (`miniconda=py37_23.1.0-1`).  Two matrix entries already prove the fix:
   the same pinned git-annex with a current miniconda takes 0.7 min instead of
   9–15 min, and `-m datalad/packages` takes 12 s.
3. **`@turtle` is almost empty and `@slow` is not where the time is.**  Exactly
   *one* `@turtle` test is collected (`test_gitannex_ssh`); the other `@turtle`
   is on a `_`-prefixed function that pytest never collects.  Meanwhile
   several *unmarked* tests take 8–21 s.  The slow/not-slow split costs more in
   coverage gaps (PRs never run the 75 `@slow` tests) than it saves in time.

The proposals, in short — as two pull requests (§7):

|        |                                                                                |              |
| ------ | ------------------------------------------------------------------------------ | -----------: |
| **A1** | install git-annex from PyPI by default, on all three platforms                 | ~180 job-min |
| **A2** | retire miniconda; standalone + conda coverage on cron only                     |            — |
| **A3** | one selection instead of the slow/not-slow split; Python sweep = base + newest | ~112 job-min |
| **A4** | scope the six "scenario smoke" entries like the NFS ones already are           |  ~78 job-min |
| **A5** | coverage for PRs under review only — off on cron and on drafts                 | ~160 job-min |
| **A6** | `-n 2` → an explicit worker count (1.58× measured at `-n 4`)                   |      per job |
| **A7** | stop provisioning NeuroDebian where APT is unused; pip cache / `uv`            |        small |
| **A8** | drop `DATALAD_TESTS_SETUP_TESTREPOS`, duplicate `--doctest-modules`            |        small |
| **B1** | `test_files_split`: monkeypatch `CMD_MAX_ARG` instead of 10 000 files          |  124 s → 3 s |
| **B2** | `git-annex testremote --fast --size=1KiB`                                      |   60 s → 3 s |
| **B3** | delete the uncollected `@turtle` in `test_s3.py`                               |            — |
| ~~B4~~ | ~~remove `utils_testrepos.py` + its config option~~ — **not doable**, see below |            — |
| **B5** | fixture reuse by tarball for one `@slow` cluster                               |  41 s → 35 s |
| later  | a caching dataset fixture keyed on the tree spec (P11)                         |            — |

Measured and **rejected**: TMPDIR on tmpfs (within noise), `eatmydata` /
`core.fsync=none` / `gc.auto=0` (this suite is not fsync-bound),
`--dist worksteal` (no effect at the scale tested).

---

## 2. Where the CI minutes actually go

Nightly `Test` run
[35213632039](https://github.com/datalad/datalad/actions/runs/35213632039)
(2026-09-17, `maint`, all 21 matrix entries incl. cron-only), from the Actions
API:

| step                        |       total | median/job |
| --------------------------- | ----------: | ---------: |
| **Run tests**               | **579 min** |   27.1 min |
| **Install git-annex**       | **196 min** |   12.7 min |
| Provision OS / APT deps     |      21 min |    1.0 min |
| Install Python dependencies |       7 min |    0.3 min |
| everything else             |     ~11 min |          — |
| **total job time**          | **814 min** |            |
| wall-clock                  |      85 min |            |

### 2.1 `Install git-annex`: 196 minutes for one binary

Per-job cost, grouped by the scenario in `tools/ci/test-jobs.yml`:

| `_DL_ANNEX_INSTALL_SCENARIO`                                             | jobs |     install time |
| ------------------------------------------------------------------------ | ---: | ---------------: |
| `miniconda=py37_23.1.0-1 … git-annex=10.20230126 -m conda` **(default)** |   14 | **9.2–15.3 min** |
| `miniconda --channel conda-forge … git-annex -m conda`                   |    4 |      0.9–1.0 min |
| `miniconda=py310_25.9.1-1 … git-annex=10.20230126 -m conda`              |    1 |      **0.7 min** |
| `venv git-annex -m datalad/packages`                                     |    2 |      **0.2 min** |

The middle two rows are the important ones: the *same pinned minimum
git-annex* (`10.20230126`) installs in 0.7 min with a 2025 miniconda and in
14 min with the `py37_23.1.0-1` one.  The old pin carries an ancient `conda`
whose classic solver grinds for ~13 minutes.  Its justification in `test.yml`
is a stale comment:

```yaml
# How/which git-annex we install.  conda's build would be the fastest,
# but it must not get ahead in PATH to not shadow travis' python
_DL_ANNEX_INSTALL_SCENARIO: "miniconda=py37_23.1.0-1 --python-match minor --batch git-annex=10.20230126 -m conda"
```

Travis has been gone for years, and `actions/setup-python` puts its Python
ahead of conda's anyway.

Worth separating the two jobs miniconda was doing here.  As a **Python-version
provider** it is redundant: `actions/setup-python` does that in seconds, and
does it on all three platforms.  As a way to **install git-annex from a conda
package** it is still meaningful coverage — but `miniconda` is by far the
slowest way in, and datalad-installer v1.2.x deprecates that component
outright in favour of `miniforge` ("to avoid Anaconda Terms of Service
issues").

Measured on the same machine, each of these ending with a usable `git-annex`
from conda-forge:

| how                                                                |                                            time |
| ------------------------------------------------------------------ | ----------------------------------------------: |
| `pixi global install git-annex`                                    |                                         **3 s** |
| `micromamba create -p … -c conda-forge git-annex`                  |                                        **12 s** |
| `Miniconda3-py37_23.1.0-1` + `conda install git-annex=10.20230126` | **266 s** (4 s bootstrap + 261 s solve/install) |

That 261 s is the same classic solver that takes 9–15 min on the runners, where
it also has to fetch everything cold.  `micromamba` is a single static binary
with no bootstrap installer; `pixi` additionally exposes the shims
(`git-annex`, `git-annex-shell`, `git-remote-annex`, …) in one bin directory,
which is exactly what the `/usr/local/bin` requirement in §7 A1 wants.  One
layer up, `uv` is the same argument for the Python dependencies.

One caveat worth knowing before trusting a conda pin: conda-forge's `nodep`
packages are repackaged upstream standalone tarballs, and those lag their own
release by a few commits.  The `nodep` builds labelled `git-annex 10.20230126`
ship a binary reporting `10.20221213-ge5b6b7b5e`, and the one labelled
10.20260316 reports 10.20260213.  datalad already compensates —
`datalad/support/external_versions.py` carries a hard-coded special case
rewriting exactly `10.20221213-ge5b6b7b5e` to `10.20230126`, with a comment
about the standalone-build dance — so nothing is broken by it.

Which build you get depends on the resolver, and that cuts in our favour here:
`conda install git-annex=10.20230126` under the old miniconda picked
`nodep_h1234567_1` (the repackaged bundle, reporting 10.20221213), while `pixi
global install "git-annex==10.20230126"` resolved `alldep_h97b9560_101` — the
*dynamically linked* conda build, whose binary correctly reports
`10.20230126-g36f5557`.  So the minimum-version entry via pixi is both better
versioned and unwrapped.  `alldep` exists only up to 10.20230626, so a plain
`pixi` (newest) still lands on a `nodep` bundle — which is exactly the
packaging the other cron entry is there to cover.

### 2.2 Three matrix entries are exact duplicates

`test.yml` builds the marker expression as

```sh
-m "${PYTEST_SELECTION:+$PYTEST_SELECTION_OP($PYTEST_SELECTION) and }not(turtle)"
```

`${VAR:+…}` expands to nothing when `VAR` is empty, so with
`PYTEST_SELECTION: ""` the value of `PYTEST_SELECTION_OP` has **no effect** —
both `"not"` and `""` produce `-m not(turtle)`.  The 3.12, 3.13 and 3.14
entries come in pairs that differ *only* in `PYTEST_SELECTION_OP`, i.e. each
pair runs the identical test set twice:

| pair    | measured `Run tests` |
| ------- | -------------------- |
| 3.12 ×2 | 44.1 + 42.2 min      |
| 3.13 ×2 | 41.3 + 42.6 min      |
| 3.14 ×2 | 28.7 + 24.8 min      |

That is ~112 job-minutes per run of duplicated work.  (The 3.10 pair with
`DATALAD_SSH_MULTIPLEX__CONNECTIONS: "0"` is *not* affected — it leaves
`PYTEST_SELECTION` at the non-empty default, so `OP=""` / `OP="not "` really
do split the suite in halves.)

The intention was presumably the slow/not-slow split that the 3.10 pair still
implements.  Rather than repair it, the cheaper move is to drop the split
altogether (§7 A3): once a full run is ~2× cheaper, one job per scenario
running everything-but-turtle costs about what today's "not slow" half costs,
saves a second job's worth of setup, and stops PRs skipping 101 tests.

### 2.3 Wall-clock is set by a concurrency cap of 20, not by the matrix size

In the same nightly run, **20 jobs started at t+0.1 min and the remaining two
waited 30.9 min** before a slot freed up:

```
 started   done  queued  job
     0.1   43.6     0.0  test (3.10)
     0.1   48.5     0.0  test (3.10, true, not)
     ...   (18 more at t+0.1)
    30.9   84.8    30.9  test (3.10, not, ru_RU.UTF-8)
    31.0   71.3    30.9  test (3.10, /var/tmp/sym link, -, INFO, ...)
```

So the 85 min wall = 31 min of queueing + a 54 min job.  Consequences:

* **Adding shards past ~20 concurrent jobs buys nothing** — they just queue.
  Sharding helps only while the total job count stays under the cap, which is
  an argument for *removing* jobs (§2.2) before splitting any.
* PR runs (7 cron-only entries filtered out → 14 test jobs, ~548 job-min)
  stay under the cap, so a PR's wall time is simply its longest job: **~54 min**
  today.  That is the number a contributor waits for.

### 2.4 Three smaller ones

* Every Linux job sets up the NeuroDebian APT repository
  (`tools/ci/test-env-linux.sh`), but **no** matrix entry installs git-annex
  from APT/NeuroDebian any more.  It is pure setup cost on 20 jobs.
* `test.yml` exports `DATALAD_TESTS_SETUP_TESTREPOS=1`.  The config key it maps
  to (`datalad.tests.setup.testrepos`) is still *declared* in
  `datalad/interface/common_cfg.py` and has zero readers **in this
  repository**, as does `datalad/tests/utils_testrepos.py` beyond its own
  test file.  Only the export goes (§7 A8): the declaration and the module
  itself are load-bearing for extensions — see B4, where removing them was
  tried and reverted.
* `--doctest-modules` is passed **twice** in the `Run tests` step (once from
  `PYTEST_OPTS`, once on the command line).

---

## 3. The git-annex builds

### 3.1 What the flavors actually are

**NeuroDebian `git-annex-standalone` deb** — 199 MB.  The upstream standalone
bundle: `git-annex` (sh) → `runshell` (sh, 274 lines) → `bin/git-annex` (sh) →
`exe/git-annex` (a bundled `ld.so`) → `shimmed/git-annex/git-annex`.  Ships its
own `git`, `libc`, locales and `gconv`, and puts them **first** in `PATH`.

**conda-forge `git-annex … nodep_*`** — 176 MB.  The *same* standalone bundle,
repackaged — but built with `GIT_ANNEX_PACKAGE_INSTALL=` **empty**, so
`runshell` additionally scans and creates `~/.cache/git-annex/locales/*` and
writes `~/.ssh/git-annex-shell` shims on *every* invocation.

**conda-forge `git-annex … alldep_*`** — 12 MB.  A normal dynamically linked
conda build, and the only conda flavor that is not a bundle — **but the newest
`alldep` build is 10.20230626**; every release since is `nodep`-only.

**PyPI `git-annex` wheel** (maintainer: Michael Hanke) — 91 MB.  An
auditwheel-repaired build: one 87 MB binary, 4 vendored `.so`s and `magic.mgc`.
A `git_annex:cli` console script `os.execv`s the binary.

**`dl.kyleam.com/git-annex/`** — 116 MB.  One statically linked Linux/amd64
ELF, with `git-annex-shell`, `git-remote-annex` and `git-remote-tor-annex` as
symlinks to it.  Build scripts at `git.kyleam.com/static-annex`; a good number
of older releases are kept alongside the recent ones, though not every one —
10.20260316, the version the rest of this document uses, is not among them.

Note that `-m datalad/packages` (used by the 3.14 entries, and on Windows since
#7933) is *also* the standalone bundle on Linux: datalad-installer downloads
`git-annex-standalone_<v>-1~ndall+1_amd64.deb`.  And `-m conda` on Linux now
always resolves to a `nodep` build, i.e. also standalone.  **Every Linux job in
the current matrix runs a standalone bundle.**

### 3.2 Micro-benchmark — process startup

Same version (10.20260316) everywhere; 40 repetitions, median:

| flavor                         | `git-annex version` |
| ------------------------------ | ------------------: |
| PyPI wheel, direct exec        |          **6.2 ms** |
| PyPI wheel, via console script |             24.1 ms |
| NeuroDebian standalone deb     |             34.8 ms |
| conda-forge `nodep`            |             48.2 ms |

Decomposing the standalone overhead (`git --version` through the bundle):

|                                             |          |
| ------------------------------------------- | -------: |
| system `/usr/bin/git --version`             |  1.77 ms |
| bundled git via the bundle's `bin/git` shim |  3.11 ms |
| the same via the bundled `ld.so` directly   |  1.89 ms |
| `runshell git --version` (the full wrapper) | 15.80 ms |

Two costs compound: `runshell` itself (~14 ms of shell, `dirname`/`pwd`/`cat`
×3/`grep`/`uname` forks, plus a `~/.cache/git-annex/locales` scan in the conda
variant), and the fact that **every `git` that git-annex spawns also goes
through a shim** because the bundle prepends its own `bin/` to `PATH`.

An annex workload (init + 30 × `git-annex add` + `whereis`/`find`/`info`/`fsck`,
median of 3):

| flavor                     |            |
| -------------------------- | ---------: |
| PyPI wheel, direct exec    | **2.99 s** |
| PyPI wheel, console script |     3.72 s |
| conda-forge `nodep`        |     6.50 s |
| NeuroDebian standalone deb |     6.96 s |

### 3.3 Macro-benchmark — the actual test suite

Identical tree, identical selection
(`not (integration or usecase or slow or network or turtle)`), `-n 2`,
`DATALAD_TESTS_SSH=0`, no coverage.  Only `PATH`/`HOME` differ.

**`datalad/core/local/tests/test_create.py`** (33 tests):

| flavor                     |       wall |
| -------------------------- | ---------: |
| PyPI wheel, direct exec    | **22.2 s** |
| PyPI wheel, console script |     27.2 s |
| NeuroDebian standalone deb |     59.1 s |
| conda-forge `nodep`        |     77.6 s |

**`datalad/core` + `datalad/support/tests/test_annexrepo.py`** (263 tests):

| flavor                     |  wall (`-n 2`) | sum of test durations | median test | × slowest |
| -------------------------- | -------------: | --------------------: | ----------: | --------: |
| PyPI wheel, direct exec    | **2 min 37 s** |                 312 s |      0.89 s |      1.00 |
| PyPI wheel, console script | **3 min 19 s** |                 394 s |      1.11 s |      1.26 |
| NeuroDebian standalone deb |     7 min 45 s |                 924 s |      2.37 s |      2.94 |
| conda-forge `nodep`        |    10 min 15 s |                1225 s |      3.19 s |      3.90 |

(One pre-existing failure, `test_clone_dataset_from_just_source`, in all four —
it wants network, which these runs did not have.  Same test set, same failure,
so the comparison is unaffected.)

Note what the middle columns do to the `@slow` bookkeeping: the median test
goes from 2.4 s to 1.1 s, and the 8–21 s unmarked tests of §4.3 land back under
the documented 10 s threshold.  The threshold was never wrong; the build was.

Caveat: the conda-forge package *labelled* 10.20260316 reports
`git-annex version: 10.20260213` — conda-forge's `nodep` recipe lags the
tarball it repackages.  A 5-week version difference cannot explain a 3.5×
gap, but the conda row is not a perfectly matched pair.

**Same subset at 10.20260901, including a static build** (kyleam's
`git-annex-10.20260901-linux-amd64.tar.gz`: one 120 MB statically linked ELF
with `git-annex-shell`/`git-remote-annex`/`git-remote-tor-annex` as symlinks to
it — no `runshell`, no bundled `ld.so`, no bundled `git`).  All four rows from
one sitting, so the ratios are comparable even though absolute numbers drift
with machine load:

| flavor                     |    startup | wall (`-n 2`) | sum of test durations | median test | × fastest |
| -------------------------- | ---------: | ------------: | --------------------: | ----------: | --------: |
| static (kyleam)            | **5.0 ms** |     **111 s** |                 219 s |      0.60 s |      1.00 |
| PyPI wheel, direct exec    |     6.3 ms |         114 s |                 224 s |      0.59 s |      1.03 |
| PyPI wheel, console script |    19.7 ms |         145 s |                 287 s |      0.77 s |      1.31 |
| NeuroDebian standalone deb |    21.5 ms |         293 s |                 584 s |      1.52 s |      2.64 |

**The static build and the PyPI wheel are the same speed.**  Exec'd directly
they are within 3 % of each other on every column — static linking buys nothing
measurable here.  What the table actually separates is three ways of *reaching*
the same Haskell binary:

* nothing in the way (static, or the wheel's binary exec'd directly): baseline;
* a Python console script that `os.execv`s it: **+27 %** — ~14 ms of interpreter
  startup per spawn, times ~20 000 spawns per full run;
* the standalone bundle's `runshell` chain: **+157 %**.

That also settles the choice between the two wrapper-free options on grounds
other than speed: coverage (the wheel has macOS and Windows builds and every
release since 10.20250605; the static builds are Linux/amd64 and only the most
recent releases), an installer method (`datalad-installer git-annex -m pip` —
its method selector, not `python -m pip`; §7 A1), and `LD_PRELOAD` (works
against the wheel, impossible against a static binary).

### 3.4 Side benefits of leaving the standalone bundle behind

* git-annex would use **the same `git` as datalad** instead of its own bundled
  one — i.e. CI would actually exercise the git version the matrix claims to
  test (`upstream-git` / `minimum-git` entries currently only affect datalad's
  own git calls, not git-annex's).
* `LD_PRELOAD` works again.  `runshell` explicitly `unset LD_PRELOAD`s, which
  makes `eatmydata`-style fsync elimination impossible today (see §6.1).  A
  *static* build (kyleam's) would not support `LD_PRELOAD` either — this is a
  point in favor of the PyPI wheel over a static binary for CI.
* No `~/.ssh/git-annex-shell` / `~/.cache/git-annex/locales` side effects in
  `$HOME` during tests.

### 3.5 What to keep on a standalone build anyway (on cron)

The standalone bundle is what a large fraction of users actually install
(NeuroDebian, `datalad-installer` defaults, conda).  Its `PATH`/`GIT_EXEC_PATH`/
`LOCPATH` behavior has caused real bugs before, so it deserves to stay in the
matrix — but on **one cron job**, not on every PR.  Packaging variants of the
same git-annex are not what a PR usually breaks, and `-m datalad/packages`
installs in 12 s, so that coverage is nearly free where it belongs.

Likewise the **minimum announced version** (`AnnexRepo.GIT_ANNEX_MIN_VERSION`
= `10.20230126`, Debian bookworm's) is not on PyPI at all — PyPI's oldest
git-annex is `10.20250520b7` — so that one job stays on conda-forge, just with
a current miniconda.

---

## 4. Where the *test* time goes, and the `@slow`/`@turtle` review

### 4.1 The marker buckets are tiny

`pytest --collect-only` over `datalad` (1396 tests):

| selection                                                                          | tests |
| ---------------------------------------------------------------------------------- | ----: |
| everything except `turtle`                                                         |  1395 |
| `turtle`                                                                           | **1** |
| `slow`                                                                             |    75 |
| `network`                                                                          |    23 |
| `integration`                                                                      |     7 |
| `usecase`                                                                          |     2 |
| default PR selection (`not (integration or usecase or slow or network or turtle)`) |  1294 |

The PR-gating job therefore runs 1294 of 1396 tests and takes 27 min; the
"everything but turtle" job runs 1395 and takes ~40 min.  The 101 extra tests
cost ~13 min.  **Excluding `@slow` buys ~30 % of one job and costs PRs all
coverage of push/clone/sibling code paths.**

### 4.2 `@turtle`

* `datalad/distributed/tests/test_ria_basics.py::test_gitannex_ssh` — the only
  collected `@turtle`.  It runs `git-annex testremote store` over SSH with
  default options.  `git-annex testremote` accepts `--fast` ("avoid slow
  operations") and `--size` (default **1 MiB**); the test passes neither:

  ```python
  ds.repo._call_annex(['testremote', 'store'], protocol=NoCapture)
  ```

  `['testremote', '--fast', '--size=1KiB', 'store']` should cut this and its
  `@slow` sibling `test_gitannex_local` (41 s) by a large factor while still
  exercising the RIA special remote's protocol surface.
* `datalad/downloaders/tests/test_s3.py::_test_expiring_token` — `@turtle
  @integration`, but the function is `_`-prefixed, so pytest never collects it.
  It waits out a 900 s STS token.  It is dead code with decorative markers:
  either delete it or (if the coverage is wanted) rename it and keep it
  cron-only.

So "partition the slow cases" has already effectively happened for `turtle`;
there is nothing left there to win.

### 4.3 The real distribution

Per-test durations from `--report-log` for `datalad/core` + `test_annexrepo.py`
under the **standalone** build (the flavor CI uses today), 278 test items,
924 s of test time:

```
  median 2.37 s     mean 3.33 s
  >= 0.5 s : 230 tests,  919 s  (99 % of total)
  >=   2 s : 156 tests,  819 s  (89 %)
  >=   5 s :  64 tests,  512 s  (55 %)
  >=  10 s :  10 tests,  133 s  (14 %)
```

Top of the list (none of these carry `@slow`):

```
   21.0 s  test_diff.py::test_path_diff
   15.1 s  test_status.py::test_status
   14.1 s  test_save.py::test_add_recursive
   13.3 s  test_save.py::test_bf1886
   13.3 s  test_run.py::test_run_from_subds_gh3551
   12.2 s  test_save.py::test_save
   12.0 s  test_resulthooks.py::test_basics
   11.1 s  test_save.py::test_save_amend
   10.6 s  test_push.py::test_gh1763
   10.0 s  test_clone.py::test_ephemeral
```

There is no fat tail to amputate.  Every one of these is "create a few
datasets, run a few commands", i.e. the cost *is* the per-process overhead and
the number of `Dataset.create()` calls.

### 4.4 Structural test-level wins

* **`test_files_split` (`@slow  # 313s`, parametrized ×2 → ~10 min).**  It
  materializes 100 × 100 files with 101-character names purely to push a
  command line past `CMD_MAX_ARG` and exercise the chunking in
  `datalad.utils.generate_file_chunks`.  That function reads the module-level
  `datalad.utils.CMD_MAX_ARG` at call time, so the same code path can be
  exercised with ~200 files and a monkeypatched limit, in seconds.  Keep the
  full-size version as `@turtle` for cron if the "real limit" assurance is
  wanted.
* **Build each fixture once, then hand out copies.**  `test_rerun_merges.py`
  has 12 `@slow` tests, each of which calls a `_setup_*` helper that does
  `Dataset(path).create()` + 2–3 `ds.run()` + a merge.  The same pattern
  repeats in `test_update.py` (10 `@slow`), `test_get.py` (8),
  `test_create_sibling.py` (7), `test_push.py` (5).  Building each distinct
  fixture **once per session** and unpacking a fresh copy per test turns
  12 × ~12 s of setup into 1 × 12 s + 12 × milliseconds.  A tarball round-trip
  is the better mechanism — see §5 — and it has to be opt-in: copies share the
  dataset ID and annex UUID, which is fine for local-only tests but not for
  tests that wire two copies together as siblings (§7 B5, P11).
* **Mark what is actually slow.**  Several unmarked tests exceed the
  documented 10 s `@slow` threshold on the build CI uses.  Rather than annotate
  them by hand, drive the split from measured durations (P9) — the workflow
  already uploads `pytest-report.jsonl` artifacts with exactly that data.

---

## 5. Fixture cost: creating a dataset vs unpacking one

In-process, with the PyPI wheel; the fixture is a dataset with three annexed
files in two directories (medians, machine otherwise idle):

| step                                          |           time |
| --------------------------------------------- | -------------: |
| `import datalad.api`                          |         294 ms |
| `Dataset(p).create()`                         |         242 ms |
| `create()` + 3 files + `save()` — one fixture |     **495 ms** |
| `cp -a` of the result                         |          44 ms |
| `shutil.copytree(..., symlinks=True)`         |           6 ms |
| `tar -cf` — minted **once per session**       | 3 ms (180 KiB) |
| `tar -xf` per test                            |       **7 ms** |
| `tarfile.extractall` per test                 |           7 ms |

So a fixture costs ~0.5 s to build and ~7 ms to unpack: **70× cheaper per
test**, and a test that builds a 3–5 dataset hierarchy spends 1.5–2.5 s on
construction before it tests anything.  The 294 ms `import datalad.api` is a
separate, additive cost for every test that shells out to the `datalad` CLI
rather than calling the Python API.

On mechanism: both `cp -a` and `tar -xf` produced *working* copies here — `git
status`, `git-annex whereis` and `git-annex fsck --fast` all succeeded in them,
and both could be `rmtree`'d afterwards.  Two reasons to prefer tar anyway:

* **speed and determinism** — `tar -xf` is 6× faster than `cp -a` (which
  preserves timestamps and xattrs at the cost of many more syscalls), the
  archive is minted once, and `tar` records modes explicitly instead of
  depending on `cp`'s flags being right on BSD/macOS as well as GNU;
* **the permission question is only masked here.**  These runs are as root, so
  git-annex's read-only object files (`0444` in `0555` directories) never block
  anything.  As a normal user — which is how CI runs — a naive copy-and-remove
  does trip over them; datalad's own `datalad.utils.rmtree` exists partly for
  that reason (it chmods files before unlinking, automatically on Windows).
  Unpacking from a tarball into a fresh temp dir sidesteps the whole question.

## 6. Environment and pytest knobs

Same git-annex (PyPI wheel, direct exec), same 91 tests
(`test_create.py` + `test_save.py` + `test_status.py`), one knob at a time.

### 6.1 Environment

| variant                                                     |       wall | vs baseline |
| ----------------------------------------------------------- | ---------: | ----------: |
| `-n 1`, TMPDIR on disk                                      |    115.5 s |       0.54× |
| **`-n 2`, TMPDIR on disk — what CI does today**             | **62.2 s** |   **1.00×** |
| `-n 2`, TMPDIR on `/dev/shm`                                |     57.1 s |       1.09× |
| `-n 2`, disk, `fsync`/`fdatasync`/`sync_file_range` → no-op |     62.8 s |       0.99× |
| `-n 2`, tmpfs + fsync no-op                                 |     56.5 s |       1.10× |
| `-n 4`, TMPDIR on disk                                      |     39.4 s |   **1.58×** |
| `-n 4`, TMPDIR on `/dev/shm`                                |     34.7 s |   **1.79×** |

Two results worth calling out:

* **`-n 2` leaves half of a 4-vCPU runner idle.**  Scaling is 1.86× from
  `-n 1` to `-n 2` and 2.93× to `-n 4` — 73 % parallel efficiency at 4
  workers, because these tests are subprocess-bound, not CPU-bound.  `-n 2` is
  hardcoded in `test.yml`.  Standard GitHub-hosted Linux runners for public
  repositories are 4-vCPU, but that deserves one `nproc` line in the workflow
  rather than an assumption.

  Re-measured at a realistic scale — `datalad/core` + `datalad/support` +
  `datalad/local`, 574 tests — `-n 2` takes **200 s** and `-n 4` **121 s**,
  i.e. **1.65×**, and the two runs ended with *identical* outcomes (564
  passed, 10 failed, 38 skipped, 6 errors; the failures are a local `patool`
  incompatibility and one network test, present at both worker counts).  So
  four workers bought 1.65× without destabilising anything in that subset —
  which is the evidence A6 wants, not a guarantee for the whole suite.
* **fsync is not a bottleneck** — eliding it entirely changes nothing
  (62.8 s vs 62.2 s), so `eatmydata`-style tricks are a dead end here.  Caveat:
  this container's backing store may fsync much more cheaply than an
  Azure-backed runner, so worth one confirmation run in CI before dismissing
  outright.  (Note also that `LD_PRELOAD` only works at all once git-annex is
  *not* a standalone bundle — `runshell` unsets it — and would not work against
  a static build at all.)
* **The tmpfs gain is not established.**  Two runs of the *identical* baseline
  configuration came out 62.2 s and 57.3 s, so the noise floor on this machine
  is ~±8 % — exactly the size of the claimed tmpfs win.  Treat `-n 4` (1.58×)
  and the coverage result below as real; treat tmpfs as unproven and worth a
  cheap CI trial, not a recommendation.

### 6.2 pytest options

| variant                                          |       wall |                  vs plain |
| ------------------------------------------------ | ---------: | ------------------------: |
| plain, `-n 2`                                    |     57.3 s |                     1.00× |
| `--cov=datalad --cov-report=xml`                 | **79.8 s** |                 **+39 %** |
| `--doctest-modules`                              |     61.9 s | +8 % (at the noise floor) |
| both (what CI runs)                              | **82.5 s** |                 **+44 %** |
| `--dist worksteal` instead of the default `load` |     61.6 s |   no effect at this scale |

**Coverage is the expensive one, and CI measures it where it is thrown away.**
`test.yml` passes `--cov=datalad --cov-report=xml` unconditionally, but uploads
only `if: github.event_name != 'schedule'`.  So every nightly cron run pays
~39 % on all 21 jobs for a report nobody consumes — on the measured 579 min of
test time that is roughly **160 job-minutes per nightly run**.  On PR runs all
14 jobs upload, which codecov merges; most of those jobs re-measure the same
lines.

`--dist worksteal` was then re-measured locally at a realistic scale —
`datalad/core` + `datalad/support` + `datalad/local`, 574 tests at `-n 4`:
**121 s with the default `--dist load`, 120 s with `--dist worksteal`**.  A
dead heat, so it is not worth changing; the suite's tail is apparently not
imbalanced enough for work stealing to matter.

### 6.3 git-level durability knobs

Injected the way CI already injects `annex.stalldetection`, i.e. through
`DATALAD_TESTS_GITCONFIG` — `datalad/conftest.py` appends it to the session's
temporary `GIT_CONFIG_GLOBAL`, so it applies to every test repo with no code
change at all:

```yaml
DATALAD_TESTS_GITCONFIG: "\n[core]\n fsync = none\n[gc]\n auto = 0\n"
```

| variant                                   |   wall |
| ----------------------------------------- | -----: |
| control (no extra git config)             | 56.4 s |
| `core.fsync=none`, `gc.auto=0`            | 61.4 s |
| the same plus an empty `init.templateDir` | 60.0 s |

No gain — both variants land within the ±8 % noise floor, and if anything on
the slow side.  Consistent with the `LD_PRELOAD` result above: this suite is
not fsync-bound.  Dead end, recorded so nobody has to try it again.

## 7. Proposal, as two pull requests

The work splits cleanly along the line of what it touches.  **PR A** changes
only `.github/workflows/test.yml` + `tools/ci/`; **PR B** changes only
`datalad/`.  They are independent: PR A makes the suite cheaper to *run*, PR B
makes the suite itself cheaper.  A third, larger piece (the caching dataset
fixture, P11) is better as its own work later.

### PR A — CI tune-ups

#### A1 — Install git-annex from PyPI by default  *(~180 job-min/run)*

Teach the `Install git-annex` step a `pypi` scenario and make it the default:

```yaml
env:
  _DL_ANNEX_INSTALL_SCENARIO: "pypi"      # was: miniconda=py37_23.1.0-1 …
```

```yaml
- name: Install git-annex
  run: |
    if [[ "$_DL_ANNEX_INSTALL_SCENARIO" == pypi* ]]; then
      # "pypi", or "pypi==10.20260901.post1" to pin
      pip install "git-annex${_DL_ANNEX_INSTALL_SCENARIO#pypi}"
      # console scripts must be findable by *non-interactive ssh* sessions
      # (DATALAD_TESTS_SSH=1) and by `sudo -E`, not just by this job's PATH
      scriptdir=$(python -c 'import sysconfig; print(sysconfig.get_path("scripts"))')
      sudo ln -sf "$scriptdir"/git-annex "$scriptdir"/git-annex-shell \
                  "$scriptdir"/git-remote-annex "$scriptdir"/git-remote-tor-annex \
                  /usr/local/bin/
    else
      pip install datalad-installer
      eval datalad-installer --sudo ok -E new.env ${_DL_ANNEX_INSTALL_SCENARIO}
      cat new.env >> ~/.bashrc
    fi
```

This exact step has been run locally under `act` (§8): git-annex 10.20260901
installed in **1.0–2.4 s**, `git-annex-shell` resolved from `/usr/local/bin`,
and `datalad/core/local/tests/test_create.py` passed 33/33.

The `/usr/local/bin` symlinks are not cosmetic: `datalad`'s
`SSHConnection.get_annex_installdir()` resolves git-annex on the far side with
`sh -e -c 'dirname $(readlink -f $(which git-annex-shell))'`, and a
non-interactive `sshd` session gets a minimal `PATH` that contains
`/usr/local/bin` but not `$GITHUB_PATH` additions.  The `DATALAD_TESTS_SSH=1`
and `sudo -E` jobs are the ones to watch on the first real run.

`pypi` is also the **only** method that is identical on all three platforms —
wheels exist for `manylinux_2_34_{x86_64,aarch64}`, `macosx_14_0_arm64`,
`macosx_15_0_x86_64` and `win_amd64`.  The matrix currently needs `-m brew` on
macOS and `-m datalad/packages` on Windows because datalad-installer's conda
method is Linux-only; `pypi` collapses all three to one line and drops a
Homebrew install from the macOS jobs.

**datalad-installer already has this method — it just is not on PyPI.**
`datalad-installer git-annex -m pip` (its *method* selector, not `python -m
pip`) was added in
[datalad-installer#219](https://github.com/datalad/datalad-installer/pull/219)
("Now that @mih provides those builds starting from 10.20250605 release"),
merged 2026-04-15 and released as **v1.2.1**.  But PyPI's newest
`datalad-installer` is **1.1.1 (2024-12-13)**: v1.2.0, v1.2.1 and v1.2.2 exist
only as GitHub releases, and the step does a plain `pip install
datalad-installer`, so CI gets 1.1.1, whose `PipInstaller.PACKAGES` knows only
`datalad`.  So the prerequisite is **publishing v1.2.2 to PyPI** (or installing
datalad-installer from git meanwhile).  Once that is done the scenario becomes
just `_DL_ANNEX_INSTALL_SCENARIO: "git-annex -m pip"` with the `-E new.env`
machinery unchanged — but the `/usr/local/bin` symlinks are still needed, since
`PipInstaller` does not call `manager.addpath()`.

Optional, and only after the plain version is proven: the wheel's console
script is a Python entry point that `os.execv`s the real binary, costing ~14 ms
of interpreter startup per spawn — **+27 % of test time** (§3.3).  Pointing the
symlinks at the binary instead avoids it, at the price of setting `MAGIC`
yourself, which is the only other thing the entry point does:

```yaml
    gadir=$(python -c 'import git_annex, os.path as op; print(op.dirname(git_annex.__file__))')
    sudo ln -sf "$gadir/git-annex" /usr/local/bin/git-annex
    sudo ln -sf "$gadir/git-annex" /usr/local/bin/git-annex-shell
    echo "MAGIC=$gadir/magic.mgc" >> "$GITHUB_ENV"
```

#### A2 — Retire miniconda; keep conda coverage on cron only

`miniconda` in the matrix served two purposes that have both moved on:

* **Python versions** — `actions/setup-python` already provides those, and
  does it in seconds.  Nothing needs conda for that any more.
* **git-annex from a conda package** — still worth covering, but not with
  `miniconda`, which datalad-installer v1.2.x now deprecates outright in
  favour of `miniforge` ("to avoid Anaconda Terms of Service issues").
  `micromamba` (12 s) or `pixi` (3 s) is the faster, more uniform way in
  against miniconda's 266 s on the same machine; §2.1 has the measurement and
  a caveat about pinning through conda at all.

For PRs, neither the conda build nor the standalone bundle needs to be in the
picture at all: both are *packaging* variants of the same git-annex, and a PR
breaking them specifically is rare.  Keep **one cron entry each**:

* `git-annex -m datalad/packages` — the NeuroDebian standalone bundle, i.e.
  what most users run, 12 s to install.  Keeps `runshell`, the bundled `git`
  and `LOCPATH`/`GIT_EXEC_PATH` behavior under test.
* one conda-packaged entry via micromamba/pixi, so that install path keeps
  being exercised.
* the **minimum announced version** (`AnnexRepo.GIT_ANNEX_MIN_VERSION` =
  `10.20230126`, Debian bookworm's) — not on PyPI at all, so this is the one
  ad-hoc conda/NeuroDebian case that has to stay.  It is already in the matrix
  at 0.7 min with a current miniconda.  Natural extension later, as dandi-cli
  recently did: make that job a *minimal-dependencies* job generally, pinning
  the lowest supported versions of the Python dependencies too, not just
  git-annex.

#### A3 — One selection, and a Python sweep that is base + newest  *(~112 job-min/run)*

Two things collapse together here.

**The slow/not-slow split can go.** The 3.12/3.13/3.14 entries come in pairs
that were presumably meant to be complementary halves, but are byte-identical
invocations (§2.2).  Rather than repair the split, drop it: with A1 making a
full run ~2× cheaper, one job per scenario running everything-but-turtle costs
about what the "not slow" half costs today, and saves a second job's worth of
setup — and PRs stop skipping the 101 `@slow`/`network` tests they skip now.

**Keep a Python sweep, but concentrate it.** On PRs: the base supported version
(3.10) and the newest (3.14), both full runs.  On cron: the middles (3.12,
3.13) plus whatever else is cron-only today.  That keeps a partial sweep on
every PR without paying for four of them.

#### A4 — Scope the "scenario smoke" jobs  *(~78 job-min/run)*

Six entries exist to smoke-test an environment knob (log level/target, obscure
filename prefix, locale, `max-batched`, SSH multiplexing off,
pathspec-from-file) and each runs the *whole* suite to do it — 155 min of test
time between them:

| entry                                                                   |     `Run tests` |
| ----------------------------------------------------------------------- | --------------: |
| `DATALAD_LOG_LEVEL=2`, `LOG_TARGET=/dev/null`, `LOG_*=1`, console UI, … |        27.7 min |
| `_DL_TMPDIR=/var/tmp/sym link`, `LOG_LEVEL=INFO`, `MAX__BATCHED=2`      |        25.0 min |
| `LC_ALL=ru_RU.UTF-8` (full suite)                                       |        39.9 min |
| `SSH_MULTIPLEX__CONNECTIONS=0`, `PATHSPEC__FROM__FILE=always` ×2        | 28.6 + 15.5 min |
| `_DL_TMPDIR=/var/tmp/sym link`, `LOG_TRACEBACK=collide` (slow-only)     |        18.7 min |

The NFS entries already do the right thing with `TESTS_TO_PERFORM`.  Giving
these the same treatment (e.g. `datalad.tests datalad.core datalad.cli
datalad.support`) roughly halves them.  This is a coverage/time judgment call,
hence listed separately from A1–A3.

#### A5 — Coverage: keep it for PRs under review, drop it elsewhere  *(~160 job-min/run)*

Coverage costs **+39 %** of test time (§6.2) and `test.yml` measures it on all
21 jobs while uploading only `if: github.event_name != 'schedule'` — so every
nightly run pays for a report nobody consumes.  It *is* valuable on PRs, so the
gate is not "less coverage" but "coverage where someone reads it":

* **cron runs**: off.
* **draft PRs**: off — nobody is reading the codecov annotation yet.
* **PRs ready for review**: on, as today.

The draft part needs one addition to the trigger so that flipping a PR out of
draft re-runs the suite with coverage on:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
```

`ready_for_review` fires only on draft → ready, not the other way, so flipping
back to draft costs nothing.  In the `Run tests` step:

```yaml
if [ "${{ github.event_name }}" != schedule ] \
   && [ "${{ github.event.pull_request.draft }}" != true ]; then
  PYTEST_OPTS+=( --cov=datalad --cov-report=xml )
fi
```

#### A6 — `-n 2` → an explicit worker count  *(up to 1.58×)*

Measured 1.86× from `-n 1` to `-n 2` and 2.93× to `-n 4` (§6.1), and `-n 2` is
hardcoded while the runners are believed to have 4 vCPU.  `-n auto` is the
tempting spelling but not the reliable one — it follows `os.cpu_count()`, which
on a container-limited runner can report the host's CPUs rather than the
job's quota, and it would silently change behavior on macOS/Windows runners
with different sizing.  So: an explicit `PYTEST_NPROC` knob, default 4 on
Linux, overridable per matrix entry, with the NFS entries left at 2.  Confirm
the runner sizing first with a one-line `nproc` in the workflow, and roll the
change out on one entry before the whole matrix — `test_push.py` already
carries a comment about a test exceeding 30 s "when running in parallel with
n=2", so the suite has some parallelism sensitivity.

#### A7 — Stop setting up NeuroDebian where it is unused

Gate the `neurodebian-ci-setup.sh` lines in `tools/ci/test-env-linux.sh` on a
matrix flag (`needs-neurodebian: true`), set only on the A2 entry that needs
APT.  Also `cache: pip` on `actions/setup-python`, and `uv pip install` for
`requirements-devel.txt` (CONTRIBUTING already recommends `uv`): ~15 s × 20
jobs.

#### A8 — Dead knobs in the workflow

Drop the `DATALAD_TESTS_SETUP_TESTREPOS=1` export (no in-tree reader; the
config *declaration* has to stay, see B4) and the duplicated
`--doctest-modules` in the `Run tests` step.

### PR B — test-suite changes

> **Measured after implementation** (this machine, git-annex 10.20260901 from
> the PyPI wheel).  The B1/B2/B5 rows above are those numbers, not estimates.
> Two of the projections in this section were wrong and are corrected in
> place below: B5's premise about `test_rerun_merges.py`, and the size of the
> win it yields.


#### B1 — `test_files_split`: patch the limit instead of materialising 10 000 files

`@slow  # 313s`, parametrized ×2 → ~10 min/run.  It materialises 100 × 100
files with 101-character names only to push a command line past `CMD_MAX_ARG`
and exercise the chunking in `datalad.utils.generate_file_chunks`.  That
function reads the module-level `datalad.utils.CMD_MAX_ARG` at call time, so
the same path can be exercised with ~200 files and a monkeypatched limit, in
seconds.  Keep the full-size version as `@turtle` for cron if the "real limit"
assurance is wanted.

#### B2 — `git-annex testremote --fast`

`test_gitannex_local` (`@slow`, 41 s) and `test_gitannex_ssh` (the only
collected `@turtle`) call `ds.repo._call_annex(['testremote', 'store'], …)`.
`testremote` accepts `--fast` ("avoid slow operations") and `--size` (default
**1 MiB**); neither is passed.  `['testremote', '--fast', '--size=1KiB',
'store']` should cut both by a large factor while still exercising the RIA
special remote's protocol surface.

#### B3 — Delete `test_s3.py::_test_expiring_token`

`@turtle @integration` on a `_`-prefixed function pytest never collects; it
waits out a 900 s STS token.  Dead code with decorative markers.

#### B4 — Remove the test-repo machinery outright

**Tried, reverted — do not retry without a deprecation cycle.**

The claim below was that `datalad/tests/utils_testrepos.py` has exactly one
in-tree user left (its own test) and that `datalad.tests.setup.testrepos` has
zero readers.  Both are true *in-tree* and both are beside the point: the
consumers are **extensions**, and the Extensions CI job caught it within two
minutes of pushing the removal.

- `datalad-next` does
  `from datalad.tests.test_utils_testrepos import BasicGitTestRepo`
  in `datalad_next/tests/utils.py` — importing from the *test* module, not
  from `utils_testrepos` — so deleting it is `ModuleNotFoundError` at
  collection, for that extension's entire suite.
- `datalad-deprecated` reads `datalad.tests.setup.testrepos`, and without the
  definition `cfg.obtain()` raises
  `RuntimeError: cannot obtain value ... not preconfigured, no default`,
  taking out `test_auto.py`, `test_publish.py` and `test_testrepos.py`.

So this is public API for extensions regardless of how dead it looks from
inside this repository, and `grep` over `datalad/` cannot establish otherwise.
Retiring it means a deprecation cycle coordinated with the extensions, which
is its own piece of work; the original text is kept below for whoever picks
that up.

> `datalad/tests/utils_testrepos.py` (`TestRepo`, `BasicAnnexTestRepo`,
> `BasicGitTestRepo`, `SubmoduleDataset`, `NestedDataset`, `InnerSubmodule`)
> has exactly one in-tree user left: its own `test_utils_testrepos.py`.  The
> `datalad.tests.setup.testrepos` config option in
> `datalad/interface/common_cfg.py` has **zero** readers since the
> nose→pytest migration removed `@with_testrepos`.  Remove all three: the
> module, its test, and the config option — plus the
> `DATALAD_TESTS_SETUP_TESTREPOS` export in `test.yml` (A8).

#### B5 — Fixture reuse by tarball, not by `cp`

`test_rerun_merges.py` (12 `@slow`), `test_update.py` (10), `test_get.py` (8),
`test_create_sibling.py` (7) and `test_push.py` (5) each rebuild the same
dataset hierarchy per test, at ~350 ms per `create()` (§5).  Reusing one built
copy is the win: ~495 ms to build a fixture against **7 ms to untar one**
(§5).  A tarball round-trip is the mechanism to use rather than `cp -a` — it is
6× faster, records modes explicitly instead of relying on `cp`'s flags being
right on BSD as well as GNU, and unpacking into a fresh temp dir avoids the
read-only annex object files that a copy-and-remove cycle trips over when the
tests run as a normal user.

Scope for PR B: convert *one* cluster (`test_rerun_merges.py` is the most
uniform) with a local helper, and only then generalise.

**Correction, from doing it.**  The premise above is wrong for
`test_rerun_merges.py`: its 15 tests do *not* rebuild the same hierarchy.
They build 15 *different* commit graphs, and what they actually share is the
bare `Dataset.create()` they all start from.  So the reusable artifact is an
empty created dataset, not a populated one, and the win is correspondingly
smaller: 496 ms to `create()` against 17 ms to untar, ×15 tests, which took
the module from **41.3 s to 34.7 s (16%)** rather than the "minutes" guessed
above.

`test_rerun_merges.py` is still the right pilot, but for a different reason
than the one given: it is the only one of the listed clusters where the
copies are safe to share a dataset ID and annex UUID.  `test_update.py`,
`test_create_sibling.py` and `test_push.py` all wire two copies together, so
the P11 caveat applies to them from the start and naive tarball reuse is not
available.

#### P11 (separate, later) — a caching dataset fixture

The general form of B5 is a session-scoped fixture that mints a dataset from a
`tree` spec *once*, tars it, and untars a fresh copy per test — effectively a
`with_tree_dataset` keyed on the tree spec plus the creation options, so
several test modules asking for the same shape share one build.  There is prior
art to learn from: `datalad/tests/utils_cached_dataset.py` already implements a
cache of *clones* keyed on a URL (`datalad.tests.cache`), and has no in-tree
users left — the idea was started and dropped.  Worth doing deliberately, with
its own design pass, rather than smuggling it into PR B: the cache key has to
cover everything that affects the result (tree, create options, git/git-annex
version, repo version), and copies share a dataset ID and annex UUID, which is
fine for local-only tests but not for tests that wire two copies together as
siblings.

### Optional, once A1–A3 have landed — durations-based sharding

`test.yml` already uploads a `pytest-report.jsonl` per job.  A committed,
periodically refreshed `tools/ci/test-durations.json` plus a small
`tools/ci/split-tests.py` would turn it into N balanced chunks and replace the
hand-maintained `TESTS_TO_PERFORM` module lists (Windows ×3, macOS ×3, NFS ×2)
with `chunk: i/N`.  Mind the concurrency cap (§2.3): shard only after A3/A4
have freed slots.

### Projected effect

Starting from the measured nightly baseline of **814 job-min / 85 min wall /
21 test jobs**.  Split into what follows from measurements alone and what
additionally needs a judgment call:

**Verified changes only (A1 + A3 + A5 + A7 + A8):**

| step                                                   |  job-min |
| ------------------------------------------------------ | -------: |
| baseline                                               |      814 |
| A1: install 196 min → ~10 min                          |     −186 |
| A3: drop 3 duplicate jobs (their 115 min of test time) |     −115 |
| A1: test time ÷1.5 on the remaining 464 min            |     −155 |
| A5: no coverage on cron runs (÷1.39 on ~309 min)       |      −87 |
| A7+A8: NeuroDebian gating, pip cache/`uv`              |      −20 |
| **remaining**                                          | **~250** |

The ÷1.5 on test time is deliberately below the 2.0–3.5× measured on
annex-heavy modules, since some jobs are NFS-, network- or doctest-bound rather
than annex-bound.  That leaves 18 jobs instead of 21, which drops below the
concurrency cap (§2.3), so the 31 min of queueing disappears: **wall ~30 min
instead of 85**.  On a PR run (11 jobs after A3, coverage retained) the longest
job goes from ~54 min to roughly **28 min** — that is what a contributor would
feel.

**With the judgment calls (A4 scoping, A6 worker count, PR B):** another ÷1.58
on test time from `-n 4` plus ~78 job-min from scoping the scenario jobs would
bring the nightly to roughly **~120 job-min** and a PR run to **~15–20 min
wall**.  Those need the `nproc` confirmation and a coverage judgment
respectively, so they are not in the conservative column.

If the full measured 2.3× build speedup holds in CI rather than the 1.5×
discount applied above, subtract a further ~80 job-min from either column.

## 8. Validating CI changes locally with `act`

[nektos/act](https://github.com/nektos/act) runs a workflow from
`.github/workflows/` locally, in a container, using the real GitHub Actions
expression engine.  For PR A that is worth a lot: the things most likely to
break there are the `filter` job's `yq` expressions, the dynamic-matrix
plumbing and the shell in the `Run tests` step — all of which cost a full CI
round trip to test otherwise, and none of which need a 30-minute test run to
verify.

It works, including inside a Claude Code cloud session, with some setup.  What
was verified here (act 0.2.89):

* `act -l` and the job graph — no container needed.
* the **`filter` job**: the `yq` expressions over `tools/ci/test-jobs.yml`, all
  the way to the full matrix JSON on `$GITHUB_OUTPUT`.
* the **`test` job's plumbing**: `fromJson(needs.filter.outputs.jobs)`,
  `env: ${{ matrix.extra-envs }}` and `runs-on: ${{ matrix.os }}` — act prints
  the expanded matrix entry it is about to run.
* `actions/checkout`, `actions/setup-python@v7` (CPython 3.10.21 installed in
  6.5 s) and `actions/upload-artifact@v7`.
* **A1's whole `Install git-annex` step, plus a real pytest run**: git-annex
  installed from PyPI in 1.0 s, `git-annex-shell` resolved from
  `/usr/local/bin`, and `datalad/core/local/tests/test_create.py` passing
  33/33 — **30 s end to end**.

### Setup in this sandbox

Two obstacles, both surmountable:

1. **No runner image can be pulled.**  The egress policy denies Docker Hub and
   ghcr blob hosts (`production.cloudfront.docker.com`,
   `pkg-containers.githubusercontent.com` → 403), so
   `catthehacker/ubuntu:act-latest` is unavailable.  Workaround: build an image
   from the sandbox's own root filesystem, which already has python, git, node,
   `sudo` and both `yq` flavors:

   ```sh
   dockerd --iptables=false --bridge=none &          # no daemon runs by default
   tar -cf - --numeric-owner --one-file-system \
       --exclude=./proc --exclude=./sys --exclude=./dev --exclude=./run \
       --exclude=./tmp --exclude=./var/tmp --exclude=./var/lib/docker \
       --exclude=./root/.cache --exclude=./home/user -C / . \
     | docker import - actrunner:local                # ~5 min, 2.7 GB
   # /tmp was excluded, so recreate it, and stub the one missing tool
   cid=$(docker run -d --network=host actrunner:local tail -f /dev/null)
   docker exec "$cid" sh -c 'mkdir -p /tmp /var/tmp && chmod 1777 /tmp /var/tmp
                             printf "#!/bin/sh\nexec echo Module Size Used_by\n" > /usr/local/bin/lsmod
                             chmod +x /usr/local/bin/lsmod'
   docker commit "$cid" actrunner:local && docker rm -f "$cid"
   ```

   `/tmp` matters: without it `git-annex` fails with `openFdAt template hash:
   does not exist` on every `annex add`.  `lsmod` is only there because the
   workflow runs `sudo lsmod` informationally and the sandbox lacks `kmod`.

2. **Node actions do not trust the sandbox proxy's CA**, so
   `actions/setup-python` fails with `self-signed certificate in certificate
   chain`.  Pass the bundle in.

   ```sh
   act schedule --pull=false -P ubuntu-latest=actrunner:local --bind \
       --container-options "--network=host" \
       --artifact-server-path /tmp/act-artifacts \
       --env HTTPS_PROXY="$HTTPS_PROXY" --env https_proxy="$HTTPS_PROXY" \
       --env NODE_EXTRA_CA_CERTS=/root/.ccr/ca-bundle.crt \
       -W .github/workflows/test.yml -j filter
   ```

   `--pull=false` stops act re-pulling the local image; `--network=host` is
   needed because the daemon runs without a bridge; `--bind` mounts the
   checkout instead of cloning.

On an ordinary developer machine none of this applies — registry pulls work,
so `act -j filter` with the default image is enough.

### Limits worth knowing before relying on it

* **Self-hosted mode (`-P ubuntu-latest=-self-hosted`) is not useful here.**
  It runs steps directly on the host, but gives each run a *fresh, empty*
  workspace under `~/.cache/act/<hash>/hostexecutor`, makes `actions/checkout`
  a no-op, and ignores `--env GITHUB_WORKSPACE`, so nothing in the repo is
  visible to the steps.  Container mode with `--bind` is the usable one.
* **Blocked hosts still block.**  `tools/ci/test-env-linux.sh` fails at its
  first line here because `neuro.debian.net` is denied by the same egress
  policy — which is an argument for A7 (gate that setup) quite apart from the
  minutes it costs.
* **act is for logic, not for timings.**  It cannot tell us anything about
  runner sizing, the 6 h job timeout, the concurrency cap, or the
  GitHub-hosted image's preinstalled tools — the container is our own
  filesystem, not `ubuntu-24.04`.  Every number in this document came from
  real CI or from direct local runs, not from act.
* **No Windows or macOS.**  Those matrix entries can only be tested on GitHub.
* **`env: ${{ matrix.extra-envs }}` is not applied by act.**  A map assigned
  to `env:` is a GitHub-specific behaviour act does not implement, so a local
  run gets the workflow-level defaults instead of the entry's overrides (act
  *does* print the expanded matrix entry, which makes this easy to miss).  Pass
  the ones that matter with `--env` when validating locally, and treat
  per-entry env plumbing as something only GitHub can confirm.
* **`actions/upload-artifact@v7` does not speak to act's artifact server**
  (`unknown field "mime_type"`, then five failed retries).  Since that step is
  `if: always()`, its failure skips everything after it — including `Report
  coverage` — so drop it from a local variant when validating the tail of the
  job.
* Two genuine bugs in A1 were caught this way before any CI round trip: `pixi`
  installing into `$PWD/.pixi` (i.e. leaving untracked cruft inside the
  checkout the tests then run against), and the step's own verification
  reporting the *wrong* git-annex, because `$GITHUB_PATH` only affects
  subsequent steps — so `command -v git-annex` found a previously installed one
  instead of the one just installed.  Both fixed; the second is why the step
  now prepends `$scriptdir` to its own `PATH` before checking.
* A useful accident: the sandbox's `/usr/bin/yq` is the *Python* yq
  (kislyuk), while runners have mikefarah's Go yq.  act surfaced that in the
  first run, which is exactly the class of bug #7933 had to fix in CI
  (`yq //= is not valid in the mikefarah yq on runners`).  Install
  mikefarah's into `/usr/local/bin` before trusting a local `filter` run.

## 9. Alternatives considered

Things that were looked at and are *not* in the proposal above, with reasons —
several are worth revisiting if P1–P9 do not go far enough.

* **kyleam's static builds** (`https://dl.kyleam.com/git-annex/`).  Measured
  (§3.3): 111 s against the wheel's 114 s exec'd directly — the same, within
  noise.  Static linking is not what makes it fast; not being wrapped is.  So
  the choice against the wheel comes down to everything else, and there the
  wheel wins: macOS and Windows builds, every release since 10.20250605 rather
  than only the most recent ones, an installer method (`git-annex -m pip`), and
  `LD_PRELOAD` remaining possible.  Recommendation: PyPI as the default; the
  static builds stay valuable as exactly this cross-check.
* **A prebuilt container image** (`container: ghcr.io/datalad/test-env:…` with
  git-annex, APT deps and Python deps baked in, rebuilt nightly).  This removes
  the install steps entirely, not just makes them cheaper — the strongest
  version of P1+P5+P6.  Costs: an image to maintain and publish, plus the
  matrix's Python-version axis turns into an image-tag axis.  Worth doing if
  install time creeps back.
* **Self-hosted runners** (the group already archives CI logs on `smaug`).
  Warm caches and more cores would help, but a public repository running
  fork PRs on self-hosted hardware is a security problem, and it moves CI
  maintenance in-house.  Not recommended for the default path; possibly for
  the cron-only heavy jobs.
* **GitHub larger runners** (8/16-vCPU).  Paid, and the standard runners are
  free for public repos, so this converts money into wall time.  Only worth it
  if the concurrency cap (§2.3), not CPU, stops being the binding constraint.
* **Test-impact selection** (`pytest-testmon` or a coverage-based mapping from
  changed files to tests) for PR runs.  Tempting, but datalad's tests are
  integration-style: most of them touch `datalad.utils`/`support.gitrepo`/
  `support.annexrepo`, so a dependency-based selector would select nearly
  everything for the changes that matter, while risking false negatives on the
  ones it prunes.  Durations-based balancing (P9) gives most of the wall-time
  win without the correctness risk.
* **Dropping coverage entirely.**  Measured at +39 % (§6.2).  A5 turns it off
  where nobody reads it — cron runs, where the report is discarded, and draft
  PRs, where nobody is looking at the codecov annotation yet — and keeps it for
  PRs under review, where it is the point.  Dropping it from those too would
  save more but trade away a review signal, which is not a trade the
  measurements can make.
* **Marking more tests `@slow`.**  This was the obvious reading of "partition
  the slow cases", but the duration distribution (§4.3) says there is no fat
  tail: the split mostly moves 101 tests out of PR coverage for ~13 min.  A3
  goes the other way and removes the split.

## 10. What could not be measured here

* CI's own `pytest-report.jsonl` artifacts:
  `productionresultssa5.blob.core.windows.net` is denied by this sandbox's
  egress policy, so the CI numbers above come from
  the Actions jobs/steps API and the per-test numbers from local runs.  (The
  static builds *were* measured, once `www.oneukrainian.com` was added to the
  environment's **Custom** allowed-domains list — see
  [cloud environments][ce] if some other host needs the same.)

  [ce]: https://code.claude.com/docs/en/cloud-environments#allow-specific-domains
* Whether GitHub's Linux runners here really give 4 vCPU (the `-n 2` question,
  §6.1).  `datalad wtf` now reports `system.cpus` (both `os.cpu_count()` and,
  where the platform distinguishes them, the affinity mask), and CI already
  runs `datalad wtf`, so the number is in every job's log.
* Every local number comes from one 4-vCPU container, where two runs of an
  identical configuration differed by ~8 %.  Ratios within a single sitting are
  solid; absolute seconds across sittings are not.

## 11. Reproducing the local measurements

Both halves of §3 -- the startup micro-benchmark and the test-subset wall
time -- were measured with a throwaway script that is not worth carrying in
the tree.  The recipe it automated:

```sh
# three flavors of the same version
pip download --no-deps --only-binary :all: git-annex==10.20260316
curl -O https://conda.anaconda.org/conda-forge/linux-64/git-annex-10.20260316-nodep_h1234567_0.conda
curl -LO https://github.com/datalad/git-annex/releases/download/10.20260316/git-annex-standalone_10.20260316-1.ndall%2B1_amd64.deb
# then: unpack each into its own prefix, put its bin/ first in PATH, and run
python -m pytest -c tox.ini -q -n 2 \
  -m "not (integration or usecase or slow or network or turtle)" \
  datalad/core datalad/support/tests/test_annexrepo.py
```

Process-spawn counts were obtained by putting counting shims named `git` and
`git-annex` first in `PATH` and appending a line per invocation.
