# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Benchmarks for save (including save --from) and run operations.

These benchmarks cover:
- Standard save (no fr=) -- regression guard on small and heavy trees
- save(fr=) with inner commits -- the new merge path
- save(fr=, recursive=True) on a hierarchy -- bottom-up merge propagation
- save(fr=) with a large untracked tree -- 'normal' vs 'all' sensitivity
- run() with/without inner commits -- end-to-end pipeline
- Heavy hierarchy: 10 subdatasets × 1000 files, changes in 2 subs --
  measures the cost of diff_dataset scanning untouched subdatasets

Tagging convention: benchmark classes set ``tags = ['ai_generated']``
to mirror ``@pytest.mark.ai_generated`` in the test suite.  ASV has
no marks system; tags are a project convention for grep/filtering.
"""

import os
import os.path as op
import tarfile
import tempfile

from datalad.api import (
    Dataset,
    create_test_dataset,
)
from datalad.utils import (
    create_tree,
    get_tempfile_kwargs,
    rmtree,
    rotree,
)

from .common import SuprocBenchmarks

# ---- helpers ---------------------------------------------------------------

# Heavy hierarchy uses a manual helper (not create_test_dataset) because
# we need predictable subdataset names (sub00..sub09) to modify specific
# subs in setup().  create_test_dataset randomizes leading dirs.

N_SUBS = 10
N_FILES_PER_SUB = 1000


def _create_heavy_hierarchy(ds_path):
    """Create a super-dataset with N_SUBS annex subdatasets, each containing
    N_FILES_PER_SUB tracked files.  Uses default annex repos to benchmark
    the realistic code path.
    """
    ds = Dataset(ds_path).create()
    for si in range(N_SUBS):
        sub = ds.create(f"sub{si:02d}")
        tree = {
            f"file_{fi:04d}.txt": f"sub{si} file {fi}"
            for fi in range(N_FILES_PER_SUB)
        }
        create_tree(sub.path, tree)
        sub.save(message=f"sub{si:02d}: {N_FILES_PER_SUB} files")
    # A few top-level tracked files
    tree = {f"top_{i:02d}.txt": f"top {i}" for i in range(20)}
    create_tree(ds.path, tree)
    ds.save(message="hierarchy with heavy subs")
    return ds


def _extract_tar(tarpath, dsname, counter_cls):
    """Extract a tarball to a fresh tempdir, return (tempdir, ds_path)."""
    tempdir = tempfile.mkdtemp(
        **get_tempfile_kwargs({}, prefix="bm_"))
    with tarfile.open(tarpath) as tar:
        tar.extractall(tempdir)
    epath = op.join(tempdir, dsname)
    epath_unique = epath + str(counter_cls.ds_count)
    os.rename(epath, epath_unique)
    counter_cls.ds_count += 1
    return tempdir, epath_unique


# ---- benchmarks: small / flat ---------------------------------------------


class save_clean(SuprocBenchmarks):
    """Baseline: standard save without fr= (Status-based path).

    Guards against regressions in the non-fr code path.
    Uses create_test_dataset for a single dataset with 50 files.
    """
    tags = ['ai_generated']

    def setup(self):
        tempdir = tempfile.mkdtemp(
            **get_tempfile_kwargs({}, prefix="bm_save_clean"))
        self.remove_paths.append(tempdir)
        dss = create_test_dataset(
            op.join(tempdir, "ds"), spec='0', seed=0, nfiles=50)
        self.ds = Dataset(dss[0])
        # Dirty 5 files for save to pick up
        for i in range(5):
            (self.ds.pathobj / f"file{i}.dat").write_text("modified")

    def time_save(self):
        self.ds.save(message="benchmark save")


class save_from_flat(SuprocBenchmarks):
    """save(fr=<baseline>) on a flat dataset with inner commits."""
    tags = ['ai_generated']

    params = [[1, 5, 20]]
    param_names = ["n_inner_commits"]

    def setup(self, n_inner_commits):
        tempdir = tempfile.mkdtemp(
            **get_tempfile_kwargs({}, prefix="bm_save_from"))
        self.remove_paths.append(tempdir)
        dss = create_test_dataset(
            op.join(tempdir, "ds"), spec='0', seed=0, nfiles=10)
        self.ds = Dataset(dss[0])
        self.baseline = self.ds.repo.get_hexsha()
        # Create N inner commits
        for i in range(n_inner_commits):
            fname = f"inner_{i:03d}.txt"
            (self.ds.pathobj / fname).write_text(f"inner {i}")
            self.ds.repo.call_git(["add", fname])
            self.ds.repo.call_git(["commit", "-m", f"inner {i}"])
        # Add untracked working-tree changes
        for i in range(3):
            (self.ds.pathobj / f"wt_{i}.txt").write_text(f"wt {i}")

    def teardown(self, n_inner_commits):
        self._cleanup()

    def time_save_from(self, n_inner_commits):
        self.ds.save(fr=self.baseline, message="merge benchmark")


class save_from_untracked(SuprocBenchmarks):
    """save(fr=...) with a large untracked directory.

    Tests the performance impact of untracked='normal' (directory
    entries) vs 'all' (individual files).  With 'normal', a dir of N
    files is 1 entry in paths_by_ds; with 'all' it is N entries.

    Uses create_test_dataset spec with d prefix for the untracked dir.
    """
    tags = ['ai_generated']

    params = [[50, 500, 5000]]
    param_names = ["n_untracked"]

    def setup(self, n_untracked):
        tempdir = tempfile.mkdtemp(
            **get_tempfile_kwargs({}, prefix="bm_save_untrk"))
        self.remove_paths.append(tempdir)
        self.ds = Dataset(op.join(tempdir, "ds")).create(annex=False)
        (self.ds.pathobj / "tracked.txt").write_text("initial")
        self.ds.save(message="baseline")
        self.baseline = self.ds.repo.get_hexsha()
        # One inner commit so fr= is meaningful
        (self.ds.pathobj / "inner.txt").write_text("inner")
        self.ds.repo.call_git(["add", "inner.txt"])
        self.ds.repo.call_git(["commit", "-m", "inner"])
        # Create a large untracked directory
        untracked_dir = op.join(self.ds.path, "build")
        os.makedirs(untracked_dir)
        for i in range(n_untracked):
            with open(op.join(untracked_dir, f"file_{i:05d}"), "w") as f:
                f.write(f"content {i}")

    def teardown(self, n_untracked):
        self._cleanup()

    def time_save_from_untracked(self, n_untracked):
        self.ds.save(fr=self.baseline, message="untracked tree merge")


class run_simple(SuprocBenchmarks):
    """End-to-end run() benchmark on a lightweight single dataset."""
    tags = ['ai_generated']

    def setup(self):
        tempdir = tempfile.mkdtemp(
            **get_tempfile_kwargs({}, prefix="bm_run"))
        self.remove_paths.append(tempdir)
        dss = create_test_dataset(
            op.join(tempdir, "ds"), spec='0', seed=0, nfiles=5)
        self.ds = Dataset(dss[0])

    def time_run(self):
        """run() without inner commits — comparable to master baseline."""
        self.ds.run(
            'echo plain > plain_file',
            result_renderer='disabled')

    def time_run_inner_commit(self):
        """run() with inner commits — triggers merge-commit creation."""
        self.ds.run(
            'echo inner > inner_file && git add inner_file'
            ' && git commit -m "inner"',
            result_renderer='disabled')


# ---- benchmarks: heavy hierarchy ------------------------------------------
# 10 subdatasets × 1000 tracked files each.
# The key question: when `run` or `save --from` touches only 2 of 10
# subdatasets, does diff_dataset scanning all 10 add visible overhead
# compared to the old Status-based path?


class save_heavy_hierarchy(SuprocBenchmarks):
    """save on a heavy hierarchy (10 subs × 1000 files).

    Benchmarks both the standard save (no fr=) and save(fr=) paths
    after modifying files in only 2 of 10 subdatasets.  The overhead
    of scanning 8 untouched subdatasets is what we want to measure.

    setup_cache creates the hierarchy once (expensive ~30s);
    setup extracts it and makes minimal changes.
    """
    tags = ['ai_generated']

    timeout = 3600
    dsname = 'bm_heavy'
    _tarfile = 'bm_heavy.tar'
    ds_count = 0

    def setup_cache(self):
        _create_heavy_hierarchy(self.dsname)
        self._tarfile = op.realpath(self._tarfile)
        rotree(self.dsname, ro=False, chmod_files=False)
        with tarfile.open(self._tarfile, "w") as tar:
            tar.add(self.dsname, recursive=True)
        rmtree(self.dsname)

    def setup(self):
        tempdir, ds_path = _extract_tar(
            self._tarfile, self.dsname, self.__class__)
        self.remove_paths.append(tempdir)
        self.ds = Dataset(ds_path)
        self.baseline = self.ds.repo.get_hexsha()
        # Add a new file in 2 of 10 subdatasets (the rest stay clean).
        # We create new files rather than modifying existing ones because
        # annexed files are read-only symlinks.
        for si in (0, 5):
            sub = Dataset(op.join(ds_path, f"sub{si:02d}"))
            (sub.pathobj / "new_file.txt").write_text("added by setup")

    def time_save(self):
        """Standard recursive save (no fr=) — the baseline."""
        self.ds.save(recursive=True, message="bm save")

    def time_save_from(self):
        """save(fr=baseline) — diff_dataset path, no inner commits."""
        self.ds.save(
            fr=self.baseline, recursive=True, message="bm save --from")


class save_heavy_hierarchy_with_inner(SuprocBenchmarks):
    """save(fr=) on a heavy hierarchy where 2 subs have inner commits.

    Same tree as save_heavy_hierarchy, but the command created git
    commits in 2 subdatasets.  This triggers merge-commit creation in
    those 2 subs + the superdataset (upward propagation), while the
    other 8 subs are scanned but untouched.
    """
    tags = ['ai_generated']

    timeout = 3600
    dsname = 'bm_heavy'
    _tarfile = 'bm_heavy.tar'
    ds_count = 0

    # Reuse the same setup_cache as save_heavy_hierarchy
    setup_cache = save_heavy_hierarchy.setup_cache

    def setup(self):
        tempdir, ds_path = _extract_tar(
            self._tarfile, self.dsname, self.__class__)
        self.remove_paths.append(tempdir)
        self.ds = Dataset(ds_path)
        self.baseline = self.ds.repo.get_hexsha()
        # Create inner commits in 2 of 10 subdatasets
        for si in (0, 5):
            sub = Dataset(op.join(ds_path, f"sub{si:02d}"))
            (sub.pathobj / "inner_file.txt").write_text("inner")
            sub.repo.call_git(["add", "inner_file.txt"])
            sub.repo.call_git(["commit", "-m", f"sub{si:02d} inner"])
        # Also add 1 uncommitted new file in sub00
        sub00 = Dataset(op.join(ds_path, "sub00"))
        (sub00.pathobj / "uncommitted_new.txt").write_text("uncommitted")

    def time_save_from(self):
        """save(fr=) with inner commits — full merge pipeline."""
        self.ds.save(
            fr=self.baseline, recursive=True, message="bm merge")


class run_heavy_hierarchy(SuprocBenchmarks):
    """End-to-end run() on a heavy hierarchy.

    Command touches 2 of 10 subdatasets: creates a file in each.
    Measures the full run -> save(fr=) pipeline on a realistic tree.
    """
    tags = ['ai_generated']

    timeout = 3600
    dsname = 'bm_heavy'
    _tarfile = 'bm_heavy.tar'
    ds_count = 0

    setup_cache = save_heavy_hierarchy.setup_cache

    def setup(self):
        tempdir, ds_path = _extract_tar(
            self._tarfile, self.dsname, self.__class__)
        self.remove_paths.append(tempdir)
        self.ds = Dataset(ds_path)

    def time_run(self):
        """run() that creates files in 2 subs — comparable to master baseline."""
        self.ds.run(
            'echo new > sub00/new_file.txt && echo new > sub05/new_file.txt',
            result_renderer='disabled')

    def time_run_inner_commit(self):
        """run() with inner commits in 2 subs — triggers merges."""
        self.ds.run(
            'cd sub00 && echo x > inner.txt && git add inner.txt'
            ' && git commit -m "sub00 inner"'
            ' && cd ../sub05 && echo x > inner.txt && git add inner.txt'
            ' && git commit -m "sub05 inner"',
            result_renderer='disabled')
