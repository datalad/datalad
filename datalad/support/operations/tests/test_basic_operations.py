# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

from datalad.support.operations.operations_local import (
    LocalOperation,
)
from datalad.support.operations.operations_remote import RemoteOperation
from datalad.support.exceptions import CommandError
from datalad.utils import (
    Path,
    PurePath
)
from datalad.tests.utils import (
    assert_raises,
    assert_false,
    assert_repo_status,
    with_tempfile,
    with_tree,
    ok_,
    ok_exists,
    ok_file_has_content,
    create_tree,
    eq_,
    neq_,
    assert_status,
    assert_result_count,
    assert_in,
    assert_in_results,
    assert_not_in,
    swallow_logs,
    swallow_outputs,
    known_failure_githubci_win,
    known_failure_appveyor,
    known_failure_windows,
    slow,
    with_testrepos,
    OBSCURE_FILENAME,
    SkipTest,
    has_symlink_capability,
    skip_ssh
)


@with_tempfile(mkdir=True)
@with_tempfile
def test_make_directory_local(cwd, path):
    cwd = Path(cwd)
    path = Path(path)
    deep = path / 'deeper' / OBSCURE_FILENAME

    ops = LocalOperation(cwd=cwd)

    # raise on non-existing parents:
    assert_raises(FileNotFoundError, ops.make_directory, deep)
    # doesn't raise:
    ops.make_directory(path)
    assert path.is_dir()
    # raise on existing target:
    assert_raises(FileExistsError, ops.make_directory, path)
    # doesn't raise:
    ops.make_directory(deep, force=True)
    assert deep.is_dir()
    # relative resolves based on cwd:
    rel_path = Path('another')
    ops.make_directory(rel_path)
    assert (cwd / rel_path).is_dir()


@skip_ssh
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile
def test_make_directory_remote(cwd, remote_cwd, path):
    cwd = Path(cwd)
    remote_cwd = Path(remote_cwd)
    path = Path(path)
    deep = path / 'deeper' / OBSCURE_FILENAME

    # NOTE, that "datalad-test" is supposed to be localhost. So, absolute paths
    # match on "local" and "remote" end.
    ops = RemoteOperation("ssh://datalad-test:",
                          cwd=cwd,
                          remote_cwd=remote_cwd)

    # raise on non-existing parents:
    assert_raises(CommandError, ops.make_directory, deep)
    # doesn't raise:
    ops.make_directory(path)
    ok_(path.is_dir())
    # raise on existing target:
    assert_raises(CommandError, ops.make_directory, path)
    # doesn't raise:
    ops.make_directory(deep, force=True)
    ok_(deep.is_dir())
    # relative resolves based on cwd:
    rel_path = Path('another')
    ops.make_directory(rel_path)
    ok_((remote_cwd / rel_path).is_dir())
    assert_false((cwd / rel_path).is_dir())


@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_exists_local(file_path, dir_path, link_path, cwd):
    file_path = Path(file_path)
    dir_path = Path(dir_path)
    link_path = Path(link_path)
    cwd = Path(cwd)
    ops = LocalOperation(cwd=cwd)

    # regular file:
    assert_false(ops.exists(file_path))
    file_path.write_text('some')
    ok_(ops.exists(file_path))

    # symlink
    if has_symlink_capability():
        assert_false(ops.exists(link_path))
        link_path.symlink_to('broken')
        ok_(ops.exists(link_path))
        ops.remove(link_path)
        link_path.symlink_to(file_path)
        ok_(ops.exists(link_path))

    # directory
    assert_false(ops.exists(dir_path))
    ops.make_directory(dir_path)
    ok_(ops.exists(dir_path))

    # relative
    assert_false(ops.exists(Path('relative')))
    (cwd / 'relative').write_text('content')
    ok_(ops.exists(Path('relative')))


@skip_ssh
@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_exists_remote(file_path, dir_path, link_path, cwd, remote_cwd):
    file_path = Path(file_path)
    dir_path = Path(dir_path)
    link_path = Path(link_path)
    cwd = Path(cwd)
    remote_cwd = Path(remote_cwd)
    # NOTE, that "datalad-test" is supposed to be localhost. So, absolute paths
    # match on "local" and "remote" end.
    ops = RemoteOperation("ssh://datalad-test:",
                          cwd=cwd,
                          remote_cwd=remote_cwd)

    # regular file:
    assert_false(ops.exists(file_path))
    file_path.write_text('some')
    ok_(ops.exists(file_path))

    # symlink
    if has_symlink_capability():
        assert_false(ops.exists(link_path))
        link_path.symlink_to('broken')
        ok_(ops.exists(link_path))
        ops.remove(link_path)
        link_path.symlink_to(file_path)
        ok_(ops.exists(link_path))

    # directory
    assert_false(ops.exists(dir_path))
    ops.make_directory(dir_path)
    ok_(ops.exists(dir_path))

    # relative
    assert_false(ops.exists(Path('relative')))
    (remote_cwd / 'relative').write_text('content')
    ok_(ops.exists(Path('relative')))


@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_remove_local(dir_path, link_path, cwd):

    dir_path = Path(dir_path)
    link_path = Path(link_path)
    cwd = Path(cwd)
    ops = LocalOperation(cwd=cwd)

    # non-existent doesn't raise:
    ops.remove(dir_path)
    ops.make_directory(dir_path)
    ok_(ops.exists(dir_path))
    # empty directory
    ops.remove(dir_path)
    assert_false(ops.exists(dir_path))
    # recreate for a tree
    ops.make_directory(dir_path)
    ok_(ops.exists(dir_path))
    underneath = (dir_path / 'some')
    underneath.write_text('content')
    # non-empty dir w/o recursive
    assert_raises(OSError, ops.remove(dir_path))
    ok_(ops.exists(dir_path))
    # non-empty dir w/ recursive
    ops.remove(dir_path, recursive=True)
    assert_false(ops.exists(dir_path))

    if has_symlink_capability():
        # remove a link
        link_path.symlink_to('broken')
        ops.remove(link_path)

    # relative to correct base:
    relative = cwd / OBSCURE_FILENAME
    relative.write_text("doesn't matter")
    ok_(ops.exists(relative))
    ops.remove(Path(OBSCURE_FILENAME))
    assert_false(ops.exists(relative))


@skip_ssh
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_remove_remote(dir_path, link_path, cwd, remote_cwd):

    dir_path = Path(dir_path)
    link_path = Path(link_path)
    cwd = Path(cwd)
    remote_cwd = Path(remote_cwd)

    # NOTE, that "datalad-test" is supposed to be localhost. So, absolute paths
    # match on "local" and "remote" end.
    ops = RemoteOperation("ssh://datalad-test:",
                          cwd=cwd,
                          remote_cwd=remote_cwd)

    # non-existent doesn't raise:
    ops.remove(dir_path)
    ops.make_directory(dir_path)
    ok_(ops.exists(dir_path))
    # empty directory
    ops.remove(dir_path)
    assert_false(ops.exists(dir_path))
    # recreate for a tree
    ops.make_directory(dir_path)
    ok_(ops.exists(dir_path))
    underneath = (dir_path / 'some')
    underneath.write_text('content')
    # non-empty dir w/o recursive
    assert_raises(CommandError, ops.remove(dir_path))
    ok_(ops.exists(dir_path))
    # non-empty dir w/ recursive
    ops.remove(dir_path, recursive=True)
    assert_false(ops.exists(dir_path))

    if has_symlink_capability():
        # remove a link
        link_path.symlink_to('broken')
        ops.remove(link_path)

    # relative to correct base:
    relative = remote_cwd / OBSCURE_FILENAME
    relative.write_text("doesn't matter")
    ok_(ops.exists(relative))
    ops.remove(Path(OBSCURE_FILENAME))
    assert_false(ops.exists(relative))


@with_tempfile(mkdir=True)
def test_rename_local(cwd):
    cwd = Path(cwd)
    ops = LocalOperation(cwd=cwd)

    # rename regular file
    file_path = cwd / "first"
    file_path.write_text("first")
    ops.rename(Path("first"), Path("second"))
    ok_(ops.exists(Path("second")))
    assert_false(ops.exists(Path("first")))
    eq_("first", (cwd / "second").read_text())

    # rename dir
    dir_path = cwd / "dir"
    ops.make_directory(dir_path)
    dir_path.is_dir()
    ops.rename(Path("dir"), Path(OBSCURE_FILENAME))
    ok_(ops.exists(Path(OBSCURE_FILENAME)))
    (cwd / OBSCURE_FILENAME).is_dir()
    assert_false(ops.exists(dir_path))

    if has_symlink_capability():
        # rename symlink
        link_path = cwd / "somelink"
        link_path.symlink_to('broken')
        ok_(ops.exists(link_path))
        ops.rename(link_path, Path("newlink"))
        ok_(ops.exists(Path("newlink")))
        assert_false(ops.exists(link_path))


@skip_ssh
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_rename_remote(cwd, remote_cwd):
    cwd = Path(cwd)
    remote_cwd = Path(remote_cwd)

    # NOTE, that "datalad-test" is supposed to be localhost. So, absolute paths
    # match on "local" and "remote" end.
    ops = RemoteOperation("ssh://datalad-test:",
                          cwd=cwd,
                          remote_cwd=remote_cwd)

    # rename regular file
    file_path = remote_cwd / "first"
    file_path.write_text("first")
    ops.rename(Path("first"), Path("second"))
    ok_(ops.exists(Path("second")))
    assert_false(ops.exists(Path("first")))
    eq_("first", (remote_cwd / "second").read_text())

    # rename dir
    dir_path = remote_cwd / "dir"
    ops.make_directory(dir_path)
    dir_path.is_dir()
    ops.rename(Path("dir"), Path(OBSCURE_FILENAME))
    ok_(ops.exists(Path(OBSCURE_FILENAME)))
    (remote_cwd / OBSCURE_FILENAME).is_dir()
    assert_false(ops.exists(dir_path))

    if has_symlink_capability():
        # rename symlink
        link_path = remote_cwd / "somelink"
        link_path.symlink_to('broken')
        ok_(ops.exists(link_path))
        ops.rename(link_path, Path("newlink"))
        ok_(ops.exists(Path("newlink")))
        assert_false(ops.exists(link_path))
