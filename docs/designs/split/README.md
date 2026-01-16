# DataLad Split Command - Design Documentation

This directory contains the complete design documentation and prototype experiments for implementing a `datalad split` command.

## Quick Navigation

**Start here**: [`QUICK_START.md`](QUICK_START.md) - Quick overview and next steps

**Main documents**:
- [`SPLIT_COMMAND_SUMMARY.md`](SPLIT_COMMAND_SUMMARY.md) - Complete project overview
- [`SPLIT_IMPLEMENTATION_PLAN.md`](SPLIT_IMPLEMENTATION_PLAN.md) - Detailed technical implementation plan
- [`NEXT_STEPS.md`](NEXT_STEPS.md) - Immediate actions and guidance

**Experiments**: [`experiments/`](experiments/) - Prototype validation scripts

## Purpose

Implements a command to split DataLad dataset directories into independent subdatasets while:
- Preserving git history through filtering
- Cleaning up git-annex metadata to avoid bloat
- Handling nested subdatasets correctly via bottom-up traversal
- Maintaining file availability information

## Based On

- [GitHub Issue #3554](https://github.com/datalad/datalad/issues/3554)
- Community discussion and technical proposals

## Key Innovation

**Bottom-up traversal**: Processes nested subdatasets from leaves to root, ensuring proper subdataset preservation and registration during splits.

## Command Example

```bash
# Split multiple nested directories with shell glob (makes data/, data/subject*/ all subdatasets)
datalad split data data/subject*
```

## Next Steps

1. Read [`QUICK_START.md`](QUICK_START.md)
2. Run experiments in [`experiments/`](experiments/)
3. Follow implementation plan in [`SPLIT_IMPLEMENTATION_PLAN.md`](SPLIT_IMPLEMENTATION_PLAN.md)

## Status

**Planning Complete** - Ready for prototype validation via experiments
