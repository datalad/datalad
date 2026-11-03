# DataLad Split Command - Prototype Experiments

This directory contains experimental scripts to validate the git/git-annex command sequences needed for the split command implementation.

## Experiments

### 01_basic_filter.sh
**Purpose**: Test basic git filter-branch + git-annex filter-branch workflow

**What it tests**:
- Clone → git-annex filter-branch → git filter-branch workflow
- Metadata cleanup with git annex forget
- Verification that only target files remain
- Size reduction from filtering

**Expected outcome**: Filtered repository should contain only files from the target subdirectory, with cleaned git-annex metadata.

**Run**: `bash experiments/01_basic_filter.sh`

### 02_nested_subdatasets.sh
**Purpose**: Test how filter-branch handles nested subdatasets

**What it tests**:
- Subdataset preservation during filtering
- .gitmodules path updates
- Git submodule state after filtering
- Whether nested subdatasets remain functional

**Expected outcome**: Understand whether nested subdatasets survive filtering and if manual intervention is needed.

**Run**: `bash experiments/02_nested_subdatasets.sh`

### 03_metadata_cleanup.sh
**Purpose**: Verify git annex forget effectiveness for metadata cleanup

**What it tests**:
- Size reduction from git annex forget
- Removal of references to filtered-out files
- Verification that retained files remain accessible
- Comparison of with/without forget

**Expected outcome**: Quantify the benefit of git annex forget and confirm metadata is properly cleaned.

**Run**: `bash experiments/03_metadata_cleanup.sh`

### 04_performance.sh
**Purpose**: Measure performance and scalability

**What it tests**:
- Timing for clone, filter-branch, and cleanup operations
- Memory usage for various dataset sizes
- Scaling characteristics (linear, quadratic, etc.)
- Identification of bottlenecks

**Expected outcome**: Performance metrics to guide optimization and determine feasibility for large datasets.

**Run**: `bash experiments/04_performance.sh`

**Note**: This test is resource-intensive and will create multi-GB datasets.

## Running Experiments

### Prerequisites

**Required:**
- DataLad installed and configured (`pip install datalad` or see [installation guide](http://handbook.datalad.org/en/latest/intro/installation.html))
- git-annex with filter-branch support (version 8.20200720 or later)
- Sufficient disk space (especially for experiment 04)

**Optional:**
- GNU time for performance measurement (`apt-get install time` on Debian/Ubuntu)

**Verify installation:**
```bash
datalad --version
git annex version | grep "git-annex version"
```

### Quick Start

Run all experiments:
```bash
for exp in experiments/*.sh; do
    echo "Running $exp..."
    bash "$exp"
done
```

Run individual experiment:
```bash
bash experiments/01_basic_filter.sh
```

### Experiment Locations

All experiments create temporary directories under `/tmp/datalad-split-expXX/`:
- Experiment 1: `/tmp/datalad-split-exp01/`
- Experiment 2: `/tmp/datalad-split-exp02/`
- Experiment 3: `/tmp/datalad-split-exp03/`
- Experiment 4: `/tmp/datalad-split-exp04/`

These directories are cleaned and recreated on each run.

## Interpreting Results

### Success Indicators
- ✓ marks indicate expected behavior
- ⚠ marks indicate warnings or unexpected behavior
- ✗ marks indicate errors or failures

### Key Metrics to Observe

1. **Size Reduction**: How much does the filtered repository shrink?
2. **Metadata Cleanup**: Are references to filtered-out files removed?
3. **File Availability**: Do retained files remain accessible via git-annex?
4. **Subdataset Integrity**: Do nested subdatasets survive and function?
5. **Performance**: How long does each operation take? Memory usage?

## Common Issues

### git-annex filter-branch not available
If you see "git-annex filter-branch failed or not available", you may have an older git-annex version. The split command can still work but may not achieve optimal size reduction.

### Permission errors
Ensure you have write access to `/tmp/` or modify the `EXPERIMENT_DIR` variables in the scripts.

### Out of disk space
Experiment 4 creates large datasets. Ensure you have at least 10GB free space, or reduce the test sizes.

## Next Steps

After running experiments:
1. Review results and identify any unexpected behaviors
2. Document findings in the implementation plan
3. Adjust the implementation approach based on learnings
4. Use successful command sequences in the actual split implementation

## Contributing

If you discover issues or have improvements to the experiments:
1. Document your findings
2. Modify the experiment scripts to test your hypothesis
3. Share results with the development team
