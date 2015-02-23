"""
Tests to test implementation of basic classes for datalad.

Note: There's not a lot to test by now.
"""
__author__ = 'Benjamin Poldrack'

import os.path
from shutil import rmtree

from nose.tools import assert_raises, assert_is_instance, assert_true
from git.exc import GitCommandError

from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.dataset import Dataset

def test_GitRepo():

    pathToTestRepo = os.path.expanduser('~/test_git_repo')
    gr = GitRepo(pathToTestRepo, 'http://psydata.ovgu.de/forrest_gump/.git')
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(os.path.exists(os.path.join(pathToTestRepo, '.git')))


    #do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    with assert_raises(GitCommandError):
        GitRepo(pathToTestRepo, 'http://psydata.ovgu.de/forrest_gump/.git')

    rmtree(pathToTestRepo)

def test_AnnexRepo():

    pathToTestRepo = os.path.expanduser('~/test_annex_repo')
    ar = AnnexRepo(pathToTestRepo, 'http://psydata.ovgu.de/forrest_gump/.git')
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(pathToTestRepo, '.git', 'annex')))

    #do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    with assert_raises(GitCommandError):
        AnnexRepo(pathToTestRepo, 'http://psydata.ovgu.de/forrest_gump/.git')

    rmtree(pathToTestRepo)

def test_Dataset():

    pathToTestRepo = os.path.expanduser('~/test_dataset')
    ds = Dataset(pathToTestRepo, 'http://psydata.ovgu.de/forrest_gump/.git')
    assert_is_instance(ds, Dataset, "Dataset was not created.")
    assert_true(os.path.exists(os.path.join(pathToTestRepo, '.datalad')))

    #do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    with assert_raises(GitCommandError):
        Dataset(pathToTestRepo, 'http://psydata.ovgu.de/forrest_gump/.git')

    rmtree(pathToTestRepo)