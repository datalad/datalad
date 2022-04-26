# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad unlock

"""

__docformat__ = 'restructuredtext'

from datalad.api import (
    clone,
    create,
    unlock,
)
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    InsufficientArgumentsError,
    NoDatasetFound,
)
from datalad.tests.utils_pytest import (
    assert_cwd_unchanged,
    assert_false,
    assert_in_results,
    assert_not_in_results,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    chpwd,
    eq_,
    getpwd,
    skip_if_root,
    slow,
    with_tempfile,
    with_tree,
)
from datalad.utils import Path


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile
def test_unlock_raises(path=None, path2=None, path3=None):

    # make sure, we are not within a dataset:
    _cwd = getpwd()
    chpwd(path)

    # no dataset and no path:
    assert_raises(InsufficientArgumentsError,
                  unlock, dataset=None, path=None)
    # no dataset and path not within a dataset:
    assert_raises(NoDatasetFound,
                  unlock, dataset=None, path=path2)

    create(path=path, annex=False)
    ds = Dataset(path)
    # no complaints
    ds.unlock()

    # make it annex, but call unlock with invalid path:
    (ds.pathobj / ".noannex").unlink()
    AnnexRepo(path, create=True)

    # One that doesn't exist.
    res = ds.unlock(path="notexistent.txt", result_xfm=None,
                    on_failure='ignore', return_type='item-or-list')
    eq_(res['message'], "path does not exist")

    # And one that isn't associated with a dataset.
    assert_in_results(
        ds.unlock(path=path2, on_failure="ignore"),
        status="error",
        message=("path not underneath the reference dataset %s", ds.path))

    chpwd(_cwd)


# Note: As root there is no actual lock/unlock.
#       Therefore don't know what to test for yet.
# https://github.com/datalad/datalad/pull/3975/checks?check_run_id=369789027#step:8:134
@slow  # 12sec on Yarik's laptop
@skip_if_root
@with_tempfile
@with_tempfile
def test_unlock(origpath=None, clonepath=None):
    origds = Dataset(origpath).create()
    (origds.pathobj / 'test-annex.dat').write_text('some text')
    origds.save()

    ds = clone(origpath, clonepath)
    repo = ds.repo
    testfile = ds.pathobj / 'test-annex.dat'

    managed_branch = repo.is_managed_branch()
    if not managed_branch:
        # file is currently locked:
        # TODO: use get_annexed_files instead of hardcoded filename
        assert_raises(IOError, open, testfile, "w")

    # Note: In V6+ we can unlock even if the file's content isn't present, but
    # doing so when unlock() is called with no paths isn't consistent with the
    # current behavior when an explicit path is given (it doesn't unlock) or
    # with the behavior in V5, so we don't do it.

    # Unlocking the dataset without an explicit path does not fail if there
    # are files without content.
    eq_(ds.unlock(path=None, on_failure="ignore"), [])
    eq_(ds.unlock(path=[], on_failure="ignore"), [])
    # cannot unlock without content (annex get wasn't called)
    assert_in_results(
        ds.unlock(path="test-annex.dat", on_failure="ignore"),
        path=str(testfile),
        status="impossible")

    repo.get('test-annex.dat')
    result = ds.unlock()
    if not managed_branch:
        # with managed repos `unlock` is not talking
        assert_result_count(result, 1)
        assert_in_results(result, path=str(testfile), status='ok')

    testfile.write_text("change content")

    ds.save(
        'test-annex.dat',
        message="edit 'test-annex.dat' via unlock and lock it again")

    if not managed_branch:
        # after commit, file is locked again:
        assert_raises(IOError, open, testfile, "w")

    # content was changed:
    eq_("change content", testfile.read_text())

    # unlock again, this time more specific:
    result = ds.unlock(path='test-annex.dat')
    if not managed_branch:
        # with managed repos `unlock` is not talking
        assert_result_count(result, 1)
        assert_in_results(result, path=str(testfile), status='ok')

    testfile.write_text("change content again")

    ds.save(
        'test-annex.dat',
        message="edit 'test-annex.dat' via unlock and lock it again")

    # TODO:
    # BOOOM: test-annex.dat writeable in V6!
    # Why the hell is this different than the first time we wrote to the file
    # and locked it again?
    # Also: After opening the file is empty.

    if not managed_branch:
        # after commit, file is locked again:
        assert_raises(IOError, open, testfile, "w")

    # content was changed:
    eq_("change content again", testfile.read_text())


@with_tree(tree={"dir": {"a": "a", "b": "b"}})
def test_unlock_directory(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    ds.unlock(path="dir")
    dirpath = Path("dir")
    dirpath_abs = Path(ds.pathobj / "dir")

    # On adjusted branches (for the purposes of this test, crippled
    # filesystems), the files were already unlocked and the committed state is
    # the unlocked pointer file.
    is_managed_branch = ds.repo.is_managed_branch()
    if is_managed_branch:
        assert_repo_status(ds.path)
    else:
        assert_repo_status(ds.path, modified=[dirpath / "a", dirpath / "b"])
    ds.save()
    ds.drop(str(dirpath / "a"), reckless='kill')
    assert_false(ds.repo.file_has_content(str(dirpath / "a")))

    # Unlocking without an explicit non-directory path doesn't fail if one of
    # the directory's files doesn't have content.
    res = ds.unlock(path="dir")
    assert_not_in_results(res, action="unlock",
                          path=str(dirpath_abs / "a"))
    if is_managed_branch:
        assert_not_in_results(res, action="unlock",
                              path=str(dirpath_abs / "b"))
    else:
        assert_in_results(res, action="unlock", status="ok",
                          path=str(dirpath_abs / "b"))
        assert_repo_status(ds.path, modified=[dirpath / "b"])

    # If we explicitly provide a path that lacks content, we get a result
    # for it.
    assert_in_results(ds.unlock(path=dirpath / "a", on_failure="ignore"),
                      action="unlock", status="impossible",
                      path=str(dirpath_abs / "a"))


@with_tree(tree={"untracked": "untracked",
                 "regular_git": "regular_git",
                 "already_unlocked": "already_unlocked"})
def test_unlock_cant_unlock(path=None):
    ds = Dataset(path).create(force=True)
    ds.save(path="regular_git", to_git=True)
    ds.save(path="already_unlocked")
    ds.unlock(path="already_unlocked")
    assert_repo_status(
        ds.path,
        # See managed branch note in previous test_unlock_directory.
        modified=[] if ds.repo.is_managed_branch() else ["already_unlocked"],
        untracked=["untracked"])
    expected = {"regular_git": "notneeded",
                "untracked": "impossible"}
    # Don't add "already_unlocked" in v6+ because unlocked files are still
    # reported as having content and still passed to unlock. If we can
    # reliably distinguish v6+ unlocked files in status's output, we should
    # consider reporting a "notneeded" result.
    for f, status in expected.items():
        assert_in_results(
            ds.unlock(path=f, on_failure="ignore"),
            action="unlock",
            status=status,
            path=str(ds.pathobj / f))


@with_tree(tree={'subdir': {'sub': {}}})
def test_unlock_gh_5456(path=None):
    path = Path(path)
    unrelated_super = Dataset(path).create(annex=False, force=True)
    ds = Dataset(path / 'subdir' / 'sub').create()
    ds.unlock('.')
