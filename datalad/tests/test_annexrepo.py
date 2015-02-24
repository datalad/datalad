# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests to test implementation of class AnnexRepo

Note: There's not a lot to test by now.

"""
__author__ = 'Benjamin Poldrack'

import os.path
from shutil import rmtree

from nose.tools import assert_raises, assert_is_instance, assert_true
from git.exc import GitCommandError

from datalad.support.annexrepo import AnnexRepo

def test_AnnexRepo():

    pathToTestRepo = os.path.expanduser('~/test_annex_repo')
    ar = AnnexRepo(pathToTestRepo, 'http://psydata.ovgu.de/forrest_gump/.git')
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(pathToTestRepo, '.git', 'annex')))

    #do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    assert_raises(GitCommandError, AnnexRepo, pathToTestRepo, 'http://psydata.ovgu.de/forrest_gump/.git')

    rmtree(pathToTestRepo)