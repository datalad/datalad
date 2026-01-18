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

import logging
import os
import shutil
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
from datalad.interface.common_opts import jobs_opt
from datalad.interface.results import get_status_dict
from datalad.log import log_progress
from datalad.support.constraints import (
    EnsureBool,
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
    InsufficientArgumentsError,
)
from datalad.support.param import Parameter
from datalad.utils import (
    ensure_list,
    getpwd,
)

lgr = logging.getLogger('datalad.distribution.split')


@build_doc
class Split(Interface):
    """Split directories from a dataset into subdatasets.

    This command extracts one or more directories from a dataset and converts
    them into independent subdatasets using git filter-branch and git-annex
    filter-branch to rewrite history.

    .. warning::
       This operation modifies git history. It is HIGHLY recommended to create
       a backup before running this command.

    .. note::
       **IMPORTANT: UNDERSTANDING HISTORY MODES:**

       The `--mode` parameter controls how parent history is affected:

       - **split-top (default)**: SAFEST - subdatasets have filtered history,
         parent history is NOT rewritten. A new commit is added to parent
         marking the split. Original commits unchanged, split appears at a
         single point in time.

       - **truncate-top**: Discards ALL parent history, creating orphan commit.
         Subdatasets have filtered history. Use for fresh start when history
         is not valuable. DESTRUCTIVE - requires re-cloning.

       - **truncate-top-graft**: Like truncate-top but preserves full history
         in separate branch with git replace for transparent access when needed.
         Best of both worlds - minimal working tree, full history available.

       - **rewrite-parent**: Rewrites ENTIRE parent history to retroactively
         include subdatasets with proper gitlinks throughout. Makes it appear
         as though subdatasets existed from the beginning. CHANGES ALL COMMIT
         SHAs - requires re-cloning all copies. Most destructive but
         historically accurate.

       See `--mode` parameter documentation for details on each mode.

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

    _params_ = dict(
        path=Parameter(
            args=("path",),
            metavar='PATH',
            nargs='+',
            doc="""path(s) to split into subdataset(s). Each path will become
            a separate subdataset at that location. Paths must be directories
            within the dataset and cannot belong to existing subdatasets.""",
            constraints=EnsureStr() | EnsureNone()),

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

        mode=Parameter(
            args=("--mode",),
            metavar='MODE',
            doc="""split operation mode controlling how parent history is handled.
            'split-top' (default) creates subdatasets with filtered history and
            adds a new commit to parent marking the split - parent history is
            NOT rewritten. 'truncate-top' creates an orphan commit with no
            history, discarding all prior commits (use for fresh start).
            'truncate-top-graft' does truncate-top but preserves full history
            in {branch}-split-full branch and uses git replace to graft it,
            allowing access to full history when needed. 'rewrite-parent'
            rewrites entire parent history to make subdatasets appear as if
            they existed from the beginning with proper gitlinks throughout
            history (WARNING: changes all parent commit SHAs, requires
            re-cloning all copies). Supports both top-level (e.g., 'data/')
            and nested paths (e.g., 'data/logs/').""",
            constraints=EnsureChoice('split-top', 'truncate-top',
                                     'truncate-top-graft', 'rewrite-parent')),

        cleanup=Parameter(
            args=("--cleanup",),
            metavar='LEVEL',
            doc="""cleanup operations to reclaim disk space after split. 'none'
            (default) performs no cleanup - safest option. 'reflog' expires
            reflog entries pointing to old commits. 'gc' runs git gc to remove
            unreferenced objects from .git/objects. 'annex' runs git annex
            unused and git annex drop unused to reclaim annex object storage.
            'all' performs all cleanup operations (reflog + gc + annex). Only
            useful with --mode=truncate-top, truncate-top-graft, or
            rewrite-parent where history is modified.""",
            constraints=EnsureChoice('none', 'reflog', 'gc', 'annex', 'all')),

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

        dict(
            text="Use namespaces for complete branch isolation",
            code_py="split('data/subjects/subject01', clone_mode='worktree', worktree_use_namespace=True)",
            code_cmd="datalad split --clone-mode=worktree --worktree-use-namespace data/subjects/subject01"),

        dict(
            text="Truncate history for fresh start with minimal storage",
            code_py="split('data', mode='truncate-top', cleanup='all', force=True)",
            code_cmd="datalad split --mode=truncate-top --cleanup=all --force data"),

        dict(
            text="Truncate with grafted full history access",
            code_py="split('data', mode='truncate-top-graft', cleanup='gc', force=True)",
            code_cmd="datalad split --mode=truncate-top-graft --cleanup=gc --force data"),

        dict(
            text="Rewrite entire parent history to retroactively include subdataset (DESTRUCTIVE)",
            code_py="split('data', mode='rewrite-parent', force=True)",
            code_cmd="datalad split --mode=rewrite-parent --force data"),
    ]

    @staticmethod
    @datasetmethod(name='split')
    @eval_results
    def __call__(
            path=None,
            *,
            dataset=None,
            clone_mode='clone',
            content='auto',
            worktree_branch_prefix='split/',
            worktree_use_namespace=False,
            mode='split-top',
            cleanup='none',
            check='full',
            propagate_annex_config=None,
            preserve_branch_name=True,
            force=False,
            dry_run=False,
            jobs='auto'):

        # Validate that path was provided
        if not path:
            raise InsufficientArgumentsError(
                "requires at least one path to split"
            )

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
            resolved = resolve_path(p, ds)
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
            # Yield warning as a proper DataLad result instead of printing
            warning_lines = [
                "",
                "=" * 70,
                "WARNING: HISTORY-MODIFYING OPERATION",
                "=" * 70,
                f"Mode: {mode}",
                "",
            ]

            # Mode-specific warnings
            if mode == 'split-top':
                warning_lines.extend([
                    "This operation will:",
                    "  1. Create subdataset with filtered history (safe)",
                    "  2. Add new commit to parent marking the split",
                    "  3. Parent history remains unchanged",
                    "",
                    "Impact: LOW - safest mode, easily reversible"
                ])
            elif mode == 'truncate-top':
                warning_lines.extend([
                    "This operation will:",
                    "  1. DELETE ALL PARENT HISTORY (creates orphan commit)",
                    "  2. Create subdataset with filtered history",
                    "  3. Requires re-cloning all repository copies",
                    "",
                    "Impact: HIGH - destroys history, cannot be undone"
                ])
            elif mode == 'truncate-top-graft':
                warning_lines.extend([
                    "This operation will:",
                    "  1. Create orphan commit (working tree only)",
                    "  2. Preserve full history in separate branch",
                    "  3. Use git replace for transparent access",
                    "",
                    "Impact: MEDIUM - history preserved but requires re-cloning"
                ])
            elif mode == 'rewrite-parent':
                warning_lines.extend([
                    "This operation will:",
                    "  1. REWRITE ENTIRE PARENT HISTORY (all commits get new SHAs)",
                    "  2. Retroactively add subdataset gitlinks throughout history",
                    "  3. Requires re-cloning ALL repository copies",
                    "",
                    "Impact: HIGHEST - changes every commit, cannot be undone"
                ])

            warning_lines.extend([
                "",
                "Affected paths:",
            ])
            warning_lines.extend(f"  - {p}" for p in resolved_paths)
            warning_lines.extend([
                "",
                "STRONGLY RECOMMENDED: Create a backup before proceeding!",
                "Use --force to proceed without this prompt.",
                "=" * 70,
                ""
            ])

            yield get_status_dict(
                'split',
                status='note',
                message="\n".join(warning_lines),
                refds=refds_path,
                logger=lgr)

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

        # Process splits (with bottom-up ordering if nested)
        for target_path in _order_splits_bottomup(validated_paths, ds):
            # Perform the actual split
            for result in _perform_single_split(
                    ds=ds,
                    target_path=target_path,
                    clone_mode=clone_mode,
                    content=content,
                    worktree_branch_prefix=worktree_branch_prefix,
                    worktree_use_namespace=worktree_use_namespace,
                    mode=mode,
                    cleanup=cleanup,
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
    try:
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
    except Exception as e:
        # If subdatasets check fails, log warning but continue
        lgr.debug("Could not check for subdatasets: %s", e)

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


def _perform_single_split(
        ds,
        target_path,
        clone_mode,
        content,
        worktree_branch_prefix,
        worktree_use_namespace,
        mode,
        cleanup,
        propagate_annex_config,
        preserve_branch_name,
        dry_run,
        refds_path):
    """Perform split operation on a single path.

    Parameters
    ----------
    mode : str
        Split mode: 'split-top', 'truncate-top', 'truncate-top-graft', or 'rewrite-parent'
    cleanup : str
        Cleanup level: 'none', 'reflog', 'gc', 'annex', or 'all'
    """

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

        # Step 4.5: Apply mode-specific transformations
        if mode == 'truncate-top':
            lgr.debug("Applying truncate-top mode to %s", rel_path)
            _apply_truncate_top(target_path, create_graft_branch=False)

        elif mode == 'truncate-top-graft':
            lgr.debug("Applying truncate-top-graft mode to %s", rel_path)
            _apply_truncate_top(target_path, create_graft_branch=True)

        elif mode == 'rewrite-parent':
            lgr.debug("Applying rewrite-parent mode to %s", rel_path)
            # Rewrite parent history to include gitlinks from the beginning
            # Uses manual git commit-tree approach (validated in Experiment 17)
            _apply_rewrite_parent_simple(
                parent_ds=ds,
                subdataset_path=target_path,
                rel_path=rel_path)

        # elif mode == 'split-top': (default - no special handling needed)

        # Step 4.6: Apply cleanup if requested
        if cleanup != 'none' and mode in ('truncate-top', 'truncate-top-graft', 'rewrite-parent'):
            lgr.debug("Applying cleanup level: %s", cleanup)
            _apply_cleanup(target_path, cleanup)

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

        # Step 7: Register as submodule and commit (unless rewrite-parent)
        # For rewrite-parent mode, history is already rewritten with gitlinks
        # No need to register or create a new commit
        if mode != 'rewrite-parent':
            # Register as submodule (if not worktree)
            if clone_mode != 'worktree':
                _register_as_submodule(
                    parent_ds=ds,
                    subdataset_path=target_path,
                    rel_path=rel_path)

            # Step 8: Commit the changes
            commit_msg = (
                f"Split {rel_path}/ into subdataset\n\n"
                f"Split mode: {mode}\n"
                f"Clone mode: {clone_mode}\n"
                f"Content mode: {content}\n"
                f"Cleanup: {cleanup}\n\n"
                "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n\n"
                "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
            )
            ds.repo.call_git(['commit', '-m', commit_msg])
        else:
            # For rewrite-parent mode, history has already been rewritten
            # The _apply_rewrite_parent_simple() function handles everything
            pass

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


def _create_via_clone(ds, target_path, rel_path):
    """Create subdataset via git clone."""
    lgr.debug("Creating subdataset via clone")

    # Clone with file protocol
    ds.repo.call_git([
        '-c', 'protocol.file.allow=always',
        'clone', '.', str(rel_path)
    ])


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
            shutil.rmtree(annex_objects)

        annex_objects.symlink_to(parent_annex)
        lgr.debug("Symlinked annex objects to parent")


def _filter_subdataset(subdataset_path, filter_path, parent_path):
    """Apply git-annex filter-branch and git filter-branch."""
    lgr.debug("Filtering subdataset %s", subdataset_path)

    subdataset = Dataset(subdataset_path)
    repo = subdataset.repo

    # Check if it's an annex repo
    is_annex = hasattr(repo, 'call_annex')

    if is_annex:
        # Step 0: Initialize git-annex to ensure git-annex branch exists locally
        # Without this, filter-branch might not work correctly
        lgr.debug("Initializing git-annex in subdataset")
        try:
            repo.call_annex(['init', f'split-{Path(filter_path).name}'])
        except CommandError as e:
            # Init might fail if already initialized, which is okay
            lgr.debug("git-annex init returned error (might be already initialized): %s", e)

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

    # Check if origin remote exists
    try:
        remotes = repo.call_git(['remote'])
        has_origin = 'origin' in remotes.strip().split('\n')
    except Exception:
        has_origin = False

    if has_origin:
        repo.call_git(['remote', 'set-url', 'origin', parent_path])
    else:
        repo.call_git(['remote', 'add', 'origin', parent_path])

    # Step 4: git annex forget (if annex)
    if is_annex:
        lgr.debug("Running git annex forget")
        repo.call_annex(['forget', '--force', '--drop-dead'])


def _apply_truncate_top(subdataset_path, create_graft_branch=False):
    """Truncate history to single commit (truncate-top mode).

    Removes all commit history, keeping only the final tree state.
    Optionally creates a -split-full branch with git replace for full history.

    Parameters
    ----------
    subdataset_path : str
        Path to subdataset
    create_graft_branch : bool
        If True, create {branch}-split-full branch and git replace graft
    """
    lgr.debug("Applying truncate-top to %s (graft=%s)",
              subdataset_path, create_graft_branch)

    subdataset = Dataset(subdataset_path)
    repo = subdataset.repo

    # Get current branch name
    current_branch = repo.call_git(['branch', '--show-current']).strip()
    if not current_branch:
        current_branch = 'master'  # Detached HEAD, use master

    # If creating graft, save full history branch first
    if create_graft_branch:
        full_branch = f"{current_branch}-split-full"
        lgr.debug("Creating full history branch: %s", full_branch)
        repo.call_git(['branch', full_branch, current_branch])

    # Get the current tree
    tree_sha = repo.call_git(['rev-parse', 'HEAD^{tree}']).strip()

    # Create new orphan commit with same tree
    commit_msg = (
        "Split subdataset\n\n"
        "History truncated to single commit.\n"
        "Original history preserved in branch format.\n\n"
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n\n"
        "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
    )

    # Create commit-tree with the existing tree
    new_commit = repo.call_git(
        ['commit-tree', tree_sha, '-m', commit_msg]
    ).strip()

    # If creating graft, establish git replace relationship
    if create_graft_branch:
        old_commit = repo.call_git(['rev-parse', 'HEAD']).strip()
        lgr.debug("Creating git replace: %s -> %s", new_commit, old_commit)
        repo.call_git(['replace', new_commit, old_commit])

    # Force update current branch to new commit
    repo.call_git(['reset', '--hard', new_commit])

    lgr.debug("Truncated history to single commit: %s", new_commit)


def _apply_cleanup(subdataset_path, cleanup_level):
    """Apply cleanup operations to reclaim storage.

    Parameters
    ----------
    subdataset_path : str
        Path to subdataset
    cleanup_level : str
        Cleanup level: 'reflog', 'gc', 'annex', or 'all'
    """
    if cleanup_level == 'none':
        return

    lgr.debug("Applying cleanup level '%s' to %s", cleanup_level, subdataset_path)

    subdataset = Dataset(subdataset_path)
    repo = subdataset.repo
    is_annex = hasattr(repo, 'call_annex')

    # Reflog cleanup
    if cleanup_level in ('reflog', 'all'):
        lgr.debug("Expiring reflog")
        repo.call_git(['reflog', 'expire', '--expire=now', '--all'])

    # Git gc
    if cleanup_level in ('gc', 'all'):
        lgr.debug("Running git gc --aggressive --prune=now")
        repo.call_git(['gc', '--aggressive', '--prune=now'])

    # Git-annex cleanup
    if cleanup_level in ('annex', 'all') and is_annex:
        lgr.debug("Running git annex unused and drop")
        try:
            # Find unused content
            unused_output = repo.call_annex(['unused'])

            # Drop unused if any found
            if 'unused data' in unused_output.lower():
                repo.call_annex(['dropunused', 'all'])
                lgr.debug("Dropped unused annex content")
        except CommandError as e:
            lgr.warning("Annex cleanup failed: %s", e)


def _apply_rewrite_parent_simple(parent_ds, subdataset_path, rel_path):
    """Apply rewrite-parent mode for a single path.

    Rewrites parent history using manual git commit-tree approach to include
    gitlinks to the subdataset at each commit where the subdirectory was modified.
    This makes it appear as though the subdataset existed from the beginning.

    Based on the proven approach from Experiment 17.

    NOTE: This is a simplified implementation. Full nested support requires
    using the split_helpers_nested module and batch processing multiple paths.

    Parameters
    ----------
    parent_ds : Dataset
        Parent dataset object
    subdataset_path : str
        Absolute path to subdataset
    rel_path : Path
        Relative path of subdataset within parent
    """
    lgr.info("Rewriting parent history to retroactively include %s as subdataset", rel_path)

    parent_repo = parent_ds.repo
    subdataset = Dataset(subdataset_path)
    subdataset_repo = subdataset.repo

    # Build commit mapping BEFORE resetting (needs split commit to find boundary)
    # This links original parent commits to filtered subdataset commits
    commit_map = _build_commit_mapping(
        parent_repo, subdataset_repo, str(rel_path))

    lgr.debug("Built commit map: %d parent commits map to subdataset commits",
              len(commit_map))
    for parent_sha, subds_sha in commit_map.items():
        lgr.debug("  %s -> %s", parent_sha[:8], subds_sha[:8])

    if not commit_map:
        lgr.warning("No commits found to map - subdataset may be empty or history mismatch")
        return

    # Get list of ALL commits (no split commit has been made yet for rewrite-parent mode)
    # We want to rewrite ALL existing commits
    all_commits = parent_repo.call_git([
        'rev-list', '--reverse', 'HEAD'
    ]).strip().split('\n')

    lgr.debug("Will rewrite %d commits", len(all_commits))

    # Rewrite parent history using manual git commit-tree approach
    # This will create a completely new history with gitlinks
    _rewrite_history_with_commit_tree(
        parent_repo=parent_repo,
        rel_path=str(rel_path),
        commit_map=commit_map,
        original_commits=all_commits)

    lgr.info("Parent history rewritten - %s now appears as subdataset throughout history",
             rel_path)


def _build_commit_mapping(parent_repo, subdataset_repo, rel_path):
    """Build mapping from parent commits to subdataset commits.

    Matches commits by their commit message to establish correspondence
    between parent and filtered subdataset history.

    Returns
    -------
    dict
        Mapping of {parent_commit_sha: subdataset_commit_sha}
    """
    commit_map = {}

    try:
        # Get all parent commits (before the split was registered)
        # Find the last commit before we added the split commit
        all_commits = parent_repo.call_git([
            'rev-list', '--all', '--reverse'
        ]).strip().split('\n')

        # Find split commit (has "Split" in message)
        split_commit_idx = None
        for idx, commit in enumerate(all_commits):
            msg = parent_repo.call_git(['log', '-1', '--format=%s', commit]).strip()
            if 'Split' in msg and rel_path in msg:
                split_commit_idx = idx
                break

        # Use commits before split
        if split_commit_idx:
            parent_commits = all_commits[:split_commit_idx]
        else:
            parent_commits = all_commits

        # Get subdataset commits in reverse order (oldest first)
        subdataset_commits = subdataset_repo.call_git([
            'log', '--format=%H', '--reverse'
        ]).strip().split('\n')

        # Build mapping by matching commit messages
        for parent_commit in parent_commits:
            parent_msg = parent_repo.call_git([
                'log', '-1', '--format=%s', parent_commit
            ]).strip()

            # Find matching commit in subdataset
            for subds_commit in subdataset_commits:
                subds_msg = subdataset_repo.call_git([
                    'log', '-1', '--format=%s', subds_commit
                ]).strip()

                if subds_msg == parent_msg:
                    # Verify this commit touched the split path
                    try:
                        files = parent_repo.call_git([
                            'diff-tree', '--no-commit-id', '--name-only', '-r',
                            parent_commit
                        ]).strip().split('\n')

                        if any(f.startswith(rel_path) for f in files if f):
                            commit_map[parent_commit] = subds_commit
                            break
                    except:
                        pass

    except Exception as e:
        lgr.debug("Error building commit map: %s", e)

    return commit_map


def _build_tree_with_nested_gitlink(parent_repo, orig_tree, rel_path, gitlink_sha, gitmodules_blob):
    """Build a new tree with gitlink at a nested path using bottom-up construction.

    Git mktree doesn't accept paths with slashes like 'data/logs/'. For nested paths,
    we must build trees from bottom-up:
    1. Parse 'data/logs/' into ['data', 'logs']
    2. Navigate down: root → data/ → logs/
    3. Build new data/ tree: replace logs/ entry with gitlink (160000 mode)
    4. Build new root tree: replace data/ entry with new data/ tree
    5. Return new root tree SHA

    Algorithm validated in Experiment 20.

    Parameters
    ----------
    parent_repo : GitRepo
        Parent repository
    orig_tree : str
        Original root tree SHA to modify
    rel_path : str
        Nested path like 'data/logs/' (contains slashes)
    gitlink_sha : str
        Commit SHA for the gitlink
    gitmodules_blob : str
        Blob SHA for .gitmodules content (currently added at root level)

    Returns
    -------
    str
        New root tree SHA with nested gitlink incorporated

    Raises
    ------
    RuntimeError
        If git mktree fails or path doesn't exist in tree
    """
    import subprocess
    import tempfile

    # Parse path into components: 'data/logs/' → ['data', 'logs']
    path_parts = rel_path.rstrip('/').split('/')

    # Navigate down the tree hierarchy to collect intermediate trees
    current_tree = orig_tree
    trees_at_levels = [orig_tree]  # trees_at_levels[0] = root, [1] = data/, [2] = logs/, etc.

    # Walk down to collect all parent trees
    for part in path_parts[:-1]:  # All components except the final one
        tree_output = parent_repo.call_git(['ls-tree', current_tree]).strip()

        # Find this component's tree
        found = False
        for line in tree_output.split('\n'):
            if line and line.endswith(f'\t{part}'):
                # Extract tree SHA: "040000 tree <sha>\tpart"
                tree_sha = line.split()[2]
                trees_at_levels.append(tree_sha)
                current_tree = tree_sha
                found = True
                break

        if not found:
            # Path doesn't exist in this commit - return original tree unchanged
            lgr.debug("Path component '%s' not found in tree, skipping nested gitlink", part)
            return orig_tree

    # Build new trees from bottom-up
    # Start at deepest level: replace final component with gitlink
    deepest_parent_idx = len(path_parts) - 1  # Index in trees_at_levels
    deepest_parent_tree = trees_at_levels[deepest_parent_idx]
    final_component = path_parts[-1]

    # Get all entries from deepest parent tree
    tree_output = parent_repo.call_git(['ls-tree', deepest_parent_tree]).strip()
    new_entries = []

    for line in tree_output.split('\n'):
        if line and not line.endswith(f'\t{final_component}'):
            # Keep entries except the one we're replacing
            new_entries.append(line)

    # Add gitlink entry for final component
    new_entries.append(f'160000 commit {gitlink_sha}\t{final_component}')

    # Create new tree at this level
    tree_input = '\n'.join(new_entries) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tree') as f:
        f.write(tree_input)
        tree_file = f.name

    try:
        result = subprocess.run(
            ['git', 'mktree'],
            stdin=open(tree_file, 'r'),
            capture_output=True,
            text=True,
            cwd=parent_repo.path
        )
        if result.returncode != 0:
            raise RuntimeError(f"git mktree failed at deepest level: {result.stderr}")
        new_tree_sha = result.stdout.strip()
    finally:
        os.unlink(tree_file)

    # Work upward through parent levels, replacing each modified subtree
    for level_idx in range(len(path_parts) - 2, -1, -1):
        parent_tree = trees_at_levels[level_idx]
        component = path_parts[level_idx]

        # Get all entries from parent tree
        tree_output = parent_repo.call_git(['ls-tree', parent_tree]).strip()
        new_entries = []

        for line in tree_output.split('\n'):
            if line and not line.endswith(f'\t{component}'):
                # Keep entries except the one we're replacing
                new_entries.append(line)

        # Add modified subtree entry
        new_entries.append(f'040000 tree {new_tree_sha}\t{component}')

        # Create new tree at this level
        tree_input = '\n'.join(new_entries) + '\n'
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tree') as f:
            f.write(tree_input)
            tree_file = f.name

        try:
            result = subprocess.run(
                ['git', 'mktree'],
                stdin=open(tree_file, 'r'),
                capture_output=True,
                text=True,
                cwd=parent_repo.path
            )
            if result.returncode != 0:
                raise RuntimeError(f"git mktree failed at level {level_idx}: {result.stderr}")
            new_tree_sha = result.stdout.strip()
        finally:
            os.unlink(tree_file)

    # new_tree_sha is now the modified root tree
    return new_tree_sha


def _rewrite_history_with_commit_tree(parent_repo, rel_path, commit_map, original_commits):
    """Rewrite parent history using manual git commit-tree approach.

    This creates new commits one-by-one, preserving metadata and adding gitlinks.
    Approach validated in Experiment 17.

    Parameters
    ----------
    parent_repo : GitRepo
        Parent repository
    rel_path : str
        Relative path of subdataset
    commit_map : dict
        Mapping of {parent_commit_sha: subdataset_commit_sha}
    original_commits : list
        List of original commit SHAs to rewrite (oldest first)
    """
    is_nested_path = '/' in str(rel_path)
    if is_nested_path:
        lgr.info("Processing nested path '%s' using recursive tree building", rel_path)

    total_commits = len(original_commits)

    # Use the provided list of commits (already in reverse order, oldest first)
    all_commits = original_commits

    # Start progress reporting
    pbar_id = f'rewrite-history-{id(parent_repo)}-{rel_path}'
    log_progress(
        lgr.info, pbar_id,
        'Start rewriting %d commits to add %s as subdataset', total_commits, rel_path,
        total=total_commits,
        label='Rewriting history',
        unit=' Commits'
    )

    # Create .gitmodules content
    gitmodules_content = f"""[submodule "{rel_path}"]
\tpath = {rel_path}
\turl = ./{rel_path}
"""

    # Create .gitmodules blob once (will be reused)
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(gitmodules_content)
        gitmodules_file = f.name

    try:
        gitmodules_blob = parent_repo.call_git(
            ['hash-object', '-w', gitmodules_file]
        ).strip()
    finally:
        os.unlink(gitmodules_file)

    new_commits = {}
    prev_new_commit = None

    for idx, orig_commit in enumerate(all_commits, 1):
        # Progress update
        msg_snippet = parent_repo.call_git([
            'log', '-1', '--format=%s', orig_commit]).strip()[:50]
        log_progress(
            lgr.info, pbar_id,
            'Processing commit %d/%d: %s', idx, total_commits, msg_snippet,
            update=idx,
            total=total_commits
        )

        # Get original commit metadata
        author_name = parent_repo.call_git([
            'log', '-1', '--format=%an', orig_commit]).strip()
        author_email = parent_repo.call_git([
            'log', '-1', '--format=%ae', orig_commit]).strip()
        author_date = parent_repo.call_git([
            'log', '-1', '--format=%ai', orig_commit]).strip()
        committer_name = parent_repo.call_git([
            'log', '-1', '--format=%cn', orig_commit]).strip()
        committer_email = parent_repo.call_git([
            'log', '-1', '--format=%ce', orig_commit]).strip()
        committer_date = parent_repo.call_git([
            'log', '-1', '--format=%ci', orig_commit]).strip()
        message = parent_repo.call_git([
            'log', '-1', '--format=%B', orig_commit]).strip()

        # Get original tree
        orig_tree = parent_repo.call_git([
            'log', '-1', '--format=%T', orig_commit]).strip()

        # Build new tree - different approach for nested vs top-level paths
        if orig_commit in commit_map:
            gitlink_sha = commit_map[orig_commit]

            if is_nested_path:
                # Nested path: use recursive tree builder
                lgr.debug("Building nested tree for commit %s", orig_commit[:8])
                new_tree = _build_tree_with_nested_gitlink(
                    parent_repo, orig_tree, rel_path, gitlink_sha, gitmodules_blob
                )

                # Add .gitmodules at root level
                # TODO: For proper nested support, .gitmodules should be at parent directory level
                # For now, add to root tree
                tree_entries_output = parent_repo.call_git(['ls-tree', new_tree]).strip()
                new_tree_entries = tree_entries_output.split('\n') if tree_entries_output else []

                # Remove existing .gitmodules if present, then add new one
                new_tree_entries = [e for e in new_tree_entries if e and not e.endswith('\t.gitmodules')]
                new_tree_entries.append(f'100644 blob {gitmodules_blob}\t.gitmodules')

                # Rebuild root tree with .gitmodules
                tree_input = '\n'.join(new_tree_entries) + '\n'
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                    f.write(tree_input)
                    tree_file = f.name

                try:
                    import subprocess
                    result = subprocess.run(
                        ['git', 'mktree'],
                        stdin=open(tree_file, 'r'),
                        capture_output=True,
                        text=True,
                        cwd=parent_repo.path
                    )
                    if result.returncode != 0:
                        raise RuntimeError(f"git mktree failed adding .gitmodules: {result.stderr}")
                    new_tree = result.stdout.strip()
                finally:
                    os.unlink(tree_file)

            else:
                # Top-level path: use simple flat tree building
                # List tree entries, excluding the split path
                tree_entries_output = parent_repo.call_git([
                    'ls-tree', orig_tree
                ]).strip()

                new_tree_entries = []
                if tree_entries_output:
                    for line in tree_entries_output.split('\n'):
                        # Parse: "mode type sha\tpath"
                        if line and not line.endswith(f'\t{rel_path}'):
                            new_tree_entries.append(line)

                # Add gitlink and .gitmodules
                new_tree_entries.append(f'160000 commit {gitlink_sha}\t{rel_path}')
                new_tree_entries.append(f'100644 blob {gitmodules_blob}\t.gitmodules')

                # Create new tree from entries
                tree_input = '\n'.join(new_tree_entries) + '\n' if new_tree_entries else ''
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                    f.write(tree_input)
                    tree_file = f.name

                try:
                    import subprocess
                    result = subprocess.run(
                        ['git', 'mktree'],
                        stdin=open(tree_file, 'r'),
                        capture_output=True,
                        text=True,
                        cwd=parent_repo.path
                    )
                    if result.returncode != 0:
                        raise RuntimeError(f"git mktree failed: {result.stderr}")
                    new_tree = result.stdout.strip()
                finally:
                    os.unlink(tree_file)

        else:
            # No mapping for this commit - remove the split path from tree
            if is_nested_path:
                # For nested paths without mapping, keep original tree for now
                # TODO: Implement nested path removal
                lgr.debug("No mapping for commit %s, keeping original tree for nested path", orig_commit[:8])
                new_tree = orig_tree
            else:
                # Top-level path: remove it from tree
                tree_entries_output = parent_repo.call_git([
                    'ls-tree', orig_tree
                ]).strip()

                new_tree_entries = []
                if tree_entries_output:
                    for line in tree_entries_output.split('\n'):
                        if line and not line.endswith(f'\t{rel_path}'):
                            new_tree_entries.append(line)

                # Create new tree from entries
                tree_input = '\n'.join(new_tree_entries) + '\n' if new_tree_entries else ''
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                    f.write(tree_input)
                    tree_file = f.name

                try:
                    import subprocess
                    result = subprocess.run(
                        ['git', 'mktree'],
                        stdin=open(tree_file, 'r'),
                        capture_output=True,
                        text=True,
                        cwd=parent_repo.path
                    )
                    if result.returncode != 0:
                        raise RuntimeError(f"git mktree failed: {result.stderr}")
                    new_tree = result.stdout.strip()
                finally:
                    os.unlink(tree_file)

        # Create new commit with same metadata
        env = os.environ.copy()
        env['GIT_AUTHOR_NAME'] = author_name
        env['GIT_AUTHOR_EMAIL'] = author_email
        env['GIT_AUTHOR_DATE'] = author_date
        env['GIT_COMMITTER_NAME'] = committer_name
        env['GIT_COMMITTER_EMAIL'] = committer_email
        env['GIT_COMMITTER_DATE'] = committer_date

        commit_tree_args = ['commit-tree', new_tree, '-m', message]
        if prev_new_commit:
            commit_tree_args.insert(1, '-p')
            commit_tree_args.insert(2, prev_new_commit)

        new_commit = parent_repo.call_git(commit_tree_args, env=env).strip()

        lgr.debug("Rewrote %s -> %s (%s)", orig_commit[:8], new_commit[:8],
                  message.split('\n')[0][:40])

        new_commits[orig_commit] = new_commit
        prev_new_commit = new_commit

    # Update branch to new history
    current_branch = parent_repo.call_git(['rev-parse', '--abbrev-ref', 'HEAD']).strip()
    parent_repo.call_git(['update-ref', f'refs/heads/{current_branch}', prev_new_commit])
    parent_repo.call_git(['reset', '--hard', current_branch])

    # Finish progress reporting
    log_progress(
        lgr.info, pbar_id,
        'Finished rewriting %d commits successfully', len(new_commits)
    )


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
        annexed_files = subdataset.repo.call_annex(
            ['find', '--include', '*']).splitlines()

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
            ['find', '--include', '*']).splitlines()

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


def _register_as_submodule(parent_ds, subdataset_path, rel_path):
    """Register filtered repository as submodule."""
    lgr.debug("Registering %s as submodule", rel_path)

    # git submodule add
    parent_ds.repo.call_git([
        'submodule', 'add',
        f'./{rel_path}',
        str(rel_path)
    ])


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
