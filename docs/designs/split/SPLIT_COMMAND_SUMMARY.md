# DataLad Split Command - Project Summary

## Overview

This project implements a `datalad split` command to split DataLad datasets into multiple subdatasets. The command addresses [GitHub Issue #3554](https://github.com/datalad/datalad/issues/3554), which requests functionality to retroactively reorganize directories within a dataset into independent subdatasets.

## Problem Statement

Users often discover too late that their dataset structure should have been organized differently with subdatasets. Currently, there's no clean way to:
- Split a directory into a subdataset while preserving history
- Handle nested subdatasets during the split
- Clean up git-annex metadata to avoid bloat
- Maintain file availability information after splitting

## Proposed Solution

A new `datalad split` command that:
1. Clones the dataset to avoid destructive in-place modifications
2. Filters git history using `git filter-branch --subdirectory-filter`
3. Filters git-annex metadata using `git-annex filter-branch`
4. Cleans up metadata with `git annex forget --force --drop-dead`
5. Registers the new subdataset in the parent
6. Handles nested subdatasets via bottom-up traversal

### Key Innovation: Bottom-Up Traversal

The implementation handles nested subdatasets by processing from leaves to root, ensuring that subdatasets within the split path are properly preserved and registered.

## Project Structure

```
docs/designs/split/
├── SPLIT_IMPLEMENTATION_PLAN.md    # Detailed implementation plan
├── NEXT_STEPS.md                   # Quick reference for next actions
├── SPLIT_COMMAND_SUMMARY.md        # This file - project overview
├── QUICK_START.md                  # Quick start guide
└── experiments/                     # Prototype validation scripts
    ├── README.md                    # Experiment documentation
    ├── 01_basic_filter.sh          # Basic workflow validation
    ├── 02_nested_subdatasets.sh    # Subdataset handling test
    ├── 03_metadata_cleanup.sh      # Metadata cleanup verification
    └── 04_performance.sh           # Performance benchmarking
```

## Documentation Overview

### 1. SPLIT_IMPLEMENTATION_PLAN.md (18 KB)
**Comprehensive implementation blueprint**

Sections:
- Executive Summary & Use Cases
- Technical Approach (clone-based filtering)
- Proposed Command Interface & Parameters
- 8 Implementation Phases:
  1. Core Infrastructure
  2. Core Functionality
  3. Advanced Features
  4. Nested Subdataset Support
  5. Testing Strategy (comprehensive test plan)
  6. Prototype Experimentation
  7. Documentation
  8. Advanced Considerations
- Implementation Checklist
- Known Limitations & Future Work

### 2. NEXT_STEPS.md (7 KB)
**Quick reference guide for immediate actions**

Contents:
- What's completed (research, planning, experiments)
- Immediate next steps (run experiments, document results)
- Phase overview
- Critical success factors
- Key resources and design decisions
- Known challenges and tips
- Progress tracking checklist

### 3. experiments/ Directory
**4 executable bash scripts + documentation**

Each experiment tests a specific aspect of the technical approach:

- **01_basic_filter.sh**: Validates the core workflow
  - Tests: clone → filter → cleanup sequence
  - Verifies: Size reduction, content filtering, metadata cleanup

- **02_nested_subdatasets.sh**: Tests subdataset handling
  - Tests: Filter with nested subdatasets present
  - Verifies: Subdataset preservation, .gitmodules updates

- **03_metadata_cleanup.sh**: Measures cleanup effectiveness
  - Tests: git annex forget impact
  - Verifies: Metadata removal, size reduction, file availability

- **04_performance.sh**: Performance benchmarking
  - Tests: Small (10MB), medium (200MB), large (2.5GB) datasets
  - Measures: Time and memory for each operation

## Command Interface

### Basic Usage
```bash
datalad split [-d DATASET] [OPTIONS] PATH [PATH ...]
```

### Key Parameters
- **PATH**: Directory(ies) to split into subdatasets (required)
- **-d, --dataset**: Parent dataset (default: current)
- **--regex-subdatasets REGEX**: Pattern-based batch splitting
- **-c, --cfg-proc PROC**: Apply configuration to new subdatasets
- **--skip-rewrite {all,parent,subdataset}**: Control history rewriting
- **--dry-run**: Preview changes without executing
- **--force**: Proceed despite uncommitted changes
- **-r, --recursive**: Handle nested subdatasets (default: true)
- **--jobs N**: Parallel processing for multiple paths

### Example Commands
```bash
# Simple: split one directory
datalad split data/subject01

# Multiple nested with shell glob (makes data/, data/subject*/ all subdatasets)
datalad split data data/subject*

# Pattern-based (batch operation)
datalad split --regex-subdatasets 'data/subject\d+'

# With configuration processor
datalad split -c yoda data/code

# Preview without changes
datalad split --dry-run data/subject01

# Incremental mode (no history rewrite, safer but less cleanup)
datalad split --skip-rewrite all data/subject01
```

## Technical Approach

### Core Workflow
1. **Validate Inputs**: Check paths exist, aren't subdatasets, don't overlap
2. **Discover Nested**: Find any subdatasets within target paths
3. **Bottom-Up Processing**: Handle deepest subdatasets first
4. **Clone & Filter**: For each path:
   - Clone dataset to temporary location
   - Run `git-annex filter-branch <path>` (metadata filtering)
   - Run `git filter-branch --subdirectory-filter <path>` (history filtering)
   - Mark origin dead, remove remote
   - Run `git annex forget --force --drop-dead` (cleanup)
5. **Register Subdataset**: Install filtered repo as subdataset in parent
6. **Remove Original Content**: Clean up original path in parent
7. **Commit Changes**: Save parent dataset state

### Critical Insight: Command Order

**git-annex filter-branch MUST run BEFORE git filter-branch**

This ensures git-annex metadata is filtered before the git history is rewritten, preventing orphaned metadata references.

### Nested Subdataset Strategy

Use **bottom-up traversal**:
1. Discover all subdatasets recursively in target path
2. Sort by depth (deepest first)
3. Process leaves before parents
4. Preserve subdataset registrations during filtering

## Testing Strategy

### Test Categories (from Phase 5 of implementation plan)

1. **Basic Functionality** (8 tests)
   - Simple directory split
   - Multiple directory split
   - History preservation
   - Annexed content preservation

2. **Git-Annex Integration** (4 tests)
   - Metadata filtering
   - Key information preservation
   - Unrelated key cleanup
   - Special remote handling

3. **Nested Subdatasets** (4 tests)
   - Preservation during split
   - Hierarchy maintenance
   - Cross-boundary handling
   - Bottom-up processing order

4. **Edge Cases** (6 tests)
   - Nonexistent paths
   - Already subdatasets
   - Overlapping paths
   - Dataset root
   - Empty directories
   - Uncommitted changes

5. **Configuration & Options** (4 tests)
   - Configuration processors
   - Dry-run mode
   - Skip-rewrite modes
   - Output path specification

6. **Error Handling** (3 tests)
   - Missing dataset
   - Permission errors
   - Git-annex unavailable

7. **Integration Tests** (3 tests)
   - Split-then-clone roundtrip
   - Remote operations
   - Complete workflow scenarios

8. **Performance Tests** (benchmarks/)
   - Large directory handling
   - Many subdatasets
   - Memory usage profiling

## Key Design Decisions

1. **Clone-Based vs In-Place**: Clone-based for safety
2. **History Filtering**: Support both full rewrite and incremental modes
3. **Metadata Cleanup**: Use git-annex filter-branch + forget
4. **Nested Subdatasets**: Bottom-up traversal algorithm
5. **Command Ordering**: git-annex filter-branch BEFORE git filter-branch
6. **Multiple Strategies**: Horizontal/vertical/incremental pruning
7. **Dry-Run**: Preview mode to prevent mistakes

## Risk Mitigation

### Identified Risks
1. **Data Loss**: Incorrect filtering could lose availability info
2. **History Corruption**: Git filter-branch is powerful but dangerous
3. **Performance**: Large datasets may be very slow
4. **Complexity**: Nested subdatasets add significant complexity

### Mitigation Strategies
1. **Extensive Testing**: 30+ test cases covering edge cases
2. **Clone-Based**: Never modify original until verified
3. **Dry-Run Default**: Consider requiring explicit --execute
4. **Comprehensive Docs**: Clear warnings and examples
5. **Experiment First**: Validate approach before implementing
6. **Community Review**: Get feedback from maintainers

## Dependencies

### Required
- DataLad (any recent version)
- Git (any version supporting filter-branch)
- git-annex with filter-branch support (8.20200720+)

### Optional
- GNU time (for performance measurements)
- Sufficient disk space for cloning during split

## Success Criteria

Implementation complete when:
- ✅ Comprehensive plan created
- ✅ Experiments prepared
- ⏳ Experiments validate approach
- ⏳ Core functionality working
- ⏳ Nested subdatasets handled correctly
- ⏳ All tests passing
- ⏳ Documentation complete
- ⏳ Code review approved
- ⏳ Merged to main branch

## Resources

### Documentation
- [GitHub Issue #3554](https://github.com/datalad/datalad/issues/3554) - Original request
- [GitHub Issue #600](https://github.com/datalad/datalad/issues/600) - Related filtering discussion
- [git-annex filter-branch](https://git-annex.branchable.com/git-annex-filter-branch/) - Core tool documentation

### DataLad
- [DataLad Handbook](http://handbook.datalad.org) - User guide
- [DataLad Documentation](http://docs.datalad.org) - API documentation
- [DataLad GitHub](https://github.com/datalad/datalad) - Source code

### Community
- Matrix: #datalad:matrix.org
- Mailing List: datalad@googlegroups.com
- Issues: https://github.com/datalad/datalad/issues

## Contributing

1. **Run Experiments**: Validate technical approach
2. **Document Results**: Share findings in `experiments/EXPERIMENT_RESULTS.md`
3. **Implement Incrementally**: Start with basic case, add complexity
4. **Write Tests First**: Test-driven development
5. **Document as You Go**: Docstrings, examples, warnings
6. **Request Review**: Get feedback early and often

## License

This implementation follows DataLad's MIT license.

## Authors

- Planning: Based on community discussion in issue #3554
- Primary contributor: [To be determined]
- Contributors: [Will be listed as implementation progresses]

## Acknowledgments

- **Kyle Meyer**: Original technical approach proposal
- **Yaroslav Halchenko**: Interface design and use cases
- **DataLad Community**: Feedback and requirements gathering
- **git-annex**: Joey Hess for filter-branch functionality

---

**Status**: Planning Complete, Ready for Experimentation
**Version**: 0.1 (Planning Phase)
**Last Updated**: 2026-01-16
**Next Milestone**: Validate approach via experiments
