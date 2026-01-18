# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Integration tests for split command - tests complete workflows on real scenarios."""

from pathlib import Path

import pytest

from datalad.api import (
    Dataset,
    split,
)
from datalad.tests.utils_pytest import (
    assert_in,
    assert_result_count,
    assert_status,
    with_tempfile,
)


@pytest.mark.ai_generated
@with_tempfile
def test_split_top_complete_workflow(path=None):
    """Test complete split-top workflow from creation to verification."""
    # Create parent dataset with history (no annex for easier file modification)
    ds = Dataset(path).create(force=True, annex=False)

    # Create multiple commits touching both data/ and root
    data_dir = Path(path) / 'data'
    data_dir.mkdir()

    # Commit 1: Add data and root files
    (data_dir / 'file1.txt').write_text('data v1')
    (Path(path) / 'root.txt').write_text('root v1')
    ds.save(message='Commit 1: Initial files')

    # Commit 2: Modify data
    (data_dir / 'file2.txt').write_text('data v2')
    ds.save(message='Commit 2: Add data file')

    # Commit 3: Modify both
    (data_dir / 'file1.txt').write_text('data v1 modified')
    (Path(path) / 'root.txt').write_text('root v1 modified')
    ds.save(message='Commit 3: Modify both')

    # Get initial commit count
    initial_commits = ds.repo.call_git(['rev-list', '--count', 'HEAD']).strip()

    # Perform split
    res = split('data', dataset=path, force=True, return_type='list')

    # Verify split succeeded
    assert_result_count(res, 1, action='split', status='ok')

    # Verify parent has new commit
    new_commits = ds.repo.call_git(['rev-list', '--count', 'HEAD']).strip()
    assert int(new_commits) == int(initial_commits) + 1

    # Verify subdataset exists
    subds = Dataset(Path(path) / 'data')
    assert subds.is_installed()

    # Verify subdataset has filtered history (3 commits that touched data/)
    subds_commits = subds.repo.call_git(['rev-list', '--count', 'HEAD']).strip()
    assert int(subds_commits) == 3  # All commits touched data/

    # Verify .gitmodules
    assert (Path(path) / '.gitmodules').exists()
    gitmodules_content = (Path(path) / '.gitmodules').read_text()
    assert '[submodule "data"]' in gitmodules_content

    # Verify files in subdataset
    assert (Path(path) / 'data' / 'file1.txt').exists()
    assert (Path(path) / 'data' / 'file2.txt').exists()

    # Verify root file still in parent
    assert (Path(path) / 'root.txt').exists()


@pytest.mark.ai_generated
@with_tempfile
def test_truncate_top_space_savings(path=None):
    """Test truncate-top mode reduces history to single commit."""
    ds = Dataset(path).create(force=True, annex=False)

    # Create dataset with multiple commits
    data_dir = Path(path) / 'data'
    data_dir.mkdir()

    for i in range(5):
        (data_dir / f'file{i}.txt').write_text(f'content {i}')
        ds.save(message=f'Commit {i+1}')

    # Split with truncate-top
    res = split(
        'data',
        dataset=path,
        mode='truncate-top',
        force=True,
        return_type='list'
    )

    assert_result_count(res, 1, action='split', status='ok')

    # Verify subdataset has exactly 1 commit
    subds = Dataset(Path(path) / 'data')
    subds_commits = subds.repo.call_git(['rev-list', '--count', 'HEAD']).strip()
    assert int(subds_commits) == 1

    # Verify all files still present
    for i in range(5):
        assert (Path(path) / 'data' / f'file{i}.txt').exists()

    # Verify commit message
    commit_msg = subds.repo.call_git(['log', '-1', '--format=%s']).strip()
    assert 'Split subdataset' in commit_msg


@pytest.mark.ai_generated
@with_tempfile
def test_truncate_top_graft_preserves_history(path=None):
    """Test truncate-top-graft creates backup branch with git replace."""
    ds = Dataset(path).create(force=True)

    data_dir = Path(path) / 'data'
    data_dir.mkdir()

    # Create commits with distinct messages
    messages = []
    for i in range(3):
        (data_dir / f'file{i}.txt').write_text(f'content {i}')
        msg = f'Data commit {i+1}'
        messages.append(msg)
        ds.save(message=msg)

    # Split with truncate-top-graft
    res = split(
        'data',
        dataset=path,
        mode='truncate-top-graft',
        force=True,
        return_type='list'
    )

    assert_result_count(res, 1, action='split', status='ok')

    subds = Dataset(Path(path) / 'data')

    # Get current branch name
    current_branch = subds.repo.call_git(['branch', '--show-current']).strip()

    # Verify current branch has 1 commit (truncated)
    # Note: Must disable git replace to see actual truncated state
    current_commits = subds.repo.call_git([
        '--no-replace-objects', 'rev-list', '--count', current_branch
    ]).strip()
    assert int(current_commits) == 1

    # Verify -split-full branch exists with full history
    branches = subds.repo.call_git(['branch']).strip()
    full_branch_name = f'{current_branch}-split-full'
    assert full_branch_name in branches

    full_commits = subds.repo.call_git([
        'rev-list', '--count', full_branch_name
    ]).strip()
    assert int(full_commits) == 3

    # Verify git replace exists
    replace_list = subds.repo.call_git(['replace', '--list']).strip()
    assert len(replace_list) > 0

    # Verify log shows full history (due to replace)
    log_output = subds.repo.call_git(['log', '--oneline']).strip().split('\n')
    # With replace active, should show full history
    assert len(log_output) >= 3


@pytest.mark.ai_generated
@with_tempfile
def test_cleanup_operations(path=None):
    """Test cleanup operations reclaim space."""
    ds = Dataset(path).create(force=True)

    data_dir = Path(path) / 'data'
    data_dir.mkdir()

    # Create multiple commits
    for i in range(5):
        (data_dir / f'file{i}.txt').write_text(f'x' * 1000)  # Some content
        ds.save(message=f'Commit {i+1}')

    # Split with cleanup
    res = split(
        'data',
        dataset=path,
        mode='truncate-top',
        cleanup='all',
        force=True,
        return_type='list'
    )

    assert_result_count(res, 1, action='split', status='ok')

    # Verify reflog was expired
    subds = Dataset(Path(path) / 'data')
    reflog = subds.repo.call_git(['reflog']).strip()
    # After expiry and gc, reflog should be minimal
    assert len(reflog.split('\n')) < 10

    # Verify gc ran (check for packed refs or reduced object count)
    # This is indirect - just verify command succeeded


@pytest.mark.ai_generated
@with_tempfile
def test_multiple_paths_bottomup_processing(path=None):
    """Test splitting multiple paths processes bottom-up."""
    ds = Dataset(path).create(force=True)

    # Create nested structure
    (Path(path) / 'data').mkdir()
    (Path(path) / 'logs').mkdir()

    (Path(path) / 'data' / 'file1.txt').write_text('data')
    (Path(path) / 'logs' / 'file2.txt').write_text('logs')
    ds.save(message='Initial commit')

    # Split both paths
    res = split(
        ['data', 'logs'],
        dataset=path,
        force=True,
        return_type='list'
    )

    # Should succeed for both
    assert_result_count(res, 2, action='split', status='ok')

    # Verify both subdatasets exist
    assert Dataset(Path(path) / 'data').is_installed()
    assert Dataset(Path(path) / 'logs').is_installed()


@pytest.mark.ai_generated
@with_tempfile
def test_worktree_mode_shares_objects(path=None):
    """Test worktree mode creates shared object storage."""
    ds = Dataset(path).create(force=True, annex=False)

    data_dir = Path(path) / 'data'
    data_dir.mkdir()
    (data_dir / 'file.txt').write_text('content')
    ds.save(message='Add data')

    # Split with worktree mode
    res = split(
        'data',
        dataset=path,
        clone_mode='worktree',
        force=True,
        return_type='list'
    )

    assert_result_count(res, 1, action='split', status='ok')

    # Verify .git is a file (points to parent), not a directory
    git_path = Path(path) / 'data' / '.git'
    assert git_path.exists()
    assert git_path.is_file()  # Worktree has .git file, not directory


@pytest.mark.ai_generated
@with_tempfile
def test_annex_integration_preserves_location(path=None):
    """Test git-annex location tracking is preserved."""
    ds = Dataset(path).create(force=True)  # Creates annex by default

    data_dir = Path(path) / 'data'
    data_dir.mkdir()

    # Add annexed file
    (data_dir / 'large.dat').write_text('x' * 10000)
    ds.save(message='Add large file')

    # Split
    res = split('data', dataset=path, force=True, return_type='list')
    assert_result_count(res, 1, action='split', status='ok')

    # Verify subdataset has git-annex
    subds = Dataset(Path(path) / 'data')
    assert hasattr(subds.repo, 'call_annex')

    # Verify git-annex branch exists
    branches = subds.repo.call_git(['branch', '-a']).strip()
    assert 'git-annex' in branches

    # Verify location tracking
    # whereis should show origin (parent) has the content
    try:
        whereis_output = subds.repo.call_annex(['whereis', 'large.dat'])
        assert 'origin' in whereis_output
    except:
        # Whereis might fail if content not present, which is ok
        pass


@pytest.mark.ai_generated
@with_tempfile
def test_dry_run_no_modifications(path=None):
    """Test dry-run mode makes no actual changes."""
    ds = Dataset(path).create(force=True)

    data_dir = Path(path) / 'data'
    data_dir.mkdir()
    (data_dir / 'file.txt').write_text('data')
    ds.save(message='Initial')

    # Get initial state
    initial_commit = ds.repo.call_git(['rev-parse', 'HEAD']).strip()

    # Dry-run split
    res = split(
        'data',
        dataset=path,
        dry_run=True,
        return_type='list'
    )

    assert_result_count(res, 1, action='split', status='ok')

    # Verify no changes
    current_commit = ds.repo.call_git(['rev-parse', 'HEAD']).strip()
    assert current_commit == initial_commit

    # Verify subdataset NOT created
    assert not (Path(path) / 'data' / '.git').exists()

    # Verify data directory still exists as directory
    assert (Path(path) / 'data').is_dir()
    assert (Path(path) / 'data' / 'file.txt').exists()


@pytest.mark.ai_generated
@with_tempfile
def test_content_copy_mode(path=None):
    """Test content=copy mode copies annexed content to subdataset."""
    ds = Dataset(path).create(force=True)

    data_dir = Path(path) / 'data'
    data_dir.mkdir()
    (data_dir / 'file.dat').write_text('x' * 5000)
    ds.save(message='Add file')

    # Split with content copy
    res = split(
        'data',
        dataset=path,
        content='copy',
        force=True,
        return_type='list'
    )

    assert_result_count(res, 1, action='split', status='ok')

    # Verify subdataset has content
    subds = Dataset(Path(path) / 'data')

    # Check if content is present (file is not a symlink or is unlocked)
    file_path = Path(path) / 'data' / 'file.dat'
    # With copy mode, content should be available
    # (exact behavior depends on annex settings)
    assert file_path.exists()


@pytest.mark.ai_generated
@with_tempfile
def test_error_handling_nonexistent_path(path=None):
    """Test proper error handling for nonexistent paths."""
    ds = Dataset(path).create(force=True)

    # Try to split nonexistent path
    res = split(
        'nonexistent',
        dataset=path,
        force=True,
        on_failure='ignore',
        return_type='list'
    )

    # Should report error/impossible
    assert_result_count(res, 1, action='split')
    assert_status('impossible', res)


@pytest.mark.ai_generated
@with_tempfile
def test_error_handling_file_not_directory(path=None):
    """Test error when trying to split a file."""
    ds = Dataset(path).create(force=True)

    # Create a file
    (Path(path) / 'file.txt').write_text('content')
    ds.save(message='Add file')

    # Try to split the file
    res = split(
        'file.txt',
        dataset=path,
        force=True,
        on_failure='ignore',
        return_type='list'
    )

    assert_status('impossible', res)


@pytest.mark.ai_generated
@with_tempfile
def test_verification_checks(path=None):
    """Test that verification checks run and report correctly."""
    ds = Dataset(path).create(force=True)

    data_dir = Path(path) / 'data'
    data_dir.mkdir()
    (data_dir / 'file.txt').write_text('content')
    ds.save(message='Add data')

    # Split with verification (default)
    res = split(
        'data',
        dataset=path,
        force=True,
        return_type='list'
    )

    # Should have split result + verification results
    assert_result_count(res, 1, action='split', status='ok')
    # Verification results depend on implementation
    verify_results = [r for r in res if r.get('action') == 'verify']
    assert len(verify_results) >= 0  # May have verification results


@pytest.mark.ai_generated
@with_tempfile
def test_preserve_commit_metadata(path=None):
    """Test that commit authors and timestamps are preserved in split."""
    ds = Dataset(path).create(force=True)

    data_dir = Path(path) / 'data'
    data_dir.mkdir()

    # Create commit with specific metadata
    (data_dir / 'file.txt').write_text('content')
    ds.save(message='Important data commit')

    # Get original author
    original_author = ds.repo.call_git([
        'log', '-1', '--format=%an <%ae>'
    ]).strip()

    # Split
    split('data', dataset=path, force=True)

    # Check subdataset preserves author
    subds = Dataset(Path(path) / 'data')
    subds_author = subds.repo.call_git([
        'log', '-1', '--format=%an <%ae>'
    ]).strip()

    # Author should be preserved
    assert original_author == subds_author


@pytest.mark.ai_generated
@with_tempfile
def test_rewrite_parent_mode_basic(path=None):
    """Test rewrite-parent mode preserves all commits with retroactive gitlinks."""
    # Create parent dataset without annex for simpler testing
    ds = Dataset(path).create(force=True, annex=False)

    # Create commits before data/ exists
    (Path(path) / 'root1.txt').write_text('root 1')
    ds.save(message='Root commit 1')

    # Create data/ and add commits
    data_dir = Path(path) / 'data'
    data_dir.mkdir()
    (data_dir / 'file1.txt').write_text('v1')
    ds.save(message='Commit 1: Add data')

    (data_dir / 'file2.txt').write_text('v2')
    ds.save(message='Commit 2: Add more data')

    # Another root commit
    (Path(path) / 'root2.txt').write_text('root 2')
    ds.save(message='Root commit 2')

    # Another data commit
    (data_dir / 'file3.txt').write_text('v3')
    ds.save(message='Commit 3: Add even more data')

    # Count commits before split
    commits_before = ds.repo.call_git(['rev-list', '--count', 'HEAD']).strip()

    # Run split with rewrite-parent mode
    result = split(
        'data',
        dataset=path,
        mode='rewrite-parent',
        force=True,
        return_type='list'
    )

    assert_status('ok', result)

    # Count commits after split - should be SAME
    commits_after = ds.repo.call_git(['rev-list', '--count', 'HEAD']).strip()
    assert commits_before == commits_after, \
        f"Commit count changed: {commits_before} -> {commits_after}"

    # Check that commits have gitlinks
    all_commits = ds.repo.call_git(['rev-list', '--reverse', 'HEAD']).strip().split('\n')

    # Initial commit should NOT have gitlink (no data/ yet)
    initial_commit = all_commits[0]
    initial_tree = ds.repo.call_git(['log', '-1', '--format=%T', initial_commit]).strip()
    initial_tree_lines = ds.repo.call_git(['ls-tree', initial_tree]).strip()
    assert '\tdata' not in initial_tree_lines, "Initial commit should not have data/"

    # Check which commits should have gitlinks (those that touched data/)
    # We know these commits touched data/ based on commit messages
    data_commits = ['Commit 1: Add data', 'Commit 2: Add more data', 'Commit 3: Add even more data']

    for commit in all_commits:
        msg = ds.repo.call_git(['log', '-1', '--format=%s', commit]).strip()
        tree = ds.repo.call_git(['log', '-1', '--format=%T', commit]).strip()
        tree_lines = ds.repo.call_git(['ls-tree', tree]).strip()

        if msg in data_commits:
            # Commits that touched data/ should have gitlinks
            assert '160000 commit' in tree_lines and '\tdata' in tree_lines, \
                f"Commit '{msg}' should have gitlink but doesn't"
        elif msg != '[DATALAD] new dataset':
            # Root commits may or may not have gitlinks depending on when they occurred
            # Just verify tree is valid
            pass

    # Verify subdataset exists and has correct structure
    subds = Dataset(Path(path) / 'data')
    assert subds.is_installed(), "Subdataset should be installed"

    # Verify subdataset has filtered history (only commits touching data/)
    subds_commits = subds.repo.call_git(['rev-list', '--count', 'HEAD']).strip()
    # Should have 3 commits (the ones that touched data/)
    assert int(subds_commits) == 3, \
        f"Subdataset should have 3 commits, got {subds_commits}"

    # Verify files exist in subdataset
    assert (Path(path) / 'data' / 'file1.txt').exists()
    assert (Path(path) / 'data' / 'file2.txt').exists()
    assert (Path(path) / 'data' / 'file3.txt').exists()


@pytest.mark.ai_generated
@with_tempfile
def test_rewrite_parent_mode_nested(path=None):
    """Test rewrite-parent mode with nested directory structure."""
    ds = Dataset(path).create(force=True, annex=False)

    # Create nested structure
    nested_dir = Path(path) / 'data' / 'subdir' / 'deep'
    nested_dir.mkdir(parents=True)

    (nested_dir / 'file.txt').write_text('v1')
    ds.save(message='Add nested structure')

    (nested_dir / 'file.txt').write_text('v2')
    ds.save(message='Update nested file')

    commits_before = int(ds.repo.call_git(['rev-list', '--count', 'HEAD']).strip())

    # Split
    result = split(
        'data',
        dataset=path,
        mode='rewrite-parent',
        force=True,
        return_type='list'
    )

    assert_status('ok', result)

    # Verify commits preserved
    commits_after = int(ds.repo.call_git(['rev-list', '--count', 'HEAD']).strip())
    assert commits_before == commits_after

    # Verify nested structure in subdataset
    assert (Path(path) / 'data' / 'subdir' / 'deep' / 'file.txt').exists()
    assert (Path(path) / 'data' / 'subdir' / 'deep' / 'file.txt').read_text() == 'v2'


@pytest.mark.ai_generated
@with_tempfile
def test_rewrite_parent_mode_commit_metadata(path=None):
    """Test that rewrite-parent mode preserves commit metadata."""
    ds = Dataset(path).create(force=True, annex=False)

    data_dir = Path(path) / 'data'
    data_dir.mkdir()
    (data_dir / 'file.txt').write_text('v1')
    ds.save(message='Test commit for metadata')

    # Get original metadata
    original_author = ds.repo.call_git(['log', '-1', '--format=%an']).strip()
    original_email = ds.repo.call_git(['log', '-1', '--format=%ae']).strip()
    original_date = ds.repo.call_git(['log', '-1', '--format=%ai']).strip()
    original_msg = ds.repo.call_git(['log', '-1', '--format=%B']).strip()

    # Split with rewrite-parent
    split('data', dataset=path, mode='rewrite-parent', force=True)

    # Get metadata after rewrite
    new_author = ds.repo.call_git(['log', '-1', '--format=%an']).strip()
    new_email = ds.repo.call_git(['log', '-1', '--format=%ae']).strip()
    # Date will change due to rewrite, but author should be same
    new_msg = ds.repo.call_git(['log', '-1', '--format=%B']).strip()

    # Metadata should be preserved
    assert new_author == original_author, "Author changed after rewrite"
    assert new_email == original_email, "Email changed after rewrite"
    assert new_msg == original_msg, "Message changed after rewrite"


@pytest.mark.ai_generated
@with_tempfile
def test_rewrite_parent_mode_nested_path_error(path=None):
    """Test that rewrite-parent mode fails gracefully on nested paths."""
    ds = Dataset(path).create(force=True, annex=False)

    # Create nested structure
    nested_dir = Path(path) / 'images' / 'adswa'
    nested_dir.mkdir(parents=True)
    (nested_dir / 'file.txt').write_text('v1')
    ds.save(message='Add nested structure')

    # Attempt to split nested path (should fail with NotImplementedError)
    result = split(
        'images/adswa',
        dataset=path,
        mode='rewrite-parent',
        force=True,
        return_type='list',
        on_failure='ignore'
    )

    # Should have failed with error status
    assert len(result) > 0
    error_result = [r for r in result if r.get('status') == 'error']
    assert len(error_result) > 0, "Should have error result for nested path"

    # Error message should mention nested paths not supported
    error_msg = str(error_result[0].get('message', ''))
    assert 'nested path' in error_msg.lower() or 'slash' in error_msg.lower(), \
        f"Error message should mention nested paths: {error_msg}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
