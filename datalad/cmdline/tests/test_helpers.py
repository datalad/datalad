# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for cmdline.helpers"""

__docformat__ = 'restructuredtext'

from mock import patch
from nose.tools import assert_is_instance

from os import mkdir
from os.path import join as opj, exists, realpath
from ..helpers import get_datalad_master, get_repo_instance

from ...tests.utils import ok_, eq_, assert_cwd_unchanged, ok_clean_git, \
    with_tempfile, SkipTest, with_testrepos
from ...support.collectionrepo import CollectionRepo
from ...support.handlerepo import HandleRepo
from ...support.annexrepo import AnnexRepo
from ...support.gitrepo import GitRepo
from ...consts import DATALAD_COLLECTION_NAME
from ...utils import chpwd, getpwd


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
def test_get_datalad_master(path):
    lcpath = opj(path, DATALAD_COLLECTION_NAME)
    ok_(not exists(lcpath))

    class mocked_dirs:
        user_data_dir = path

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs) as cm:
        master = get_datalad_master()
        eq_(master.path, lcpath)
        ok_(exists(lcpath))
        ok_clean_git(lcpath, annex=False)
        # raises exception in case of invalid collection repo:
        get_repo_instance(lcpath, CollectionRepo)


@assert_cwd_unchanged
@with_testrepos('^basic_git$', flavors=['clone'])
def test_get_repo_instance_git(path):

    # get instance from path:
    repo = get_repo_instance(path, GitRepo)
    assert_is_instance(repo, GitRepo)
    eq_(realpath(repo.path), realpath(path))

    old_pwd = getpwd()

    # get instance from current dir:
    chpwd(path)
    repo = get_repo_instance()
    assert_is_instance(repo, GitRepo)
    eq_(realpath(repo.path), realpath(path))

    # get instance from current subdir:
    new_subdir = opj(path, "subdir")
    mkdir(new_subdir)
    chpwd(new_subdir)
    eq_(new_subdir, getpwd())
    repo = get_repo_instance()
    assert_is_instance(repo, GitRepo)
    eq_(realpath(repo.path), realpath(path))

    chpwd(old_pwd)


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=['clone'])
def test_get_repo_instance_annex(path):

    # get instance from path:
    repo = get_repo_instance(path, AnnexRepo)
    assert_is_instance(repo, AnnexRepo)
    eq_(realpath(repo.path), realpath(path))

    old_pwd = getpwd()

    # get instance from current dir:
    chpwd(path)
    repo = get_repo_instance()
    assert_is_instance(repo, AnnexRepo)
    eq_(realpath(repo.path), realpath(path))

    # get instance from current subdir:
    new_subdir = opj(path, "subdir")
    mkdir(new_subdir)
    chpwd(new_subdir)
    eq_(new_subdir, getpwd())
    repo = get_repo_instance()
    assert_is_instance(repo, AnnexRepo)
    eq_(realpath(repo.path), realpath(path))

    chpwd(old_pwd)


@assert_cwd_unchanged
@with_testrepos('.*handle.*', flavors=['clone'])
def test_get_repo_instance_handle(path):

    # get instance from path:
    repo = get_repo_instance(path, HandleRepo)
    assert_is_instance(repo, HandleRepo)
    eq_(realpath(repo.path), realpath(path))

    old_pwd = getpwd()

    # get instance from current dir:
    chpwd(path)
    repo = get_repo_instance()
    assert_is_instance(repo, HandleRepo)
    eq_(realpath(repo.path), realpath(path))

    # get instance from current subdir:
    new_subdir = opj(path, "subdir")
    mkdir(new_subdir)
    chpwd(new_subdir)
    eq_(new_subdir, getpwd())
    repo = get_repo_instance()
    assert_is_instance(repo, HandleRepo)
    eq_(realpath(repo.path), realpath(path))

    chpwd(old_pwd)


@assert_cwd_unchanged
@with_testrepos('.*collection.*', flavors=['clone'])
def test_get_repo_instance_collection(path):

    # get instance from path:
    repo = get_repo_instance(path, CollectionRepo)
    assert_is_instance(repo, CollectionRepo)
    eq_(realpath(repo.path), realpath(path))

    old_pwd = getpwd()

    # get instance from current dir:
    chpwd(path)
    repo = get_repo_instance()
    assert_is_instance(repo, CollectionRepo)
    eq_(realpath(repo.path), realpath(path))

    # get instance from current subdir:
    new_subdir = opj(path, "subdir")
    mkdir(new_subdir)
    chpwd(new_subdir)
    eq_(new_subdir, getpwd())
    repo = get_repo_instance()
    assert_is_instance(repo, CollectionRepo)
    eq_(realpath(repo.path), realpath(path))

    chpwd(old_pwd)
