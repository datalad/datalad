# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper functions for nested subdataset setup in split --mode=rewrite-parent.

Based on experimental validation (Experiments 17-19), proper nested subdataset
setup requires THREE critical steps after rewriting history with gitlinks:

1. Clone filtered repositories to their paths
2. Checkout correct commits (matching gitlinks)
3. Initialize submodules in git config (often forgotten!)

Missing step 3 results in uninitialized submodules (shown with '-' prefix
in git submodule status) and incomplete setup.
"""

__docformat__ = 'restructuredtext'

import logging
import os
import subprocess
from pathlib import Path

lgr = logging.getLogger('datalad.distribution.split')


def setup_nested_subdatasets(parent_ds, split_paths, filtered_repos, commit_maps):
    """
    Set up physical subdatasets after rewriting parent history with gitlinks.

    This implements the complete 3-step setup procedure discovered in
    Experiments 17-19:

    1. Clone filtered repositories into their paths
    2. Checkout commits matching the gitlinks in parent tree
    3. Initialize submodules in .git/config at each level

    CRITICAL: Step 3 (submodule init) is often forgotten but essential!
    Without it, submodules show '-' prefix in git submodule status and
    may not function correctly.

    Parameters
    ----------
    parent_ds : Dataset
        Parent dataset object
    split_paths : list of str
        List of split paths (e.g., ['data/', 'data/logs/', 'data/logs/subds/'])
        Will be processed in bottom-up order (deepest first)
    filtered_repos : dict
        Mapping of {path: filtered_repo_path} for each split path
    commit_maps : dict
        Mapping of {path: {original_sha: filtered_sha}} for each split path

    Returns
    -------
    generator
        Yields result dictionaries for each step

    See Also
    --------
    docs/designs/split/experiments/NESTED_SUBDATASET_SETUP_PROCEDURE.md
        Complete procedure documentation with examples
    """
    # Sort paths deepest first (bottom-up processing)
    paths = sorted(split_paths, key=lambda p: -p.count('/'))

    for path in paths:
        # Get parent directory for this split
        parent_dir = os.path.dirname(path) or '.'
        parent_repo_path = os.path.join(parent_ds.path, parent_dir)

        # Step 1: Get gitlink SHA from parent's tree
        gitlink_sha = _get_gitlink_sha(parent_repo_path, os.path.basename(path))

        if not gitlink_sha:
            yield {
                'action': 'setup_subdataset',
                'status': 'error',
                'path': path,
                'message': f'No gitlink found for {path} in parent tree',
            }
            continue

        # Step 2: Clone filtered repository
        subds_path = os.path.join(parent_ds.path, path)
        try:
            _clone_repository(filtered_repos[path], subds_path)
        except Exception as e:
            yield {
                'action': 'setup_subdataset',
                'status': 'error',
                'path': path,
                'message': f'Failed to clone filtered repo: {e}',
            }
            continue

        # Step 3: Checkout correct commit
        try:
            _checkout_commit(subds_path, gitlink_sha)
        except Exception as e:
            yield {
                'action': 'setup_subdataset',
                'status': 'error',
                'path': path,
                'message': f'Failed to checkout {gitlink_sha}: {e}',
            }
            continue

        # Step 4: CRITICAL - Initialize submodule in parent's .git/config
        try:
            _initialize_submodule(parent_repo_path, os.path.basename(path))
        except Exception as e:
            yield {
                'action': 'setup_subdataset',
                'status': 'error',
                'path': path,
                'message': f'Failed to initialize submodule: {e}',
            }
            continue

        yield {
            'action': 'setup_subdataset',
            'status': 'ok',
            'path': path,
            'message': f'Successfully set up nested subdataset at {path}',
        }

    # Final verification
    yield from verify_nested_subdataset_setup(parent_ds, split_paths)


def verify_nested_subdataset_setup(parent_ds, split_paths):
    """
    Verify complete nested subdataset setup with all required aspects.

    Based on Experiment 19 verification, checks ALL of the following:

    1. .git directories exist at all levels
    2. .gitmodules files present where expected
    3. [submodule "..."] entries in each level's .git/config
    4. git submodule status shows NO '-' prefix (indicates initialized)
    5. Gitlinks match actual commits
    6. git submodule update --init --recursive works

    Parameters
    ----------
    parent_ds : Dataset
        Parent dataset object
    split_paths : list of str
        List of split paths to verify

    Yields
    ------
    dict
        Result dictionaries for each verification check
    """
    checks_passed = []
    checks_failed = []

    # Check 1: .git directories at all levels
    for path in split_paths:
        git_dir = os.path.join(parent_ds.path, path, '.git')
        if os.path.isdir(git_dir):
            checks_passed.append(f'.git exists at {path}')
        else:
            checks_failed.append(f'.git MISSING at {path}')

    # Check 2: .gitmodules files
    for path in split_paths:
        parent_dir = os.path.dirname(path) or '.'
        gitmodules_path = os.path.join(parent_ds.path, parent_dir, '.gitmodules')
        # Check if it exists in tree (for parent) or on disk (for nested)
        if parent_dir == '.':
            # Parent level - check in tree
            try:
                subprocess.run(
                    ['git', 'ls-tree', 'HEAD', '.gitmodules'],
                    cwd=parent_ds.path,
                    check=True,
                    capture_output=True
                )
                checks_passed.append('.gitmodules in parent tree')
            except subprocess.CalledProcessError:
                checks_failed.append('.gitmodules MISSING from parent tree')
        else:
            # Nested level - check on disk
            if os.path.exists(gitmodules_path):
                checks_passed.append(f'.gitmodules at {parent_dir}/')
            else:
                checks_failed.append(f'.gitmodules MISSING at {parent_dir}/')

    # Check 3: Submodule initialization (no '-' prefix in status)
    try:
        result = subprocess.run(
            ['git', 'submodule', 'status', '--recursive'],
            cwd=parent_ds.path,
            capture_output=True,
            text=True,
            check=True
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                if line.startswith('-'):
                    checks_failed.append(f'Submodule NOT initialized: {line}')
                else:
                    checks_passed.append(f'Submodule initialized: {line[:50]}...')
    except subprocess.CalledProcessError as e:
        checks_failed.append(f'git submodule status failed: {e}')

    # Check 4: [submodule] entries in .git/config
    for path in split_paths:
        parent_dir = os.path.dirname(path) or '.'
        config_path = os.path.join(parent_ds.path, parent_dir, '.git/config')
        if os.path.exists(config_path):
            with open(config_path) as f:
                content = f.read()
                submod_name = os.path.basename(path.rstrip('/'))
                if f'[submodule "{submod_name}"]' in content:
                    checks_passed.append(f'[submodule "{submod_name}"] in config')
                else:
                    checks_failed.append(
                        f'[submodule "{submod_name}"] MISSING from {parent_dir}/.git/config'
                    )

    # Check 5: Gitlinks match actual commits
    for path in split_paths:
        parent_dir = os.path.dirname(path) or '.'
        try:
            gitlink = _get_gitlink_sha(
                os.path.join(parent_ds.path, parent_dir),
                os.path.basename(path)
            )
            actual = _get_commit_sha(os.path.join(parent_ds.path, path))
            if gitlink == actual:
                checks_passed.append(f'Gitlink matches commit for {path}')
            else:
                checks_failed.append(
                    f'Gitlink MISMATCH for {path}: {gitlink} != {actual}'
                )
        except Exception as e:
            checks_failed.append(f'Failed to verify gitlink for {path}: {e}')

    # Check 6: git submodule update works
    try:
        subprocess.run(
            ['git', 'submodule', 'update', '--init', '--recursive'],
            cwd=parent_ds.path,
            check=True,
            capture_output=True
        )
        checks_passed.append('git submodule update --init --recursive: OK')
    except subprocess.CalledProcessError as e:
        checks_failed.append(f'git submodule update FAILED: {e}')

    # Yield results
    if checks_failed:
        yield {
            'action': 'verify_nested_setup',
            'status': 'error',
            'message': f'Verification failed: {len(checks_failed)} check(s) failed',
            'failed_checks': checks_failed,
            'passed_checks': checks_passed,
        }
    else:
        yield {
            'action': 'verify_nested_setup',
            'status': 'ok',
            'message': f'All {len(checks_passed)} verification checks passed',
            'passed_checks': checks_passed,
        }


def _get_gitlink_sha(repo_path, submodule_name):
    """Get gitlink SHA from git tree."""
    try:
        result = subprocess.run(
            ['git', 'ls-tree', 'HEAD', submodule_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        # Output format: "160000 commit <sha>\t<name>"
        parts = result.stdout.strip().split()
        if len(parts) >= 3 and parts[0] == '160000':
            return parts[2]
    except subprocess.CalledProcessError:
        pass
    return None


def _clone_repository(source, destination):
    """Clone a repository."""
    subprocess.run(
        ['git', 'clone', source, destination],
        check=True,
        capture_output=True
    )


def _checkout_commit(repo_path, commit_sha):
    """Checkout a specific commit."""
    subprocess.run(
        ['git', 'checkout', commit_sha],
        cwd=repo_path,
        check=True,
        capture_output=True
    )


def _initialize_submodule(parent_repo_path, submodule_name):
    """
    Initialize submodule in parent's .git/config.

    CRITICAL: This step is often forgotten but essential!
    Without it, the submodule shows '-' prefix in git submodule status.
    """
    # git submodule init reads .gitmodules and writes to .git/config
    subprocess.run(
        ['git', 'submodule', 'init', submodule_name],
        cwd=parent_repo_path,
        check=True,
        capture_output=True
    )

    # git submodule sync ensures URLs match .gitmodules
    subprocess.run(
        ['git', 'submodule', 'sync', submodule_name],
        cwd=parent_repo_path,
        check=True,
        capture_output=True
    )


def _get_commit_sha(repo_path):
    """Get current commit SHA."""
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()
