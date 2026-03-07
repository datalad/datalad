# DataLad Split Command - Architecture Overview

## Command Flow Diagram

```
User Invocation
│
├─ CLI: datalad split data/subject01
├─ Python API: datalad.api.split('data/subject01')
└─ Dataset Method: ds.split('data/subject01')
          │
          ▼
    Split.__call__()  [@eval_results decorator]
          │
          ├─ 1. Parameter Processing
          │   ├─ ensure_list(path)
          │   ├─ require_dataset()
          │   └─ resolve_path()
          │
          ├─ 2. Validation Phase
          │   ├─ _validate_split_params()
          │   │   ├─ Check parameter compatibility
          │   │   └─ Check annex availability
          │   │
          │   ├─ _display_safety_warning()
          │   │   └─ [if not force and not dry_run]
          │   │
          │   └─ _validate_split_path()  [for each path]
          │       ├─ Check path exists and is directory
          │       ├─ Check path is within dataset
          │       ├─ Check not splitting dataset root
          │       ├─ Check path not in subdataset
          │       └─ Check path has git-tracked files
          │
          ├─ 3. Ordering Phase
          │   └─ _order_splits_bottomup()
          │       └─ Sort by depth (deepest first)
          │
          ├─ 4. Split Execution [for each path]
          │   │
          │   └─ _perform_single_split()
          │       │
          │       ├─ Step 1: git rm -r --cached <path>/
          │       │
          │       ├─ Step 2: rm -rf <path>
          │       │
          │       ├─ Step 3: Create subdataset
          │       │   │
          │       │   ├─ clone mode
          │       │   │   └─ _create_via_clone()
          │       │   │       └─ git clone . <path>
          │       │   │
          │       │   ├─ worktree mode
          │       │   │   └─ _create_via_worktree()
          │       │   │       ├─ git branch split/<path>
          │       │   │       └─ git worktree add <path> split/<path>
          │       │   │
          │       │   └─ reckless-ephemeral mode
          │       │       └─ _create_via_reckless_ephemeral()
          │       │           ├─ git clone . <path>
          │       │           └─ ln -s parent/.git/annex/objects
          │       │
          │       ├─ Step 4: Filter repository
          │       │   └─ _filter_subdataset()
          │       │       ├─ git-annex filter-branch <path>
          │       │       │   --include-all-key-information
          │       │       │   --include-all-repo-config
          │       │       ├─ git filter-branch
          │       │       │   --subdirectory-filter <path>
          │       │       │   --prune-empty HEAD
          │       │       ├─ git remote set-url origin <parent>
          │       │       └─ git annex forget --force --drop-dead
          │       │
          │       ├─ Step 5: Handle content
          │       │   └─ _handle_content()
          │       │       ├─ copy mode: datalad get all files
          │       │       ├─ move mode: get + drop from parent
          │       │       └─ none/auto: skip
          │       │
          │       ├─ Step 6: Propagate config
          │       │   └─ _propagate_annex_config()
          │       │       ├─ Get annex.* from parent
          │       │       └─ Set in subdataset
          │       │
          │       ├─ Step 7: Register submodule
          │       │   └─ _register_as_submodule()
          │       │       └─ git submodule add ./<path> <path>
          │       │
          │       └─ Step 8: Commit
          │           └─ git commit -m "Split ..."
          │
          └─ 5. Verification Phase [if check != 'none']
              │
              └─ _verify_split()  [for each split]
                  ├─ tree: Check directory structure
                  ├─ annex: git annex fsck --fast
                  └─ full: annex + check origin remote
                      │
                      └─ yield get_status_dict()
```

## Class Hierarchy

```
Interface (abstract base)
    │
    └─ Split
        │
        ├─ Class Attributes
        │   ├─ _params_: dict of Parameter objects
        │   ├─ _examples_: list of example dicts
        │   ├─ return_type = 'list'
        │   ├─ result_xfm = None
        │   └─ result_filter = None
        │
        └─ Methods
            └─ __call__(path, *, dataset, clone_mode, ...)
                [@staticmethod, @datasetmethod, @eval_results]
```

## Parameter Flow

```
Command Line Arguments
    │
    ▼
Parameter Objects (with Constraints)
    │
    ├─ args: CLI argument spec
    ├─ doc: Documentation
    ├─ constraints: Validation/conversion
    └─ kwargs: argparse options
    │
    ▼
Constraint Validation
    │
    ├─ EnsureStr()
    ├─ EnsureChoice('a', 'b')
    ├─ EnsureDataset()
    └─ Composition: | (OR), & (AND)
    │
    ▼
Validated Parameters → __call__() Arguments
```

## Result Dictionary Flow

```
Operation
    │
    ▼
get_status_dict(
    action='split',
    status='ok',  # or 'error', 'impossible', 'notneeded'
    path='/path/to/item',
    type='dataset',
    message='Description',
    logger=lgr,
    refds='/reference/dataset',
    **kwargs
)
    │
    ▼
yield result_dict
    │
    ▼
@eval_results decorator
    │
    ├─ Collects all yielded results
    ├─ Applies result_filter
    ├─ Applies result_xfm
    ├─ Handles error statuses
    └─ Renders output
    │
    ▼
Return to user (list/generator)
```

## File Structure

```
datalad/
├── api.py                          # Exports: from .distribution.split import Split
│
├── distribution/
│   ├── split.py                    # Main implementation
│   │   ├─ Split(Interface)         # Command class
│   │   ├─ _validate_split_params() # Parameter validation
│   │   ├─ _validate_split_path()   # Path validation
│   │   ├─ _order_splits_bottomup() # Ordering logic
│   │   ├─ _perform_single_split()  # Core split operation
│   │   ├─ _create_via_clone()      # Clone mode
│   │   ├─ _create_via_worktree()   # Worktree mode
│   │   ├─ _create_via_reckless_ephemeral()  # Ephemeral mode
│   │   ├─ _filter_subdataset()     # git/annex filtering
│   │   ├─ _handle_content()        # Content handling
│   │   ├─ _propagate_annex_config() # Config propagation
│   │   ├─ _register_as_submodule() # Submodule registration
│   │   └─ _verify_split()          # Post-split verification
│   │
│   └── tests/
│       └── test_split.py           # Comprehensive tests
│
├── interface/
│   ├── base.py                     # Interface, @build_doc, @eval_results
│   ├── common_opts.py              # Reusable parameters
│   └── results.py                  # get_status_dict()
│
└── support/
    ├── param.py                    # Parameter class
    ├── constraints.py              # Constraint validators
    ├── gitrepo.py                  # GitRepo.call_git()
    └── annexrepo.py                # AnnexRepo.call_annex()
```

## Data Flow Example

### Input
```python
datalad.api.split(
    'data/subjects/subject01',
    dataset='/datasets/study',
    clone_mode='worktree',
    content='auto'
)
```

### Processing
```
1. require_dataset('/datasets/study')
   → Dataset('/datasets/study')

2. resolve_path('data/subjects/subject01', dataset='/datasets/study')
   → Path('/datasets/study/data/subjects/subject01')

3. Validate path:
   ✓ Exists and is directory
   ✓ Within dataset
   ✓ Not in subdataset
   ✓ Has git-tracked files

4. Create worktree:
   git branch split/data/subjects/subject01 HEAD
   git rm -r --cached data/subjects/subject01/
   rm -rf data/subjects/subject01
   git worktree add data/subjects/subject01 split/data/subjects/subject01

5. Filter:
   cd data/subjects/subject01
   git-annex filter-branch data/subjects/subject01 \
       --include-all-key-information \
       --include-all-repo-config
   git filter-branch --subdirectory-filter data/subjects/subject01 HEAD
   git remote set-url origin /datasets/study

6. Commit:
   cd /datasets/study
   git commit -m "Split data/subjects/subject01/ into subdataset"
```

### Output
```python
[
    {
        'action': 'split',
        'status': 'ok',
        'path': '/datasets/study/data/subjects/subject01',
        'type': 'dataset',
        'message': 'Successfully split data/subjects/subject01 into subdataset',
        'refds': '/datasets/study',
    }
]
```

## Key Design Patterns

### 1. Generator Pattern
```python
@eval_results
def __call__(...):
    # Yield results as they're produced
    for path in paths:
        # Do work
        yield get_status_dict(...)
```

**Why**: Allows streaming results, better error handling, progress reporting

### 2. Decorator Stacking
```python
@staticmethod
@datasetmethod(name='split')  # Binds to Dataset class
@eval_results                 # Handles result processing
def __call__(...):
```

**Why**: Separation of concerns - each decorator adds one responsibility

### 3. Result Dictionary
```python
get_status_dict(
    'split',
    status='ok',
    path=target,
    ds=dataset,  # Automatically sets path and type
    logger=lgr,   # Automatic logging
)
```

**Why**: Standardized output format, automatic logging, structured data

### 4. Early Validation
```python
def __call__(...):
    # Validate parameters immediately
    _validate_split_params(...)

    # Validate each path before processing
    for path in paths:
        for result in _validate_split_path(path):
            if result['status'] != 'ok':
                yield result
                continue
```

**Why**: Fail fast, clear error messages, avoid partial operations

### 5. Exception Capture
```python
try:
    operation()
except CommandError as e:
    ce = CapturedException(e)
    yield get_status_dict(
        'split',
        status='error',
        message=('Failed: %s', ce),
        exception=ce,
        logger=lgr,
    )
```

**Why**: Convert exceptions to results, maintain generator flow

## Integration Points

### 1. Command Registration
- Import in `datalad/api.py`: `from .distribution.split import Split`
- Automatic CLI registration via `__call__` method name
- Automatic dataset method binding via `@datasetmethod(name='split')`

### 2. Result Rendering
- CLI: Uses `result_renderer` (default or custom)
- Python: Returns list/generator of result dicts
- Logging: Automatic via `logger` parameter in results

### 3. Testing
- Use pytest decorators: `@with_tempfile`, `@with_tree`
- Use assertion helpers: `assert_status()`, `assert_result_count()`
- Mark AI-generated tests: `@pytest.mark.ai_generated`

## Performance Considerations

### Storage Impact by Mode

| Mode | Parent .git | Subdataset .git | Annex | Total Overhead |
|------|-------------|-----------------|-------|----------------|
| clone | ~5.3M | ~5.3M | Separate (~10M total) | ~10M |
| worktree | ~5.3M | 4KB | Shared | 4KB |
| reckless-ephemeral | ~5.3M | ~5.3M | Symlinked | ~5.3M |

### Optimization Strategies

1. **Worktree for local splits**: Minimal overhead, maximum sharing
2. **Batch operations**: Process multiple paths in single commit
3. **Lazy verification**: Only run expensive checks when needed
4. **Bottom-up ordering**: Prevents redundant work on nested paths

## Error Handling Strategy

### Levels of Error Handling

1. **Parameter validation**: Raise exceptions early
   ```python
   if invalid:
       raise ValueError("Invalid parameter")
   ```

2. **Path validation**: Yield 'impossible' status
   ```python
   yield get_status_dict('split', status='impossible', message="...")
   ```

3. **Operation errors**: Yield 'error' status with exception
   ```python
   try:
       operation()
   except Exception as e:
       yield get_status_dict('split', status='error', exception=CapturedException(e))
   ```

4. **Partial failures**: Continue processing other paths
   ```python
   for path in paths:
       try:
           yield from process(path)
       except:
           # Error yielded, continue with next path
           continue
   ```

## Testing Strategy

### Test Coverage Areas

1. **Parameter validation**
   - Valid combinations
   - Invalid combinations
   - Constraint enforcement

2. **Path validation**
   - Existing paths
   - Non-existent paths
   - Paths in subdatasets
   - Dataset root

3. **Core functionality**
   - Basic split
   - With annex
   - Multiple paths
   - Nested paths

4. **Modes**
   - Clone mode
   - Worktree mode
   - Reckless-ephemeral mode

5. **Content handling**
   - Copy mode
   - Move mode
   - None mode

6. **Edge cases**
   - Empty directories
   - No git-annex
   - Already split paths
   - Conflicting paths

## Summary

The split command follows DataLad's established patterns:
- **Interface-based** architecture with decorators
- **Parameter-driven** with constraint validation
- **Generator-based** execution with result dictionaries
- **Repository manipulation** via GitRepo/AnnexRepo APIs
- **Comprehensive testing** with standard utilities

This architecture ensures:
- ✅ Consistent user experience across commands
- ✅ Proper error handling and reporting
- ✅ Testability and maintainability
- ✅ Integration with existing DataLad ecosystem
