# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Benchmarks for save and run operations on realistic dataset hierarchies.

These benchmarks cover:
- Standard save on a small dataset -- regression guard
- Standard save on a heavy hierarchy (10 annex subs × 1000 files)
- run() on a heavy hierarchy

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

    Guards against regressions in the save code path.
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
        self.ds.run('echo plain > plain_file', result_renderer='disabled')


# ---- benchmarks: heavy hierarchy ------------------------------------------
# 10 subdatasets × 1000 tracked files each.
# Measures the cost of recursive save/run scanning a large tree
# when only 2 of 10 subdatasets have changes.


class save_heavy_hierarchy(SuprocBenchmarks):
    """save on a heavy hierarchy (10 subs × 1000 files).

    Benchmarks standard recursive save after modifying files in only
    2 of 10 subdatasets.

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
        # Add a new file in 2 of 10 subdatasets (the rest stay clean).
        # We create new files rather than modifying existing ones because
        # annexed files are read-only symlinks.
        for si in (0, 5):
            sub = Dataset(op.join(ds_path, f"sub{si:02d}"))
            (sub.pathobj / "new_file.txt").write_text("added by setup")

    def time_save(self):
        """Standard recursive save — the baseline."""
        self.ds.save(recursive=True, message="bm save")


class run_heavy_hierarchy(SuprocBenchmarks):
    """End-to-end run() on a heavy hierarchy.

    Command touches 2 of 10 subdatasets: creates a file in each.
    Measures the full run pipeline on a realistic tree.
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
        """run() that creates files in 2 subs (no inner git commits)."""
        self.ds.run(
            'echo new > sub00/new_file.txt && echo new > sub05/new_file.txt',
            result_renderer='disabled')
