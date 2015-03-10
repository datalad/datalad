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

import os.path
import os

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_equal
from git.exc import GitCommandError

from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged


from datalad.cmd import Runner


@assert_cwd_unchanged
@with_testrepos(flavors=['local'])
@with_tempfile
def test_AnnexRepo_instance_from_clone(src, dst):

    ar = AnnexRepo(dst, src)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.git', 'annex')))

    # do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    # and therefore can't clone to `dst`
    assert_raises(GitCommandError, AnnexRepo, dst, src)

    
@assert_cwd_unchanged
@with_testrepos(flavors=['local'])
def test_AnnexRepo_instance_from_existing(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_instance_brand_new(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))



@with_testrepos
@with_tempfile
def test_AnnexRepo_get(src, dst):

    ar = AnnexRepo(dst, src)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")

    cwd = os.getcwd()
    os.chdir(dst)
    testfile = 'test-annex.dat'
    assert_raises(IOError, open, testfile, 'r')
    # If get has nothing to do, we can't test it.

    ar.annex_get(testfile)
    f = open(testfile, 'r')
    assert_equal(f.readlines(), ['123\n'], "test-annex.dat's content doesn't match.")

    os.chdir(cwd)
