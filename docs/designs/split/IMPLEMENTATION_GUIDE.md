# DataLad Split Command - Detailed Implementation Guide

## Overview

This guide provides step-by-step instructions for implementing the `datalad split` command based on the actual DataLad codebase architecture and patterns.

**Target File**: `datalad/distribution/split.py` (or `datalad/local/split.py`)
**Test File**: `datalad/distribution/tests/test_split.py`

---

## Part 1: File Structure and Imports

### Step 1.1: Create the Module File

Create `datalad/distribution/split.py` with standard header:

```python
# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Split directories from a dataset into subdatasets"""

__docformat__ = 'restructuredtext'
```

### Step 1.2: Add Required Imports

```python
import logging
import os
import subprocess
from pathlib import Path

from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
    resolve_path,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import (
    jobs_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.support.constraints import (
    EnsureChoice,
    EnsureInt,
    EnsureNone,
    EnsureRange,
    EnsureStr,
)
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
    InsufficientArgumentsError,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.utils import (
    ensure_list,
    getpwd,
    Path as PathType,
)

lgr = logging.getLogger('datalad.distribution.split')
```

---

## Part 2: Parameter Definition

### Step 2.1: Define the Split Class

```python
@build_doc
class Split(Interface):
    """Split directories from a dataset into subdatasets.

    This command extracts one or more directories from a dataset and converts
    them into independent subdatasets using git filter-branch and git-annex
    filter-branch to rewrite history.

    .. warning::
       This operation rewrites git history. It is HIGHLY recommended to create
       a backup before running this command.

    The split operation:
    1. Removes the target directory from the parent's git index
    2. Creates a new repository (clone, worktree, or with special flags)
    3. Filters the repository to contain only the target directory's history
    4. Registers the filtered repository as a subdataset

    For datasets with git-annex, location tracking is preserved so content
    can be retrieved on-demand from the parent dataset.
    """

    return_type = 'list'
    result_xfm = None
    result_filter = None
```

### Step 2.2: Define Parameters Dictionary

```python
    _params_ = dict(
        path=Parameter(
            args=("path",),
            metavar='PATH',
            nargs='+',
            doc="""path(s) to split into subdataset(s). Each path will become
            a separate subdataset at that location. Paths must be directories
            within the dataset and cannot belong to existing subdatasets.""",
            constraints=EnsureStr()),

        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='DATASET',
            doc="""dataset to split. If no dataset is given, an attempt is made
            to identify the dataset based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),

        clone_mode=Parameter(
            args=("--clone-mode",),
            metavar='MODE',
            doc="""strategy for creating the subdataset repository. 'clone'
            creates an independent repository (default), 'worktree' creates a
            git worktree sharing both git objects and annex objects (most
            efficient for local reorganization), 'reckless-ephemeral' creates
            a repository with symlinked annex (temporary only).""",
            constraints=EnsureChoice('clone', 'worktree', 'reckless-ephemeral')),

        content=Parameter(
            args=("--content",),
            metavar='MODE',
            doc="""how to handle locally-present annexed content. 'auto'
            (default) uses 'none' for all modes, 'copy' duplicates content to
            subdataset, 'move' transfers content from parent to subdataset,
            'none' leaves content retrievable on-demand. Note: 'copy' and
            'move' only work with --clone-mode=clone.""",
            constraints=EnsureChoice('auto', 'copy', 'move', 'none')),

        worktree_branch_prefix=Parameter(
            args=("--worktree-branch-prefix",),
            metavar='PREFIX',
            doc="""prefix for worktree branch names (default: 'split/'). Only
            used with --clone-mode=worktree. Branch will be created as
            PREFIX + path (e.g., 'split/data/subjects/subject01').""",
            constraints=EnsureStr() | EnsureNone()),

        worktree_use_namespace=Parameter(
            args=("--worktree-use-namespace",),
            action='store_true',
            doc="""use git namespaces instead of branch prefix for worktree
            branches. Only used with --clone-mode=worktree. When enabled,
            creates branches in refs/namespaces/<namespace>/refs/heads/<path>
            for complete isolation from main branch namespace. Namespace
            defaults to the value of --worktree-branch-prefix (without
            trailing slash)."""),

        check=Parameter(
            args=("--check",),
            metavar='LEVEL',
            doc="""post-split verification level. 'full' (default) verifies
            git-annex integrity and content accessibility, 'annex' only runs
            annex fsck, 'tree' only checks directory tree structure, 'none'
            skips all verification (faster but not recommended).""",
            constraints=EnsureChoice('full', 'annex', 'tree', 'none')),

        propagate_annex_config=Parameter(
            args=("--propagate-annex-config",),
            metavar='CONFIG',
            doc="""comma-separated list of git config annex.* settings to
            propagate from parent to subdatasets (e.g.,
            'annex.addunlocked,annex.backend'). Use 'none' to skip propagation,
            or 'all' to copy all annex.* settings.""",
            constraints=EnsureStr() | EnsureNone()),

        preserve_branch_name=Parameter(
            args=("--preserve-branch-name",),
            action='store_true',
            doc="""ensure subdataset has same branch checked out as parent had
            for that path. Default: True."""),

        force=Parameter(
            args=("-f", "--force"),
            action='store_true',
            doc="""force split without confirmation prompt. Use with caution as
            this operation rewrites history."""),

        dry_run=Parameter(
            args=("--dry-run",),
            action='store_true',
            doc="""preview what would be done without actually splitting."""),

        jobs=jobs_opt,
    )
```

### Step 2.3: Add Usage Examples

```python
    _examples_ = [
        dict(
            text="Split data/subject01 into a subdataset",
            code_py="split('data/subject01')",
            code_cmd="datalad split data/subject01"),

        dict(
            text="Split multiple directories with shell glob",
            code_py="split(['data', 'data/subject01', 'data/subject02'])",
            code_cmd="datalad split data data/subject*"),

        dict(
            text="Use worktree mode for efficient local reorganization",
            code_py="split('data/subjects/subject01', clone_mode='worktree')",
            code_cmd="datalad split --clone-mode=worktree data/subjects/subject01"),

        dict(
            text="Copy content to subdataset (makes it independent)",
            code_py="split('data/raw', clone_mode='clone', content='copy')",
            code_cmd="datalad split --clone-mode=clone --content=copy data/raw"),

        dict(
            text="Preview without actually performing the split",
            code_py="split('data/analysis', dry_run=True)",
            code_cmd="datalad split --dry-run data/analysis"),
    ]
```

---

## Part 3: Implementation Structure

### Step 3.1: Define the Main Entry Point

```python
    @staticmethod
    @datasetmethod(name='split')
    @eval_results
    def __call__(
            path,
            *,
            dataset=None,
            clone_mode='clone',
            content='auto',
            worktree_branch_prefix='split/',
            worktree_use_namespace=False,
            check='full',
            propagate_annex_config=None,
            preserve_branch_name=True,
            force=False,
            dry_run=False,
            jobs='auto'):

        # Convert paths to list
        paths = ensure_list(path)

        # Get dataset
        ds = require_dataset(
            dataset,
            check_installed=True,
            purpose='split directories into subdatasets')

        # Resolve paths relative to dataset
        resolved_paths = []
        for p in paths:
            resolved = resolve_path(p, dataset, ds)
            if isinstance(resolved, list):
                resolved_paths.extend(resolved)
            else:
                resolved_paths.append(resolved)

        # Reference dataset path for results
        refds_path = ds.path

        # Validate parameters early
        _validate_split_params(
            clone_mode=clone_mode,
            content=content,
            paths=resolved_paths,
            ds=ds)

        # Display safety warning unless forced
        if not force and not dry_run:
            _display_safety_warning(ds=ds, paths=resolved_paths)
            # In real implementation, prompt for confirmation here

        # Perform path validation and discovery
        validated_paths = []
        for target_path in resolved_paths:
            for result in _validate_split_path(
                    ds=ds,
                    path=target_path,
                    refds_path=refds_path):
                if result['status'] != 'ok':
                    yield result
                    continue
                validated_paths.append(target_path)

        # Process splits (with potential bottom-up ordering if nested)
        for target_path in _order_splits_bottomup(validated_paths, ds):
            # Perform the actual split
            for result in _perform_single_split(
                    ds=ds,
                    target_path=target_path,
                    clone_mode=clone_mode,
                    content=content,
                    worktree_branch_prefix=worktree_branch_prefix,
                    propagate_annex_config=propagate_annex_config,
                    preserve_branch_name=preserve_branch_name,
                    dry_run=dry_run,
                    refds_path=refds_path):
                yield result

            # Post-split verification
            if not dry_run and check != 'none':
                for result in _verify_split(
                        ds=ds,
                        target_path=target_path,
                        check_level=check):
                    yield result
```

---

## Part 4: Helper Functions

### Step 4.1: Parameter Validation

```python
def _validate_split_params(clone_mode, content, paths, ds):
    """Validate parameter combinations early."""

    # Validate content mode compatibility
    if content in ('copy', 'move') and clone_mode != 'clone':
        raise ValueError(
            f"Content mode '{content}' only works with --clone-mode=clone")

    # Check if dataset has annex when using annex-specific features
    if content in ('copy', 'move'):
        if not hasattr(ds.repo, 'call_annex'):
            lgr.warning(
                "Content mode '%s' specified but dataset has no git-annex",
                content)

    # Ensure paths is not empty
    if not paths:
        raise InsufficientArgumentsError(
            "Please provide at least one path to split")
```

### Step 4.2: Path Validation

```python
def _validate_split_path(ds, path, refds_path):
    """Validate that a path can be split.

    Checks:
    1. Path exists and is a directory
    2. Path is within dataset
    3. Path doesn't belong to a subdataset
    4. Path is tracked in git
    5. Not trying to split root of dataset
    """
    path_obj = Path(path)
    ds_path = Path(ds.path)

    # Check 1: Exists and is directory
    if not path_obj.exists():
        yield get_status_dict(
            'split',
            status='impossible',
            message=f"Path does not exist: {path}",
            path=str(path),
            refds=refds_path,
            logger=lgr)
        return

    if not path_obj.is_dir():
        yield get_status_dict(
            'split',
            status='impossible',
            message=f"Path is not a directory: {path}",
            path=str(path),
            refds=refds_path,
            logger=lgr)
        return

    # Check 2: Within dataset
    try:
        rel_path = path_obj.relative_to(ds_path)
    except ValueError:
        yield get_status_dict(
            'split',
            status='impossible',
            message=f"Path is not within dataset: {path}",
            path=str(path),
            refds=refds_path,
            logger=lgr)
        return

    # Check 3: Not trying to split dataset root
    if path_obj == ds_path:
        yield get_status_dict(
            'split',
            status='impossible',
            message="Cannot split dataset root directory",
            path=str(path),
            refds=refds_path,
            logger=lgr)
        return

    # Check 4: Check if path belongs to subdataset
    # Use subdatasets command to check
    from datalad.local.subdatasets import Subdatasets
    subds_results = list(Subdatasets.__call__(
        dataset=ds,
        state='any',
        result_renderer='disabled'))

    for subds in subds_results:
        if subds.get('status') != 'ok':
            continue
        subds_path = Path(subds['path'])
        # Check if target path is subdataset or inside one
        if path_obj == subds_path or subds_path in path_obj.parents:
            yield get_status_dict(
                'split',
                status='impossible',
                message=(f"Path belongs to subdataset {subds_path}. "
                        "Cannot split subdataset paths."),
                path=str(path),
                refds=refds_path,
                logger=lgr)
            return

    # Check 5: Path is tracked in git
    try:
        # Check if path has any git-tracked files
        result = ds.repo.call_git(
            ['ls-files', str(rel_path)],
            read_only=True)
        if not result.strip():
            yield get_status_dict(
                'split',
                status='impossible',
                message=f"Path contains no git-tracked files: {path}",
                path=str(path),
                refds=refds_path,
                logger=lgr)
            return
    except CommandError as e:
        ce = CapturedException(e)
        yield get_status_dict(
            'split',
            status='error',
            message=('Failed to check git status: %s', ce),
            exception=ce,
            path=str(path),
            refds=refds_path,
            logger=lgr)
        return

    # All validations passed
    yield get_status_dict(
        'split',
        status='ok',
        message='Path validated for split',
        path=str(path),
        refds=refds_path,
        logger=lgr)
```

### Step 4.3: Split Ordering (Bottom-Up)

```python
def _order_splits_bottomup(paths, ds):
    """Order paths for splitting from deepest to shallowest.

    This ensures nested splits work correctly - we split children before
    parents.
    """
    path_objs = [Path(p) for p in paths]

    # Sort by depth (deepest first)
    sorted_paths = sorted(
        path_objs,
        key=lambda p: len(p.parts),
        reverse=True)

    return [str(p) for p in sorted_paths]
```

### Step 4.4: Safety Warning Display

```python
def _display_safety_warning(ds, paths):
    """Display critical safety warning before split."""
    lgr.warning(
        "\n" + "="*70 + "\n"
        "WARNING: DESTRUCTIVE OPERATION\n"
        "="*70 + "\n"
        "This operation will:\n"
        "  1. Rewrite git history using filter-branch\n"
        "  2. Modify .gitmodules and repository structure\n"
        "  3. Cannot be easily undone\n"
        "\n"
        "Affected paths:\n"
        + "\n".join(f"  - {p}" for p in paths) + "\n"
        "\n"
        "STRONGLY RECOMMENDED: Create a backup before proceeding!\n"
        "="*70 + "\n"
    )
```

---

## Part 5: Core Split Implementation

### Step 5.1: Single Split Operation

```python
def _perform_single_split(
        ds,
        target_path,
        clone_mode,
        content,
        worktree_branch_prefix,
        propagate_annex_config,
        preserve_branch_name,
        dry_run,
        refds_path):
    """Perform split operation on a single path."""

    path_obj = Path(target_path)
    ds_path = Path(ds.path)
    rel_path = path_obj.relative_to(ds_path)

    lgr.info("Splitting %s into subdataset", rel_path)

    if dry_run:
        yield get_status_dict(
            'split',
            status='ok',
            message=f"[DRY-RUN] Would split {rel_path}",
            path=str(target_path),
            type='dataset',
            refds=refds_path,
            logger=lgr)
        return

    try:
        # Step 1: Remove from git index
        lgr.debug("Removing %s from git index", rel_path)
        ds.repo.call_git(['rm', '-r', '--cached', f'{rel_path}/'])

        # Step 2: Physically remove directory
        lgr.debug("Removing %s physically", rel_path)
        import shutil
        shutil.rmtree(str(path_obj))

        # Step 3: Create subdataset based on clone_mode
        if clone_mode == 'clone':
            _create_via_clone(
                ds=ds,
                target_path=target_path,
                rel_path=rel_path)

        elif clone_mode == 'worktree':
            _create_via_worktree(
                ds=ds,
                target_path=target_path,
                rel_path=rel_path,
                prefix=worktree_branch_prefix,
                use_namespace=worktree_use_namespace)

        elif clone_mode == 'reckless-ephemeral':
            _create_via_reckless_ephemeral(
                ds=ds,
                target_path=target_path,
                rel_path=rel_path)

        # Step 4: Filter the repository
        _filter_subdataset(
            subdataset_path=target_path,
            filter_path=str(rel_path),
            parent_path=ds.path)

        # Step 5: Handle content based on mode
        if content != 'none' and content != 'auto':
            _handle_content(
                parent_ds=ds,
                subdataset_path=target_path,
                mode=content)

        # Step 6: Propagate annex config if requested
        if propagate_annex_config:
            _propagate_annex_config(
                parent_ds=ds,
                subdataset_path=target_path,
                config_spec=propagate_annex_config)

        # Step 7: Register as submodule (if not worktree)
        if clone_mode != 'worktree':
            _register_as_submodule(
                parent_ds=ds,
                subdataset_path=target_path,
                rel_path=rel_path)

        # Step 8: Commit the changes
        commit_msg = (
            f"Split {rel_path}/ into subdataset\n\n"
            f"Clone mode: {clone_mode}\n"
            f"Content mode: {content}\n\n"
            "🤖 Generated with Claude Code\n\n"
            "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
        )
        ds.repo.call_git(['commit', '-m', commit_msg])

        yield get_status_dict(
            'split',
            status='ok',
            message=f"Successfully split {rel_path} into subdataset",
            path=str(target_path),
            type='dataset',
            refds=refds_path,
            logger=lgr)

    except Exception as e:
        ce = CapturedException(e)
        yield get_status_dict(
            'split',
            status='error',
            message=('Split failed: %s', ce),
            exception=ce,
            path=str(target_path),
            refds=refds_path,
            logger=lgr)
```

### Step 5.2: Clone Mode Implementation

```python
def _create_via_clone(ds, target_path, rel_path):
    """Create subdataset via git clone."""
    lgr.debug("Creating subdataset via clone")

    # Clone with file protocol
    ds.repo.call_git([
        '-c', 'protocol.file.allow=always',
        'clone', '.', str(rel_path)
    ])
```

### Step 5.3: Worktree Mode Implementation

```python
def _create_via_worktree(ds, target_path, rel_path, prefix, use_namespace=False):
    """Create subdataset via git worktree.

    Args:
        ds: Parent dataset
        target_path: Absolute path to target
        rel_path: Relative path within dataset
        prefix: Branch prefix (default: 'split/')
        use_namespace: If True, use git namespaces for complete isolation
    """
    lgr.debug("Creating subdataset via worktree (namespace=%s)", use_namespace)

    if use_namespace:
        # Approach B: Use git namespaces for complete isolation
        namespace = prefix.rstrip('/')  # Remove trailing slash
        branch_path = str(rel_path)

        lgr.debug("Creating namespaced branch: %s in namespace %s",
                  branch_path, namespace)

        # Create branch in namespace
        env = os.environ.copy()
        env['GIT_NAMESPACE'] = namespace
        ds.repo.call_git(['branch', branch_path, 'HEAD'], env=env)

        # Worktree ref for namespaced branch
        worktree_ref = f"refs/namespaces/{namespace}/refs/heads/{branch_path}"
    else:
        # Approach A: Simple hierarchical prefix (default)
        branch_name = f"{prefix}{rel_path}"
        lgr.debug("Creating prefixed branch: %s", branch_name)
        ds.repo.call_git(['branch', branch_name, 'HEAD'])

        # Worktree ref is just the branch name
        worktree_ref = branch_name

    # Create worktree (same for both approaches)
    lgr.debug("Creating worktree at %s with ref %s", rel_path, worktree_ref)
    ds.repo.call_git([
        'worktree', 'add',
        str(rel_path),
        worktree_ref
    ])
```

### Step 5.4: Reckless Ephemeral Mode

```python
def _create_via_reckless_ephemeral(ds, target_path, rel_path):
    """Create subdataset with reckless-ephemeral mode."""
    lgr.debug("Creating subdataset via reckless-ephemeral")

    # First clone normally
    _create_via_clone(ds, target_path, rel_path)

    # Then symlink the annex objects directory
    subdataset = Dataset(target_path)
    if hasattr(subdataset.repo, 'call_annex'):
        annex_objects = Path(target_path) / '.git' / 'annex' / 'objects'
        parent_annex = Path(ds.path) / '.git' / 'annex' / 'objects'

        if annex_objects.exists():
            import shutil
            shutil.rmtree(annex_objects)

        annex_objects.symlink_to(parent_annex)
        lgr.debug("Symlinked annex objects to parent")
```

### Step 5.5: Filter Subdataset

```python
def _filter_subdataset(subdataset_path, filter_path, parent_path):
    """Apply git-annex filter-branch and git filter-branch."""
    lgr.debug("Filtering subdataset %s", subdataset_path)

    subdataset = Dataset(subdataset_path)
    repo = subdataset.repo

    # Check if it's an annex repo
    is_annex = hasattr(repo, 'call_annex')

    if is_annex:
        # Step 1: git-annex filter-branch
        lgr.debug("Running git-annex filter-branch for %s", filter_path)
        repo.call_annex([
            'filter-branch',
            filter_path,
            '--include-all-key-information',
            '--include-all-repo-config'
        ])

    # Step 2: git filter-branch
    lgr.debug("Running git filter-branch for %s", filter_path)

    # Set environment variable to squelch warning
    env = os.environ.copy()
    env['FILTER_BRANCH_SQUELCH_WARNING'] = '1'

    repo.call_git(
        ['filter-branch', '--subdirectory-filter', filter_path,
         '--prune-empty', 'HEAD'],
        env=env)

    # Step 3: Set remote origin to parent
    lgr.debug("Setting origin to %s", parent_path)
    repo.call_git(['remote', 'set-url', 'origin', parent_path])

    # Step 4: git annex forget (if annex)
    if is_annex:
        lgr.debug("Running git annex forget")
        repo.call_annex(['forget', '--force', '--drop-dead'])
```

### Step 5.6: Content Handling

```python
def _handle_content(parent_ds, subdataset_path, mode):
    """Handle annexed content based on mode."""
    lgr.debug("Handling content with mode: %s", mode)

    subdataset = Dataset(subdataset_path)

    if not hasattr(subdataset.repo, 'call_annex'):
        lgr.debug("Not an annex repo, skipping content handling")
        return

    if mode == 'copy':
        # Get all annexed files in subdataset
        lgr.info("Copying content to subdataset")
        from datalad.core.distributed.clone import _postclone
        # Use datalad get to retrieve content
        annexed_files = subdataset.repo.call_annex(
            ['find', '--include', '*'],
            read_only=True).splitlines()

        if annexed_files:
            # Get each file from parent
            for afile in annexed_files:
                try:
                    subdataset.repo.call_annex(['get', afile])
                except CommandError as e:
                    lgr.warning("Failed to get %s: %s", afile, e)

    elif mode == 'move':
        # Move content from parent to subdataset
        lgr.info("Moving content to subdataset")
        annexed_files = subdataset.repo.call_annex(
            ['find', '--include', '*'],
            read_only=True).splitlines()

        if annexed_files:
            for afile in annexed_files:
                try:
                    # First get in subdataset
                    subdataset.repo.call_annex(['get', afile])
                    # Then drop from parent if present
                    key = subdataset.repo.call_annex(
                        ['lookupkey', afile],
                        read_only=True).strip()
                    if key:
                        parent_ds.repo.call_annex(
                            ['drop', '--key', key, '--force'])
                except CommandError as e:
                    lgr.warning("Failed to move %s: %s", afile, e)
```

### Step 5.7: Config Propagation

```python
def _propagate_annex_config(parent_ds, subdataset_path, config_spec):
    """Propagate annex config from parent to subdataset."""
    lgr.debug("Propagating annex config: %s", config_spec)

    subdataset = Dataset(subdataset_path)

    if config_spec == 'none':
        return

    # Get annex config from parent
    parent_config = parent_ds.repo.call_git(
        ['config', '--get-regexp', '^annex\\.'],
        read_only=True).splitlines()

    if config_spec == 'all':
        configs_to_copy = parent_config
    else:
        # Parse comma-separated list
        requested = [c.strip() for c in config_spec.split(',')]
        configs_to_copy = [
            line for line in parent_config
            if any(line.startswith(f"{req} ") for req in requested)
        ]

    # Apply to subdataset
    for config_line in configs_to_copy:
        key, value = config_line.split(' ', 1)
        lgr.debug("Setting %s = %s", key, value)
        subdataset.repo.call_git(['config', key, value])
```

### Step 5.8: Submodule Registration

```python
def _register_as_submodule(parent_ds, subdataset_path, rel_path):
    """Register filtered repository as submodule."""
    lgr.debug("Registering %s as submodule", rel_path)

    # git submodule add
    parent_ds.repo.call_git([
        'submodule', 'add',
        f'./{rel_path}',
        str(rel_path)
    ])
```

---

## Part 6: Post-Split Verification

```python
def _verify_split(ds, target_path, check_level):
    """Verify split operation completed successfully."""
    lgr.debug("Verifying split with level: %s", check_level)

    subdataset = Dataset(target_path)

    if check_level == 'tree':
        # Just verify directory structure
        yield get_status_dict(
            'verify',
            status='ok',
            message='Tree structure verified',
            path=str(target_path),
            logger=lgr)
        return

    # Check if subdataset is valid
    if not subdataset.is_installed():
        yield get_status_dict(
            'verify',
            status='error',
            message='Subdataset not properly installed',
            path=str(target_path),
            logger=lgr)
        return

    if check_level in ('annex', 'full'):
        # Run git-annex fsck
        if hasattr(subdataset.repo, 'call_annex'):
            try:
                lgr.debug("Running git-annex fsck")
                subdataset.repo.call_annex(['fsck', '--fast'])
                yield get_status_dict(
                    'verify',
                    status='ok',
                    message='Annex integrity verified',
                    path=str(target_path),
                    logger=lgr)
            except CommandError as e:
                ce = CapturedException(e)
                yield get_status_dict(
                    'verify',
                    status='error',
                    message=('Annex fsck failed: %s', ce),
                    exception=ce,
                    path=str(target_path),
                    logger=lgr)

    if check_level == 'full':
        # Verify content accessibility
        if hasattr(subdataset.repo, 'call_annex'):
            try:
                # Check that origin remote is configured
                remotes = subdataset.repo.call_git(
                    ['remote', '-v'],
                    read_only=True)
                if 'origin' not in remotes:
                    yield get_status_dict(
                        'verify',
                        status='error',
                        message='Origin remote not configured',
                        path=str(target_path),
                        logger=lgr)
                else:
                    yield get_status_dict(
                        'verify',
                        status='ok',
                        message='Full verification passed',
                        path=str(target_path),
                        logger=lgr)
            except CommandError as e:
                ce = CapturedException(e)
                yield get_status_dict(
                    'verify',
                    status='error',
                    message=('Verification failed: %s', ce),
                    exception=ce,
                    path=str(target_path),
                    logger=lgr)
```

---

## Part 7: Testing

### Step 7.1: Create Test File

Create `datalad/distribution/tests/test_split.py`:

```python
# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test split command"""

from pathlib import Path

import pytest

from datalad.api import (
    create,
    split,
)
from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_in_results,
    assert_repo_status,
    assert_result_count,
    assert_status,
    with_tempfile,
    with_tree,
)


@pytest.mark.ai_generated
@with_tempfile(mkdir=True)
def test_basic_split(path=None):
    """Test basic split operation."""
    # Create dataset
    ds = create(path)

    # Create directory with content
    (Path(path) / 'data').mkdir()
    (Path(path) / 'data' / 'file.txt').write_text('test')
    ds.save()

    # Split data/ into subdataset
    results = split('data', dataset=path, force=True)
    assert_status('ok', results)

    # Verify subdataset was created
    subdatasets = ds.subdatasets()
    assert_result_count(subdatasets, 1)
    assert subdatasets[0]['path'] == str(Path(path) / 'data')


@pytest.mark.ai_generated
@with_tempfile(mkdir=True)
def test_split_with_annex(path=None):
    """Test split with git-annex content."""
    ds = create(path)

    # Create annexed file
    (Path(path) / 'data').mkdir()
    (Path(path) / 'data' / 'large.dat').write_bytes(b'x' * 1000000)
    ds.save()

    # Split
    results = split('data', dataset=path, force=True)
    assert_status('ok', results)

    # Verify location tracking
    subds = Dataset(Path(path) / 'data')
    # Content should be retrievable from origin
    info = subds.repo.call_annex(['whereis', 'large.dat'])
    assert 'origin' in info


@pytest.mark.ai_generated
@with_tempfile(mkdir=True)
def test_split_worktree_mode(path=None):
    """Test split with worktree mode."""
    ds = create(path)

    (Path(path) / 'data').mkdir()
    (Path(path) / 'data' / 'file.txt').write_text('test')
    ds.save()

    # Split with worktree
    results = split(
        'data',
        dataset=path,
        clone_mode='worktree',
        force=True)
    assert_status('ok', results)

    # Verify it's a worktree
    subds_git = Path(path) / 'data' / '.git'
    assert subds_git.is_file()  # Worktrees have .git file, not directory


@pytest.mark.ai_generated
def test_split_invalid_path():
    """Test split rejects invalid paths."""
    with with_tempfile(mkdir=True) as path:
        ds = create(path)

        # Try to split non-existent path
        results = list(split('nonexistent', dataset=path))
        assert_in_results(results, status='impossible')


@pytest.mark.ai_generated
@with_tempfile(mkdir=True)
def test_split_multiple_paths(path=None):
    """Test splitting multiple paths."""
    ds = create(path)

    # Create multiple directories
    for subdir in ['data1', 'data2', 'data3']:
        (Path(path) / subdir).mkdir()
        (Path(path) / subdir / 'file.txt').write_text(subdir)
    ds.save()

    # Split all at once
    results = split(
        ['data1', 'data2', 'data3'],
        dataset=path,
        force=True)
    assert_result_count(results, 3, status='ok', action='split')

    # Verify all subdatasets
    subdatasets = ds.subdatasets()
    assert_result_count(subdatasets, 3)
```

---

## Part 8: Integration

### Step 8.1: Register Command

Ensure the command is importable from `datalad.api`:

Check/modify `datalad/api.py`:
```python
from datalad.distribution.split import Split
```

### Step 8.2: Command Entry Point

The command will automatically be available as:
- Python API: `datalad.api.split()`
- Dataset method: `ds.split()`
- CLI: `datalad split`

---

## Summary Checklist

- [ ] Create `datalad/distribution/split.py` with proper structure
- [ ] Implement all parameters with constraints
- [ ] Implement `__call__` method with decorators
- [ ] Implement helper functions for validation
- [ ] Implement core split logic (clone/worktree/ephemeral modes)
- [ ] Implement filtering operations
- [ ] Implement content handling
- [ ] Implement verification
- [ ] Create comprehensive tests
- [ ] Test CLI invocation
- [ ] Test Dataset method binding
- [ ] Document in command reference

This implementation guide provides the exact structure and patterns used in DataLad, ensuring the split command integrates seamlessly with the existing codebase.
