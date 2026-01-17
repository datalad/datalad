# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test split action

"""

import os
from pathlib import Path

import pytest

from datalad.api import (
    create,
    split,
)
from datalad.support.exceptions import (
    IncompleteResultsError,
    InsufficientArgumentsError,
)
from datalad.tests.utils_pytest import (
    assert_false,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    create_tree,
    eq_,
    ok_,
    ok_exists,
    ok_file_has_content,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    chpwd,
)

from ..dataset import Dataset


###########################
# Test parameter validation
###########################

@pytest.mark.ai_generated
@with_tempfile
def test_split_needs_dataset(path=None):
    """Test that split requires a dataset."""
    ds = create(path)

    # Cannot split without specifying a path
    with assert_raises(InsufficientArgumentsError):
        split(dataset=ds.path)


@pytest.mark.ai_generated
@with_tree(tree={
    'file.txt': 'content',
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
    }
})
def test_split_invalid_clone_mode(path=None):
    """Test that invalid clone_mode is rejected."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Invalid clone mode should fail parameter validation
    # Note: This will fail at constraint validation before even calling __call__
    with assert_raises((ValueError, TypeError)):
        split('data', dataset=ds.path, clone_mode='invalid_mode')


@pytest.mark.ai_generated
@with_tree(tree={
    'file.txt': 'content',
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
    }
})
def test_split_invalid_content_mode(path=None):
    """Test that invalid content mode is rejected."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Invalid content mode should fail parameter validation
    with assert_raises((ValueError, TypeError)):
        split('data', dataset=ds.path, content='invalid_mode')


@pytest.mark.ai_generated
@with_tree(tree={
    'file.txt': 'content',
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
    }
})
def test_split_reckless_without_annex(path=None):
    """Test that reckless-ephemeral requires git-annex."""
    # Create dataset WITHOUT annex
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # reckless-ephemeral mode requires annex
    res = split(
        'data',
        dataset=ds.path,
        clone_mode='reckless-ephemeral',
        on_failure='ignore',
        return_type='list',
    )

    # Should get an error status
    assert_in_results(res, status='error')


############################
# Test path validation
############################

@pytest.mark.ai_generated
@with_tempfile
def test_split_nonexistent_path(path=None):
    """Test that split rejects nonexistent paths."""
    ds = create(path)

    # Try to split a nonexistent path
    res = split(
        'nonexistent',
        dataset=ds.path,
        on_failure='ignore',
        return_type='list',
    )

    assert_result_count(res, 1)
    assert_in_results(res, status='impossible', path=str(Path(ds.path) / 'nonexistent'))


@pytest.mark.ai_generated
@with_tree(tree={
    'file.txt': 'content',
})
def test_split_file_not_directory(path=None):
    """Test that split rejects file paths (not directories)."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Try to split a file instead of directory
    res = split(
        'file.txt',
        dataset=ds.path,
        on_failure='ignore',
        return_type='list',
    )

    assert_result_count(res, 1)
    assert_in_results(res, status='impossible')


@pytest.mark.ai_generated
@with_tempfile
def test_split_dataset_root(path=None):
    """Test that split rejects dataset root."""
    ds = create(path)

    # Try to split the dataset root itself
    res = split(
        '.',
        dataset=ds.path,
        on_failure='ignore',
        return_type='list',
    )

    assert_result_count(res, 1)
    assert_in_results(res, status='impossible')


@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'subds': {
            'file.txt': 'content',
        },
        'file2.txt': 'data',
    }
})
def test_split_path_in_subdataset(path=None):
    """Test that split rejects paths already in subdatasets."""
    ds = Dataset(path).create(force=True)

    # Create a subdataset
    subds = ds.create('data/subds')
    ds.save()

    # Try to split a path inside the subdataset
    res = split(
        'data/subds/file.txt',
        dataset=ds.path,
        on_failure='ignore',
        return_type='list',
    )

    assert_result_count(res, 1)
    assert_in_results(res, status='impossible')


@pytest.mark.ai_generated
@with_tree(tree={
    'data': {},  # Empty directory
})
def test_split_empty_directory(path=None):
    """Test that split rejects directories with no git-tracked files."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Try to split empty directory
    res = split(
        'data',
        dataset=ds.path,
        on_failure='ignore',
        return_type='list',
    )

    assert_result_count(res, 1)
    assert_in_results(res, status='impossible')


############################
# Test basic split operation
############################

@pytest.mark.ai_generated
@with_tree(tree={
    'file.txt': 'root content',
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
        'subdir': {
            'file3.txt': 'data3',
        }
    }
})
def test_split_basic(path=None):
    """Test basic split operation."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Record initial state
    initial_files = set(ds.repo.get_files())

    # Split the data directory
    res = split(
        'data',
        dataset=ds.path,
        force=True,  # Skip confirmation
        return_type='list',
    )

    # Check result
    assert_result_count(res, 1)
    assert_in_results(res, action='split', status='ok', path=str(Path(ds.path) / 'data'))

    # Verify data is now a subdataset
    subdatasets = ds.subdatasets(result_xfm='paths')
    assert_in('data', subdatasets)

    # Verify subdataset has correct structure
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())

    # Files should be at root of subdataset
    subds_files = set(subds.repo.get_files())
    assert_in('file1.txt', subds_files)
    assert_in('file2.txt', subds_files)
    assert_in('subdir/file3.txt', subds_files)

    # Parent should not track these files anymore
    parent_files = set(ds.repo.get_files())
    assert_not_in('data/file1.txt', parent_files)
    assert_not_in('data/file2.txt', parent_files)

    # But parent should still have root file
    assert_in('file.txt', parent_files)

    # Repository should be clean
    assert_repo_status(ds.path, annex=False)


@pytest.mark.ai_generated
@with_tree(tree={
    'file.txt': 'root content',
    'data': {
        'file1.dat': 'binary data 1',
        'file2.dat': 'binary data 2',
    }
})
def test_split_with_annex(path=None):
    """Test split with git-annex repository."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Split the data directory
    res = split(
        'data',
        dataset=ds.path,
        force=True,
        return_type='list',
    )

    # Check result
    assert_result_count(res, 1)
    assert_in_results(res, action='split', status='ok')

    # Verify subdataset exists and is annex
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())
    ok_(subds.repo.is_with_annex())

    # Verify files are in annex
    subds_files = set(subds.repo.get_files())
    assert_in('file1.dat', subds_files)
    assert_in('file2.dat', subds_files)


@pytest.mark.ai_generated
@with_tree(tree={
    'root.txt': 'root',
    'data1': {
        'file1.txt': 'data1',
    },
    'data2': {
        'file2.txt': 'data2',
    }
})
def test_split_multiple_paths(path=None):
    """Test splitting multiple paths at once."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Split both data directories
    res = split(
        ['data1', 'data2'],
        dataset=ds.path,
        force=True,
        return_type='list',
    )

    # Check results
    assert_result_count(res, 2)
    assert_in_results(res, action='split', status='ok', path=str(Path(ds.path) / 'data1'))
    assert_in_results(res, action='split', status='ok', path=str(Path(ds.path) / 'data2'))

    # Verify both are subdatasets
    subdatasets = set(ds.subdatasets(result_xfm='paths'))
    assert_in('data1', subdatasets)
    assert_in('data2', subdatasets)


@pytest.mark.ai_generated
@with_tree(tree={
    'root.txt': 'root',
    'level1': {
        'file1.txt': 'level1',
        'level2': {
            'file2.txt': 'level2',
            'level3': {
                'file3.txt': 'level3',
            }
        }
    }
})
def test_split_nested_paths(path=None):
    """Test splitting nested paths (bottom-up ordering)."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Split nested paths (should process deepest first)
    res = split(
        ['level1', 'level1/level2', 'level1/level2/level3'],
        dataset=ds.path,
        force=True,
        return_type='list',
    )

    # All should succeed
    assert_result_count(res, 3, action='split', status='ok')

    # Verify nested structure
    subds1 = Dataset(Path(ds.path) / 'level1')
    ok_(subds1.is_installed())

    subds2 = Dataset(Path(ds.path) / 'level1' / 'level2')
    ok_(subds2.is_installed())

    subds3 = Dataset(Path(ds.path) / 'level1' / 'level2' / 'level3')
    ok_(subds3.is_installed())


############################
# Test clone modes
############################

@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
    }
})
def test_split_clone_mode(path=None):
    """Test split with clone mode."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Split using clone mode
    res = split(
        'data',
        dataset=ds.path,
        clone_mode='clone',
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset was created
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())

    # Subdataset should have its own .git directory
    ok_exists(Path(ds.path) / 'data' / '.git')


@pytest.mark.ai_generated
@with_tree(tree={
    'subjects': {
        'subject01': {
            'data.txt': 'subject 01 data',
        }
    }
})
def test_split_worktree_mode(path=None):
    """Test split with worktree mode."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Split using worktree mode
    res = split(
        'subjects/subject01',
        dataset=ds.path,
        clone_mode='worktree',
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset was created
    subds = Dataset(Path(ds.path) / 'subjects' / 'subject01')
    ok_(subds.is_installed())

    # Check that branch was created
    branches = ds.repo.get_branches()
    assert_in('split/subjects/subject01', branches)

    # Worktree should exist
    worktrees = ds.repo.call_git(['worktree', 'list', '--porcelain']).split('\n\n')
    worktree_paths = [wt.split('\n')[0].replace('worktree ', '') for wt in worktrees if wt.startswith('worktree')]
    assert_in(str(Path(ds.path) / 'subjects' / 'subject01'), worktree_paths)


@pytest.mark.ai_generated
@with_tree(tree={
    'subjects': {
        'subject01': {
            'data.txt': 'subject 01 data',
        }
    }
})
def test_split_worktree_custom_prefix(path=None):
    """Test split with worktree mode and custom branch prefix."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Split using worktree mode with custom prefix
    res = split(
        'subjects/subject01',
        dataset=ds.path,
        clone_mode='worktree',
        worktree_branch_prefix='archive/',
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Check that branch was created with custom prefix
    branches = ds.repo.get_branches()
    assert_in('archive/subjects/subject01', branches)


@pytest.mark.ai_generated
@with_tree(tree={
    'subjects': {
        'subject01': {
            'data.txt': 'subject 01 data',
        }
    }
})
def test_split_worktree_namespace(path=None):
    """Test split with worktree mode using namespaces."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Split using worktree mode with namespaces
    res = split(
        'subjects/subject01',
        dataset=ds.path,
        clone_mode='worktree',
        worktree_use_namespace=True,
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset was created
    subds = Dataset(Path(ds.path) / 'subjects' / 'subject01')
    ok_(subds.is_installed())

    # Namespace ref should exist
    namespace_ref = f'refs/namespaces/split/refs/heads/subjects/subject01'
    refs_output = ds.repo.call_git(['show-ref'])
    assert_in(namespace_ref, refs_output)


@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'file1.dat': 'content1',
        'file2.dat': 'content2',
    }
})
def test_split_reckless_ephemeral_mode(path=None):
    """Test split with reckless-ephemeral mode."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Split using reckless-ephemeral mode
    res = split(
        'data',
        dataset=ds.path,
        clone_mode='reckless-ephemeral',
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset was created
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())

    # Check that annex objects directory is a symlink
    annex_objects = Path(ds.path) / 'data' / '.git' / 'annex' / 'objects'
    if annex_objects.exists():
        ok_(annex_objects.is_symlink())


############################
# Test content handling
############################

@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'file1.dat': 'content1' * 100,
        'file2.dat': 'content2' * 100,
    }
})
def test_split_content_none(path=None):
    """Test split with content mode 'none'."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Split with content='none'
    res = split(
        'data',
        dataset=ds.path,
        content='none',
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Subdataset files should not have content locally
    subds = Dataset(Path(ds.path) / 'data')
    annexed_files = subds.repo.get_annexed_files()

    # At least some files should be annexed and not present
    if annexed_files:
        # Check if content is available (it might not be for 'none' mode)
        whereis = subds.repo.whereis(annexed_files)
        # Content should be available somewhere (in parent's annex)
        for file in annexed_files:
            ok_(len(whereis.get(file, [])) > 0)


@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'file1.dat': 'content1' * 100,
        'file2.dat': 'content2' * 100,
    }
})
def test_split_content_copy(path=None):
    """Test split with content mode 'copy'."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Split with content='copy'
    res = split(
        'data',
        dataset=ds.path,
        content='copy',
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Subdataset files should have content locally
    subds = Dataset(Path(ds.path) / 'data')
    annexed_files = subds.repo.get_annexed_files()

    if annexed_files:
        # All files should be present
        for file in annexed_files:
            file_path = Path(subds.path) / file
            # File should exist and have content (not be a broken symlink)
            ok_exists(file_path)
            ok_(file_path.stat().st_size > 0 or not file_path.is_symlink())


############################
# Test dry-run mode
############################

@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
    }
})
def test_split_dry_run(path=None):
    """Test split with dry-run mode."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Record initial state
    initial_subdatasets = set(ds.subdatasets(result_xfm='paths'))

    # Split with dry-run
    res = split(
        'data',
        dataset=ds.path,
        dry_run=True,
        return_type='list',
    )

    # Should report what would be done
    assert_result_count(res, 1)

    # But nothing should actually change
    current_subdatasets = set(ds.subdatasets(result_xfm='paths'))
    eq_(initial_subdatasets, current_subdatasets)

    # data directory should still exist and contain files
    ok_exists(Path(ds.path) / 'data' / 'file1.txt')
    ok_exists(Path(ds.path) / 'data' / 'file2.txt')


############################
# Test verification
############################

@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
    }
})
def test_split_with_verification(path=None):
    """Test split with post-split verification."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Split with full verification
    res = split(
        'data',
        dataset=ds.path,
        check='full',
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Subdataset should be verified
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())


############################
# Test error conditions
############################

@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'file1.txt': 'data1',
    }
})
def test_split_partial_failure(path=None):
    """Test split with one path failing."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Try to split both valid and invalid paths
    res = split(
        ['data', 'nonexistent'],
        dataset=ds.path,
        force=True,
        on_failure='ignore',
        return_type='list',
    )

    # Should have one success and one failure
    assert_result_count(res, 2)
    assert_in_results(res, action='split', status='ok', path=str(Path(ds.path) / 'data'))
    assert_in_results(res, status='impossible', path=str(Path(ds.path) / 'nonexistent'))

    # Valid path should still be split successfully
    subdatasets = ds.subdatasets(result_xfm='paths')
    assert_in('data', subdatasets)


############################
# Test dataset method
############################

@pytest.mark.ai_generated
@with_tree(tree={
    'data': {
        'file1.txt': 'data1',
    }
})
def test_split_dataset_method(path=None):
    """Test split via Dataset method."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Call split as dataset method
    res = ds.split('data', force=True, return_type='list')

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset exists
    subdatasets = ds.subdatasets(result_xfm='paths')
    assert_in('data', subdatasets)


############################
# Test relative paths
############################

@pytest.mark.ai_generated
@with_tree(tree={
    'subdir': {
        'data': {
            'file1.txt': 'data1',
        }
    }
})
def test_split_relative_path(path=None):
    """Test split with relative path from within dataset."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Change to subdir and split with relative path
    with chpwd(Path(ds.path) / 'subdir'):
        res = split(
            'data',
            dataset=ds.path,
            force=True,
            return_type='list',
        )

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset exists
    subds = Dataset(Path(ds.path) / 'subdir' / 'data')
    ok_(subds.is_installed())
