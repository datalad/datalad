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
from git.exc import GitCommandError

from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, ignore_nose_capturing_stdout, \
    on_windows


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
@with_testrepos(flavors=['network-clone' if on_windows else 'local'])  # 'network' doesn't make sense for this test
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


@with_testrepos(flavors=['network-clone' if on_windows else 'local'])
def test_AnnexRepo_is_direct_mode(path):

    dm = AnnexRepo(path).is_direct_mode()
    if on_windows:
        assert_true(dm, "AnnexRepo.is_direct_mode() returned false on windows.")
    else:
        assert_false(dm, "AnnexRepo.is_direct_mode() returned true on non-windows")
    #TODO: Are there more platforms leading to direct mode?
    #Better check for filesystem instead of platform?


@with_testrepos
@with_tempfile
def test_AnnexRepo_set_direct_mode(src, dst):

    ar = AnnexRepo(dst, src)
    ar.set_direct_mode(True)
    assert_true(ar.is_direct_mode(), "Switching to direct mode failed.")
    if on_windows:
        assert_raises(RuntimeError, ar.set_direct_mode, False)
        assert_true(ar.is_direct_mode())
    else:
        ar.set_direct_mode(False)
        assert_false(ar.is_direct_mode(), "Switching to indirect mode failed.")
    #TODO: see above (test_AnnexRepo_is_direct_mode). Check for filesystem seems to be more accurate.


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
