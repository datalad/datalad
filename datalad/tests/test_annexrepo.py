# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class AnnexRepo

Note: There's not a lot to test by now.

"""

import os, platform

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_equal, assert_false
from nose import SkipTest
from git.exc import GitCommandError

from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, ignore_nose_capturing_stdout, \
    on_windows, ok_clean_git_annex_proxy
from datalad.support.exceptions import CommandNotAvailableError, FileInGitError, FileNotInAnnexError

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos
@with_tempfile
def test_AnnexRepo_instance_from_clone(src, dst):

    ar = AnnexRepo(dst, src)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.git', 'annex')))

    # do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    # and therefore can't clone to `dst`
    assert_raises(GitCommandError, AnnexRepo, dst, src)


# TODO: enable local as well whenever/if ever submodule issue gets resolved for windows
@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)  # 'network' doesn't make sense for this test
def test_AnnexRepo_instance_from_existing(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_instance_brand_new(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=['network'])
@with_tempfile
def test_AnnexRepo_get(src, dst):

    ar = AnnexRepo(dst, src)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")

    cwd = os.getcwd()
    os.chdir(dst)
    testfile = 'test-annex.dat'
    if platform.system() != "Windows":
        assert_raises(IOError, open, testfile, 'r')
        # If get has nothing to do, we can't test it.
        # TODO: on crippled filesystem, the file is actually present before getting!
        # So, what to test? Just skip for now.
        # Actually, could test content!

    ar.annex_get([testfile])
    f = open(testfile, 'r')
    assert_equal(f.readlines(), ['123\n'], "test-annex.dat's content doesn't match.")

    os.chdir(cwd)


@assert_cwd_unchanged
@with_testrepos
@with_tempfile
def test_AnnexRepo_crippled_filesystem(src, dst):
    # TODO: This test is rudimentary, since platform not really determines filesystem.
    # For now this should work for the buildbots. Nevertheless: Find a better way to test it.

    ar = AnnexRepo(dst, src)
    if on_windows:
        assert_true(ar.is_crippled_fs(), "Detected non-crippled filesystem on windows.")
    else:
        assert_false(ar.is_crippled_fs(), "Detected crippled filesystem on non-windows.")


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
def test_AnnexRepo_is_direct_mode(path):

    ar = AnnexRepo(path)
    dm = ar.is_direct_mode()
    if on_windows:
        assert_true(dm, "AnnexRepo.is_direct_mode() returned false on windows.")
    else:
        assert_false(dm, "AnnexRepo.is_direct_mode() returned true on non-windows")
    # Note: In fact this test isn't totally correct, since you always can switch to direct mode.
    # So not being on windows doesn't necessarily mean we are in indirect mode. But how to obtain a "ground truth"
    # to test against, without making test of is_direct_mode() dependent on set_direct_mode() and vice versa?


@assert_cwd_unchanged
@with_testrepos
@with_tempfile
def test_AnnexRepo_set_direct_mode(src, dst):

    ar = AnnexRepo(dst, src)
    ar.set_direct_mode(True)
    assert_true(ar.is_direct_mode(), "Switching to direct mode failed.")
    if ar.is_crippled_fs():
        assert_raises(CommandNotAvailableError, ar.set_direct_mode, False)
        assert_true(ar.is_direct_mode(), "Indirect mode on crippled fs detected. Shouldn't be possible.")
    else:
        ar.set_direct_mode(False)
        assert_false(ar.is_direct_mode(), "Switching to indirect mode failed.")


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_annex_add(src, annex_path):

    ar = AnnexRepo(annex_path, src)
    cwd = os.getcwd()
    os.chdir(annex_path)

    filename = 'file_to_annex.dat'
    f = open(filename, 'w')
    f.write("What to write?")
    f.close()
    ar.annex_add([filename])
    if not ar.is_direct_mode():
        assert_true(os.path.islink(filename), "Annexed file is not a link.")
    else:
        assert_false(os.path.islink(filename), "Annexed file is link in direct mode.")
        # TODO: How to test the file was added in direct mode?
        # May be this will need 'git annex find' or sth. to be implemented.

    os.chdir(cwd)


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_annex_proxy(src, annex_path):

    ar = AnnexRepo(annex_path, src)
    ar.set_direct_mode(True)
    ok_clean_git_annex_proxy(path=annex_path)


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_get_file_key(src, annex_path):

    ar = AnnexRepo(annex_path, src)
    cwd = os.getcwd()
    os.chdir(annex_path)

    # test-annex.dat should return the correct key:
    assert_equal(ar.get_file_key("test-annex.dat"), 'SHA256E-s4--181210f8f9c779c26da1d9b2075bde0127302ee0e3fca38c9a83f5b1dd8e5d3b.dat')

    # test.dat is actually in git
    # should raise Exception; also test for polymorphism
    assert_raises(IOError, ar.get_file_key, "test.dat")
    assert_raises(FileNotInAnnexError, ar.get_file_key, "test.dat")
    assert_raises(FileInGitError, ar.get_file_key, "test.dat")

    # filenotpresent.wtf doesn't even exist
    assert_raises(IOError, ar.get_file_key, "filenotpresent.wtf")

    os.chdir(cwd)


@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_file_has_content(src, annex_path):

    ar = AnnexRepo(annex_path, src)

    assert_false(ar.file_has_content("test-annex.dat"))
    ar.annex_get(["test-annex.dat"])
    assert_true(ar.file_has_content("test-annex.dat"))


@with_tempfile
def test_AnnexRepo_check_path(annex_path):

    ar = AnnexRepo(annex_path)
    result = ar._check_path("testfile")
    assert_equal(result, "testfile", "_check_path() returned %s" % result)
    result = ar._check_path("./testfile")
    assert_equal(result, "testfile", "_check_path() returned %s" % result)
    result = ar._check_path("testdir/../testfile")
    assert_equal(result, "testfile", "_check_path() returned %s" % result)
    result = ar._check_path("testdir/testfile")
    assert_equal(result, "testdir/testfile", "_check_path() returned %s" % result)
    result = ar._check_path(os.path.join(annex_path, "testfile"))
    assert_equal(result, "testfile", "_check_path() returned %s" % result)
    assert_raises(FileNotInAnnexError, ar._check_path, os.getcwd())
