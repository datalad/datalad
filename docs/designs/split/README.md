# DataLad Split Command - Design and Implementation

This directory contains the complete design, experimentation, and implementation planning for the `datalad split` command.

## Quick Navigation

### For Understanding the Design
- **[SPLIT_IMPLEMENTATION_PLAN.md](SPLIT_IMPLEMENTATION_PLAN.md)** - Complete technical specification
  - Command parameters and behavior
  - Phase-by-phase implementation plan
  - All features with examples

### For Implementation
- **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** - Step-by-step coding guide
  - Exact code structure following DataLad patterns
  - All helper functions with implementations
  - Testing patterns and examples

- **[ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)** - High-level architecture
  - Command flow diagrams
  - Design patterns explained
  - Integration points

### For Validation
- **[experiments/](experiments/)** - Prototype experiments (1-13)
  - **[EXPERIMENT_RESULTS.md](experiments/EXPERIMENT_RESULTS.md)** - Findings from all experiments
  - **[13_filter_branch_options_analysis.md](experiments/13_filter_branch_options_analysis.md)** - git-annex filter-branch options analysis

## Implementation Status

### ✅ Completed
1. **Design Phase** - Comprehensive specification
2. **Experimentation Phase** - 13 experiments validating all approaches
3. **Implementation Planning** - Detailed code-level guide

### 📋 Ready for Implementation
Following the IMPLEMENTATION_GUIDE.md step-by-step will create a production-ready command.

## Key Findings from Experiments

### Experiment Highlights

| Experiment | Finding | Impact |
|------------|---------|--------|
| **1-5** | Basic workflow validation | ✓ Clone → filter → cleanup works |
| **7** | Location tracking preservation | ✓ Use `--include-all-key-information` |
| **9** | In-place split workflow | ✓ Most efficient approach |
| **11** | Critical order fix | ✓ `git rm --cached` MUST be before clone |
| **12** | Content strategies | ✓ Worktree: 4KB overhead vs 5.3M clone |
| **13** | git-annex options | ✓ Current approach is optimal |

### Critical Workflow (from Experiment 11)

```bash
# CORRECT ORDER (Experiment 11 fix):
1. git rm -r --cached <path>/     # Remove from index FIRST
2. rm -rf <path>                  # Physically remove
3. git clone . <path>             # Clone into location
4. cd <path> && filter            # Filter subdataset
5. git submodule add ./<path>     # Register as submodule
```

### Worktree Efficiency (from Experiment 12)

```
Storage Comparison:
- Clone mode:    Parent 5.3M + Subdataset 5.3M = ~10.6M total
- Worktree mode: Parent 5.3M + Worktree 4KB   = ~5.3M total (99.9% savings!)
```

**Why worktree works**:
- Git worktree shares `.git/objects` (standard worktree behavior)
- After filtering, git-annex symlinks (`../../../.git/annex/objects/...`) still resolve to parent
- Shares BOTH git history AND annex content
- No manual symlink hacks needed

## Command Parameters (Final Design)

### Core Parameters
```bash
datalad split <path> [<path> ...]
  -d, --dataset DATASET           # Dataset to split
  --clone-mode {clone,worktree,reckless-ephemeral}
  --content {auto,copy,move,none}
  --worktree-branch-prefix PREFIX # Default: "split/"
  --check {full,annex,tree,none}  # Default: "full"
  --propagate-annex-config CONFIG
  --preserve-branch-name          # Default: true
  -f, --force                     # Skip confirmation
  --dry-run                       # Preview only
```

### Examples
```bash
# Basic split
datalad split data/subject01

# Multiple with glob
datalad split data data/subject*

# Worktree mode (most efficient)
datalad split --clone-mode=worktree data/subjects/subject01

# With content copy
datalad split --clone-mode=clone --content=copy data/raw

# Custom branch prefix
datalad split --clone-mode=worktree --worktree-branch-prefix=archive/ data/old/study01
```

## git-annex filter-branch Usage (from Experiment 13)

### Validated Approach
```bash
git-annex filter-branch <path> \
    --include-all-key-information \
    --include-all-repo-config
```

### Options NOT Needed
- ❌ `--include-global-config` - Redundant with `--include-all-repo-config`
- ❌ `--all` - Mutually exclusive with path specification
- ❌ `--fast` - No performance benefit for our use case

## Branch Naming (from User Feedback)

Git branch names can contain slashes, so we preserve hierarchical structure:

```bash
# Path: data/subjects/subject01
# Branch: split/data/subjects/subject01  (hierarchical!)

git branch split/data/subjects/subject01 HEAD
git worktree add data/subjects/subject01 split/data/subjects/subject01
```

## Implementation Phases

### Phase 1: Core Infrastructure ✅ Planned
- Parameter system with constraints
- Path validation
- Safety warnings
- Basic split workflow

### Phase 2: Split Modes ✅ Planned
- Clone mode (default)
- Worktree mode (most efficient)
- Reckless-ephemeral mode (temporary)

### Phase 3: Content Handling ✅ Planned
- Auto mode (default: none)
- Copy mode (duplicate content)
- Move mode (transfer content)
- None mode (on-demand retrieval)

### Phase 4: Advanced Features ✅ Planned
- Nested subdataset support (`.gitmodules` reconstruction)
- `.gitattributes` reconstruction with path adjustment
- Git-annex config propagation
- Post-split verification

### Phase 5: Testing ✅ Planned
- Parameter validation tests
- Basic split tests
- Mode-specific tests
- Content handling tests
- Edge case tests

## File Organization

```
docs/designs/split/
├── README.md                           # This file
├── SPLIT_IMPLEMENTATION_PLAN.md        # Complete specification
├── IMPLEMENTATION_GUIDE.md             # Step-by-step coding guide
├── ARCHITECTURE_OVERVIEW.md            # High-level architecture
│
├── experiments/
│   ├── EXPERIMENT_RESULTS.md           # All experiment findings
│   ├── 01_basic_filter.sh              # Basic workflow
│   ├── 07_correct_location_tracking.sh # Location tracking
│   ├── 09_in_place_split.sh            # In-place approach
│   ├── 11_repronim_containers_split.sh # Real-world test
│   ├── 12_content_mode_strategies.sh   # Content modes
│   └── 13_filter_branch_options_analysis.md  # git-annex options
│
└── [Other experiment scripts 02-06, 08, 10]
```

## DataLad Integration Points

### 1. File Location
```python
# Main implementation
datalad/distribution/split.py

# Tests
datalad/distribution/tests/test_split.py

# API registration
datalad/api.py: from .distribution.split import Split
```

### 2. Command Access
```python
# Python API
from datalad.api import split
results = split('data/subject01', dataset='/path/to/ds')

# Dataset method
ds = Dataset('/path/to/ds')
results = ds.split('data/subject01')

# CLI
datalad split data/subject01 -d /path/to/ds
```

### 3. Result Format
```python
[
    {
        'action': 'split',
        'status': 'ok',  # or 'error', 'impossible', 'notneeded'
        'path': '/path/to/subdataset',
        'type': 'dataset',
        'message': 'Successfully split ...',
        'refds': '/path/to/parent',
    }
]
```

## Design Principles

1. **Safety First**: Require backup, show warnings, support dry-run
2. **Efficiency**: Worktree mode for local reorganization
3. **Flexibility**: Multiple clone modes and content strategies
4. **Robustness**: Comprehensive validation and verification
5. **DataLad Integration**: Follow established patterns and conventions

## References

### GitHub Issue
- [#3554](https://github.com/datalad/datalad/issues/3554) - Original feature request

### Related Commands
- `subdatasets` - Pattern for path handling and validation
- `install` - Pattern for complex operations
- `clone` - Pattern for repository creation

### Git Documentation
- [git-filter-branch](https://git-scm.com/docs/git-filter-branch)
- [git-worktree](https://git-scm.com/docs/git-worktree)
- [git-annex-filter-branch](https://git-annex.branchable.com/git-annex-filter-branch/)

## Next Steps

To implement the split command:

1. **Read** IMPLEMENTATION_GUIDE.md from top to bottom
2. **Create** `datalad/distribution/split.py` following Part 1
3. **Implement** each part sequentially (Parts 2-6)
4. **Create** tests in `datalad/distribution/tests/test_split.py` (Part 7)
5. **Register** in `datalad/api.py` (Part 8)
6. **Test** all modes and content strategies
7. **Document** in DataLad's command reference

The implementation guide provides exact code following DataLad's patterns, making this a straightforward implementation task.

## Credits

Design and experimentation conducted with extensive validation of git and git-annex behavior, following DataLad's established architecture and coding conventions.
