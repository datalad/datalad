# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class Dataset

Note: There's not a lot to test by now.

"""

import os.path
import platform

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_equal
from git.exc import GitCommandError

from datalad.support.dataset import Dataset
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, ignore_nose_capturing_stdout


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=['local'])
@with_tempfile
def test_Dataset(src, dst):

    ds = Dataset(dst, src)
    assert_is_instance(ds, Dataset, "Dataset was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.datalad')))

    #do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    assert_raises(GitCommandError, Dataset, dst, src)
    

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=['local'])
def test_Dataset_instance_from_existing(path):

    gr = Dataset(path)
    assert_is_instance(gr, Dataset, "Dataset was not created.")
    assert_true(os.path.exists(os.path.join(path, '.datalad')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_Dataset_instance_brand_new(path):

    gr = Dataset(path)
    assert_is_instance(gr, Dataset, "Dataset was not created.")
    assert_true(os.path.exists(os.path.join(path, '.datalad')))


@ignore_nose_capturing_stdout
@with_testrepos(flavors=['network'])
@with_tempfile
def test_Dataset_get(src, dst):

    ds = Dataset(dst, src)
    assert_is_instance(ds, Dataset, "AnnexRepo was not created.")

    cwd = os.getcwd()
    os.chdir(dst)
    testfile = 'test-annex.dat'
    if platform.system() != "Windows":
        assert_raises(IOError, open, testfile, 'r')
        # If get has nothing to do, we can't test it.
        # TODO: see test_AnnexRepo_get()

    ds.get([testfile])
    f = open(testfile, 'r')
    assert_equal(f.readlines(), ['123\n'], "test-annex.dat's content doesn't match.")

    os.chdir(cwd)
