# Next Steps for DataLad Split Implementation

## Quick Reference

This document provides a quick overview of what has been completed and what needs to happen next.

## ✅ Completed

1. **Thorough Research**
   - Analyzed GitHub issue #3554 and comment #1202591654
   - Reviewed git-annex filter-branch documentation
   - Understood DataLad command structure and patterns
   - Identified key challenges (nested subdatasets, metadata cleanup)

2. **Implementation Plan Created**
   - Comprehensive 489-line implementation plan: `SPLIT_IMPLEMENTATION_PLAN.md`
   - Covers all phases from core infrastructure to testing
   - Addresses nested subdataset handling with bottom-up traversal
   - Includes multiple pruning strategies

3. **Prototype Experiments Prepared**
   - 4 experimental bash scripts in `experiments/` directory:
     - `01_basic_filter.sh` - Tests basic workflow
     - `02_nested_subdatasets.sh` - Tests subdataset handling
     - `03_metadata_cleanup.sh` - Verifies metadata cleanup effectiveness
     - `04_performance.sh` - Measures performance/scalability
   - All scripts are executable and documented

## 🔄 Immediate Next Steps

### 1. Run Prototype Experiments (1-2 hours)

**Priority: HIGH - Do this first!**

Run the experiments to validate the technical approach:

```bash
# Run all experiments
bash docs/designs/split/experiments/01_basic_filter.sh
bash docs/designs/split/experiments/02_nested_subdatasets.sh
bash docs/designs/split/experiments/03_metadata_cleanup.sh
bash docs/designs/split/experiments/04_performance.sh  # This one takes longer and uses more disk space

# Or run them all in sequence:
for exp in docs/designs/split/experiments/*.sh; do bash "$exp"; done
```

**What to look for**:
- Does git-annex filter-branch work as expected?
- Are nested subdatasets preserved correctly?
- Is metadata properly cleaned up?
- What's the performance characteristics?
- Any unexpected behaviors or edge cases?

### 2. Document Experiment Results (30 minutes)

After running experiments, document findings:

```bash
# Create a results file
vim docs/designs/split/experiments/EXPERIMENT_RESULTS.md
```

Include:
- Which experiments succeeded/failed
- Any surprising behaviors
- Performance metrics from experiment 04
- Adjustments needed to implementation plan
- Blockers or issues discovered

### 3. Validate Approach with Community (optional but recommended)

Before implementing, consider:
- Posting experiment results to GitHub issue #3554
- Asking for feedback on the implementation plan
- Checking if there are known issues with the approach
- Verifying git-annex version requirements

### 4. Begin Core Implementation (Week 1-2)

Once experiments validate the approach:

```bash
# Create the main implementation file
touch datalad/local/split.py

# Start with the class structure
# Refer to SPLIT_IMPLEMENTATION_PLAN.md Phase 1 & 2
```

**Start with**:
1. Parameter definitions
2. Path validation
3. Basic workflow without nested subdatasets
4. Simple test case

## 📋 Implementation Phases Overview

Refer to `SPLIT_IMPLEMENTATION_PLAN.md` for details. Summary:

- **Phase 1**: Core Infrastructure
  - Create module structure
  - Define parameters
  - Register command

- **Phase 2**: Core Functionality
  - Path validation
  - History filtering workflow
  - Subdataset registration
  - Content removal

- **Phase 3**: Advanced Features
  - Incremental mode
  - Pattern-based splitting
  - Configuration processors
  - Dry-run mode

- **Phase 4**: Nested Subdatasets
  - Bottom-up traversal
  - Boundary handling

- **Phase 5**: Testing
  - Comprehensive test suite
  - Edge cases
  - Integration tests

- **Phase 6**: Already completed! (Experiments)

- **Phase 7**: Documentation
  - Command docs
  - User guide
  - Developer docs

- **Phase 8**: Finalization
  - Code review
  - Performance optimization
  - Final testing

## 🎯 Critical Success Factors

1. **Validate with experiments first** - Don't skip this!
2. **Test early, test often** - Write tests alongside implementation
3. **Handle nested subdatasets correctly** - This is the trickiest part
4. **Clean metadata properly** - Users care about repository size
5. **Provide good error messages** - Users will make mistakes
6. **Document limitations** - Be honest about what doesn't work

## 📚 Key Resources

- **Implementation Plan**: `SPLIT_IMPLEMENTATION_PLAN.md` (489 lines)
- **Experiments**: `experiments/` directory (4 scripts + README)
- **GitHub Issue**: https://github.com/datalad/datalad/issues/3554
- **git-annex filter-branch**: https://git-annex.branchable.com/git-annex-filter-branch/

## 🔍 Key Design Decisions

1. **Clone-based approach** - Safer than in-place modifications
2. **Bottom-up traversal** - Handle deepest subdatasets first
3. **git-annex filter-branch BEFORE git filter-branch** - Critical ordering
4. **Three pruning strategies** - Flexibility for different use cases
5. **Dry-run by default?** - Consider for safety (to be decided)

## ⚠️ Known Challenges

1. **Git-annex version dependency** - filter-branch is relatively new
2. **Performance on large datasets** - May be slow, need optimization
3. **Nested subdataset complexity** - Needs careful testing
4. **Disk space requirements** - Cloning requires temporary space
5. **Backward compatibility** - How to handle existing clones?

## 💡 Tips for Implementation

1. **Start small** - Get basic case working first, add complexity gradually
2. **Use existing DataLad patterns** - Look at create.py, clone.py for examples
3. **Leverage DataLad utilities** - Don't reinvent path handling, etc.
4. **Test on real datasets** - Synthetic tests miss real-world issues
5. **Profile performance** - Identify bottlenecks early
6. **Ask for help** - DataLad community is helpful on GitHub/Matrix

## 🐛 Debugging Experiments

If experiments fail:

```bash
# Enable verbose output
set -x  # Add to script

# Run git-annex with debug
git annex --debug filter-branch ...

# Check git-annex version
git annex version

# Verify dataset state
datalad wtf
```

Common issues:
- git-annex too old (need 8.20200720+)
- Insufficient disk space
- Permissions issues in /tmp
- Dirty working tree in test datasets

## 📞 Getting Help

- **GitHub Issue**: Comment on #3554
- **Matrix Chat**: #datalad:matrix.org
- **Mailing List**: datalad@googlegroups.com
- **Documentation**: http://docs.datalad.org

## ✨ Success Criteria

Implementation is complete when:

- [ ] All test cases pass (including nested subdatasets)
- [ ] Documentation is comprehensive
- [ ] Performance is acceptable (< 1 minute for 100 files)
- [ ] Code review approved by maintainers
- [ ] Works with various git-annex versions
- [ ] No data loss in extensive testing
- [ ] User-friendly error messages
- [ ] Command appears in `datalad --help`

## 📈 Progress Tracking

Update this section as you progress:

- [ ] Experiments run and results documented
- [ ] Community feedback received
- [ ] Core module created (split.py)
- [ ] Basic functionality working
- [ ] Nested subdatasets handled
- [ ] Test suite passing
- [ ] Documentation written
- [ ] Code review requested
- [ ] Merged to main branch

---

**Last Updated**: 2026-01-16
**Status**: Planning Complete - Ready for Experimentation
**Next Action**: Run prototype experiments
