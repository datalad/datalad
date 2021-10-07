# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad unlock

"""

__docformat__ = 'restructuredtext'

from os.path import join as opj


from datalad.distribution.dataset import Dataset
from datalad.api import (
    create,
    unlock,
)
from datalad.utils import Path
from datalad.support.exceptions import (
    InsufficientArgumentsError,
    NoDatasetFound,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import (
    with_tempfile,
    assert_false,
    assert_raises,
    assert_repo_status,
    eq_,
    getpwd,
    chpwd,
    assert_cwd_unchanged,
    with_testrepos,
    with_tree,
    skip_if_root,
    slow,
    assert_in_results,
    assert_not_in_results,
    assert_result_count,
    known_failure_githubci_win,
    known_failure_windows,
)


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile
def test_unlock_raises(path, path2, path3):

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
        message="path not underneath this dataset")

    chpwd(_cwd)


# Note: As root there is no actual lock/unlock.
#       Therefore don't know what to test for yet.
# https://github.com/datalad/datalad/pull/3975/checks?check_run_id=369789027#step:8:134
@slow  # 12sec on Yarik's laptop
@known_failure_windows
@skip_if_root
@with_testrepos('.*annex.*', flavors=['clone'])
def test_unlock(path):

    ds = Dataset(path)

    # file is currently locked:
    # TODO: use get_annexed_files instead of hardcoded filename
    assert_raises(IOError, open, opj(path, 'test-annex.dat'), "w")

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
        path=opj(path, "test-annex.dat"),
        status="impossible")

    ds.repo.get('test-annex.dat')
    result = ds.unlock()
    assert_result_count(result, 1)
    assert_in_results(result, path=opj(ds.path, 'test-annex.dat'), status='ok')

    with open(opj(path, 'test-annex.dat'), "w") as f:
        f.write("change content")

    ds.repo.add('test-annex.dat')
    # TODO: RF: make 'lock' a command as well
    # re-lock to further on have a consistent situation with V5:
    ds.repo.call_annex(['lock'], files=['test-annex.dat'])
    ds.repo.commit("edit 'test-annex.dat' via unlock and lock it again")

    # after commit, file is locked again:
    assert_raises(IOError, open, opj(path, 'test-annex.dat'), "w")

    # content was changed:
    with open(opj(path, 'test-annex.dat'), "r") as f:
        eq_("change content", f.read())

    # unlock again, this time more specific:
    result = ds.unlock(path='test-annex.dat')
    assert_result_count(result, 1)

    assert_in_results(result, path=opj(ds.path, 'test-annex.dat'), status='ok')

    with open(opj(path, 'test-annex.dat'), "w") as f:
        f.write("change content again")

    ds.repo.add('test-annex.dat')
    # TODO: RF: make 'lock' a command as well
    # re-lock to further on have a consistent situation with V5:
    ds.repo.call_annex(['lock'], files=['test-annex.dat'])
    ds.repo.commit("edit 'test-annex.dat' via unlock and lock it again")

    # TODO:
    # BOOOM: test-annex.dat writeable in V6!
    # Why the hell is this different than the first time we wrote to the file
    # and locked it again?
    # Also: After opening the file is empty.

    # after commit, file is locked again:
    assert_raises(IOError, open, opj(path, 'test-annex.dat'), "w")

    # content was changed:
    with open(opj(path, 'test-annex.dat'), "r") as f:
        eq_("change content again", f.read())


@known_failure_githubci_win
@with_tree(tree={"dir": {"a": "a", "b": "b"}})
def test_unlock_directory(path):
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
    ds.drop(str(dirpath / "a"), check=False)
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
def test_unlock_cant_unlock(path):
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
def test_unlock_gh_5456(path):
    path = Path(path)
    unrelated_super = Dataset(path).create(annex=False, force=True)
    ds = Dataset(path / 'subdir' / 'sub').create()
    ds.unlock('.')
