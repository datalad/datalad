# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
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
__author__ = 'Benjamin Poldrack'

import os.path
from shutil import rmtree

from nose.tools import assert_raises, assert_is_instance, assert_true
from git.exc import GitCommandError

from datalad.support.dataset import Dataset
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged


@assert_cwd_unchanged
@with_testrepos(flavors=['local'])
@with_tempfile
def test_Dataset(src, dst):

    ds = Dataset(dst, src)
    assert_is_instance(ds, Dataset, "Dataset was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.datalad')))

    #do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    assert_raises(GitCommandError, Dataset, dst, src)
    
    
@assert_cwd_unchanged
@with_testrepos(flavors=['local'])
def test_Dataset_instance_from_existing(path):

    gr = Dataset(path)
    assert_is_instance(gr, Dataset, "Dataset was not created.")
    assert_true(os.path.exists(os.path.join(path, '.datalad')))



@assert_cwd_unchanged
@with_tempfile
def test_Dataset_instance_brand_new(path):

    gr = Dataset(path)
    assert_is_instance(gr, Dataset, "Dataset was not created.")
    assert_true(os.path.exists(os.path.join(path, '.datalad')))
