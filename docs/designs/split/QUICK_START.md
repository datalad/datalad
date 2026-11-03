# Quick Start: DataLad Split Command Implementation

## TL;DR - What This Project Does

Implements a `datalad split` command to split directories in a DataLad dataset into independent subdatasets, while preserving history and cleaning up git-annex metadata.

## Current Status

**✅ PLANNING COMPLETE** - Ready to run experiments

## What's Been Done

1. ✅ Analyzed requirements from GitHub issue #3554
2. ✅ Researched git-annex filter-branch capabilities
3. ✅ Created comprehensive implementation plan (489 lines)
4. ✅ Prepared 4 prototype experiment scripts
5. ✅ Defined testing strategy (30+ test cases)
6. ✅ Documented everything thoroughly

## Quick File Guide

```
📄 SPLIT_COMMAND_SUMMARY.md     ← START HERE - Complete overview
📄 NEXT_STEPS.md                ← What to do next
📄 SPLIT_IMPLEMENTATION_PLAN.md ← Detailed technical plan
📁 experiments/                 ← Test scripts to validate approach
   ├── README.md                ← How to run experiments
   ├── 01_basic_filter.sh       ← Test basic workflow
   ├── 02_nested_subdatasets.sh ← Test subdataset handling
   ├── 03_metadata_cleanup.sh   ← Test metadata cleanup
   └── 04_performance.sh        ← Performance benchmarks
```

## Next Actions (In Order)

### 1. Read the Overview
```bash
less docs/designs/split/SPLIT_COMMAND_SUMMARY.md
```

### 2. Run Experiments
```bash
# Run all experiments to validate approach
for exp in docs/designs/split/experiments/*.sh; do bash "$exp"; done

# Or run individually:
bash docs/designs/split/experiments/01_basic_filter.sh
bash docs/designs/split/experiments/02_nested_subdatasets.sh
bash docs/designs/split/experiments/03_metadata_cleanup.sh
bash docs/designs/split/experiments/04_performance.sh  # Takes longer, uses more disk
```

### 3. Document Experiment Results
```bash
vim docs/designs/split/experiments/EXPERIMENT_RESULTS.md
```

Note what worked, what didn't, any surprises, performance metrics.

### 4. Start Implementation (When ready)
```bash
# Create the main module
vim datalad/local/split.py

# Follow SPLIT_IMPLEMENTATION_PLAN.md phases 1-8
# Start with Phase 1: Core Infrastructure
```

## Key Technical Insight

**Critical ordering**: `git-annex filter-branch` MUST run BEFORE `git filter-branch`

```bash
# Correct order:
git annex filter-branch <path> --include-all-key-information
git filter-branch --subdirectory-filter <path> HEAD
git annex forget --force --drop-dead

# Wrong order will leave orphaned metadata!
```

## Prerequisites

- DataLad installed
- git-annex 8.20200720 or later (for filter-branch support)
- Sufficient disk space for cloning (~2x dataset size)

Check versions:
```bash
datalad --version
git annex version | grep "git-annex version"
```

## Example Usage (When Implemented)

```bash
# Split a directory into subdataset
datalad split data/subject01

# Split multiple nested with shell glob (makes data/, data/subject*/ all subdatasets)
datalad split data data/subject*

# Preview changes
datalad split --dry-run data/subject01

# Pattern-based splitting
datalad split --regex-subdatasets 'data/subject\d+'
```

## Getting Help

- 📖 Read: `SPLIT_COMMAND_SUMMARY.md` for complete overview
- 🔧 Technical details: `SPLIT_IMPLEMENTATION_PLAN.md`
- 🚀 What to do next: `NEXT_STEPS.md`
- 🧪 Run experiments: `experiments/README.md`
- 💬 Ask: GitHub issue #3554 or Matrix #datalad:matrix.org

## Key Files Summary

| File | Size | Purpose |
|------|------|---------|
| SPLIT_COMMAND_SUMMARY.md | 18KB | Complete project overview |
| SPLIT_IMPLEMENTATION_PLAN.md | 18KB | Detailed technical plan |
| NEXT_STEPS.md | 7KB | Next actions guide |
| QUICK_START.md | This file | You are here! |
| experiments/*.sh | 22KB | Validation scripts |

## Questions?

1. **What does this command do?**  
   Splits directories in a dataset into independent subdatasets with filtered history.

2. **Why is this hard?**  
   Need to filter git history, clean git-annex metadata, and handle nested subdatasets.

3. **What's the approach?**  
   Clone → filter history → filter metadata → clean up → register subdataset.

4. **What's next?**
   Run experiments to validate the approach works as expected.

## Ready to Start?

```bash
# Read the overview
less docs/designs/split/SPLIT_COMMAND_SUMMARY.md

# Run experiments
bash docs/designs/split/experiments/01_basic_filter.sh

# When ready, start implementing
vim datalad/local/split.py
```

Good luck! 🚀
