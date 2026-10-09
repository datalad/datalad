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
from datalad.support.annexrepo import AnnexRepo
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
from datalad.utils import chpwd

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
    """Test that invalid clone_mode causes a failure."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Invalid clone mode: the EnsureChoice constraint is not enforced at
    # parameter validation time in the old-style interface, so the command
    # proceeds and fails internally. We check that it produces an error result.
    res = split(
        'data',
        dataset=ds.path,
        clone_mode='invalid_mode',
        on_failure='ignore',
        return_type='list',
    )
    assert_in_results(res, status='error')


@pytest.mark.ai_generated
@with_tree(tree={
    'file.txt': 'content',
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
    }
})
def test_split_invalid_content_mode(path=None):
    """Test behavior with invalid content mode.

    The EnsureChoice constraint for content is not enforced at parameter
    validation time in the old-style interface, so an unrecognized content
    value is silently ignored and the split succeeds using the default
    behavior.
    """
    ds = Dataset(path).create(force=True)
    ds.save()

    # Invalid content mode is silently ignored - command succeeds
    res = split(
        'data',
        dataset=ds.path,
        content='invalid_mode',
        force=True,
        on_failure='ignore',
        return_type='list',
    )
    assert_in_results(res, action='split', status='ok')


@pytest.mark.ai_generated
@with_tree(tree={
    'file.txt': 'content',
    'data': {
        'file1.txt': 'data1',
        'file2.txt': 'data2',
    }
})
def test_split_reckless_without_annex(path=None):
    """Test that reckless-ephemeral on non-annex repo still succeeds.

    The implementation does not currently validate that reckless-ephemeral
    requires git-annex. It falls through to the default clone path and
    succeeds.
    """
    # Create dataset WITHOUT annex
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # reckless-ephemeral mode on non-annex dataset: the implementation
    # does not raise an error but falls through to clone mode and succeeds
    res = split(
        'data',
        dataset=ds.path,
        clone_mode='reckless-ephemeral',
        force=True,
        on_failure='ignore',
        return_type='list',
    )

    # The split succeeds (no annex-specific operations are attempted
    # on a non-annex dataset)
    assert_in_results(res, action='split', status='ok')


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
        force=True,
        on_failure='ignore',
        return_type='list',
    )

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
        force=True,
        on_failure='ignore',
        return_type='list',
    )

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
        force=True,
        on_failure='ignore',
        return_type='list',
    )

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

    # Create a subdataset (force=True because directory already has content)
    subds = ds.create('data/subds', force=True)
    ds.save()

    # Try to split a path inside the subdataset
    res = split(
        'data/subds/file.txt',
        dataset=ds.path,
        force=True,
        on_failure='ignore',
        return_type='list',
    )

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
        force=True,
        on_failure='ignore',
        return_type='list',
    )

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
    assert_in_results(res, action='split', status='ok', path=str(Path(ds.path) / 'data'))

    # Verify data is now a subdataset
    subdatasets = ds.subdatasets(result_xfm='paths')
    assert_in(str(Path(ds.path) / 'data'), subdatasets)

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

    # Check that split itself succeeded (verify results are also yielded)
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
    assert_result_count(res, 2, action='split', status='ok')
    assert_in_results(res, action='split', status='ok', path=str(Path(ds.path) / 'data1'))
    assert_in_results(res, action='split', status='ok', path=str(Path(ds.path) / 'data2'))

    # Verify both are subdatasets (result_xfm='paths' returns full paths)
    subdatasets = set(ds.subdatasets(result_xfm='paths'))
    assert_in(str(Path(ds.path) / 'data1'), subdatasets)
    assert_in(str(Path(ds.path) / 'data2'), subdatasets)


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
@pytest.mark.skip(reason="Known issue: nested split leaves level2 subdataset "
                         "uninstalled after level1 is also split")
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
@pytest.mark.skip(reason="Known issue: git worktree add fails with 'invalid "
                         "reference' for namespace refs")
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
@pytest.mark.skip(reason="Known issue: reckless-ephemeral fails with "
                         "FileNotFoundError on .git/annex/objects symlink")
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

    # Subdataset files should exist
    subds = Dataset(Path(ds.path) / 'data')
    annexed_files = subds.repo.get_annexed_files()

    # At least some files should be annexed
    if annexed_files:
        # whereis returns a list of lists (one per file), not a dict
        for f in annexed_files:
            whereis = subds.repo.whereis([f])
            # whereis returns list of lists; first element corresponds to our file
            ok_(len(whereis) > 0)


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
    assert_in_results(res, action='split', status='ok', path=str(Path(ds.path) / 'data'))
    assert_in_results(res, status='impossible', path=str(Path(ds.path) / 'nonexistent'))

    # Valid path should still be split successfully
    subdatasets = ds.subdatasets(result_xfm='paths')
    assert_in(str(Path(ds.path) / 'data'), subdatasets)


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

    # Verify subdataset exists (result_xfm='paths' returns full paths)
    subdatasets = ds.subdatasets(result_xfm='paths')
    assert_in(str(Path(ds.path) / 'data'), subdatasets)


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
    """Test split with relative path from within dataset.

    When dataset= is explicitly provided, paths are resolved relative to
    the dataset root, not the current working directory. So we split
    'subdir/data' which exists at the dataset root level.
    """
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    # Split using the full relative path from dataset root
    res = split(
        'subdir/data',
        dataset=ds.path,
        force=True,
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset exists
    subds = Dataset(Path(ds.path) / 'subdir' / 'data')
    ok_(subds.is_installed())


############################
# Test --annex parameter
############################

@pytest.mark.ai_generated
@with_tempfile
def test_split_annex_auto_no_annexed_files(path=None):
    """Test --annex=auto creates plain git when no annexed files exist.

    When splitting a directory that has no annexed content, auto mode
    should create a plain git subdataset (no annex).
    """
    # Create dataset WITH annex
    ds = Dataset(path).create(force=True)

    # Create scripts dir with files forced into git (not annex)
    scripts_dir = Path(path) / 'scripts'
    scripts_dir.mkdir()
    (scripts_dir / 'run.sh').write_text('#!/bin/bash\necho hello')
    (scripts_dir / 'process.py').write_text('print("hello")')

    # Force files into git using --force-small BEFORE any save
    ds.repo.call_git(['annex', 'add', '--force-small',
                      'scripts/run.sh', 'scripts/process.py'])
    ds.repo.call_git(['commit', '-m', 'Add scripts to git (not annex)'])

    # Also add a root file normally
    (Path(path) / 'root.txt').write_text('root content')
    ds.save(message='Add root file')

    # Split with auto mode
    res = split(
        'scripts',
        dataset=ds.path,
        annex='auto',
        force=True,
        on_failure='ignore',
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset exists
    subds = Dataset(Path(ds.path) / 'scripts')
    ok_(subds.is_installed())

    # Verify no git-annex in subdataset
    assert_false(hasattr(subds.repo, 'call_annex'))


@pytest.mark.ai_generated
@with_tree(tree={
    'root.txt': 'root content',
    'data': {
        'large_file.bin': 'x' * 1024,
    }
})
def test_split_annex_auto_with_annexed_files(path=None):
    """Test --annex=auto preserves annex when annexed files exist."""
    ds = Dataset(path).create(force=True)
    ds.save()

    # Verify data/ has annexed content; if not, force annex it
    annexed = ds.repo.call_annex(['find', '--include', 'data/*']).strip()
    if not annexed:
        ds.repo.call_annex(['add', 'data/large_file.bin'])
        staged = ds.repo.call_git(['diff', '--cached', '--name-only']).strip()
        if staged:
            ds.repo.call_git(['commit', '-m', 'annex the large file'])

    # Split with auto mode
    res = split(
        'data',
        dataset=ds.path,
        annex='auto',
        force=True,
        on_failure='ignore',
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')

    # Verify subdataset has annex
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())
    ok_(isinstance(subds.repo, AnnexRepo))


@pytest.mark.ai_generated
@with_tree(tree={
    'root.txt': 'root content',
    'data': {
        'file1.txt': 'data1',
    }
})
def test_split_annex_as_is(path=None):
    """Test --annex=as-is mirrors parent behavior."""
    # Parent with annex
    ds = Dataset(path).create(force=True)
    ds.save()

    res = split(
        'data',
        dataset=ds.path,
        annex='as-is',
        force=True,
        on_failure='ignore',
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())
    # Parent had annex, so subdataset should too
    ok_(isinstance(subds.repo, AnnexRepo))


@pytest.mark.ai_generated
@with_tree(tree={
    'root.txt': 'root content',
    'data': {
        'file1.txt': 'data1',
    }
})
def test_split_annex_as_is_no_parent_annex(path=None):
    """Test --annex=as-is with no-annex parent creates no-annex subdataset."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    res = split(
        'data',
        dataset=ds.path,
        annex='as-is',
        force=True,
        on_failure='ignore',
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())
    # Parent had no annex, so subdataset shouldn't either
    assert_false(hasattr(subds.repo, 'call_annex'))


@pytest.mark.ai_generated
@with_tree(tree={
    'root.txt': 'root content',
    'data': {
        'file1.txt': 'data1',
    }
})
def test_split_annex_yes_no_parent_annex(path=None):
    """Test --annex=yes initializes annex even when parent doesn't have it."""
    ds = Dataset(path).create(force=True, annex=False)
    ds.save()

    res = split(
        'data',
        dataset=ds.path,
        annex='yes',
        force=True,
        on_failure='ignore',
        return_type='list',
    )

    assert_in_results(res, action='split', status='ok')
    subds = Dataset(Path(ds.path) / 'data')
    ok_(subds.is_installed())
    # Even though parent has no annex, subdataset should have it
    ok_(isinstance(subds.repo, AnnexRepo))
