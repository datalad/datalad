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
from ..helpers import get_repo_instance
from ..helpers import strip_arg_from_argv

from ...tests.utils import ok_, eq_, assert_cwd_unchanged, ok_clean_git, \
    with_tempfile, SkipTest, with_testrepos
from ...support.annexrepo import AnnexRepo
from ...support.gitrepo import GitRepo
from ...utils import chpwd, getpwd


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


def test_strip_arg_from_argv():
    eq_(strip_arg_from_argv(['-s', 'value'], 'value', ('-s',)), [])
    eq_(strip_arg_from_argv(['-s', 'value'], 'value', ('-s', '--long-s')), [])
    eq_(strip_arg_from_argv(
            ['cmd', '-s', 'value', '--more'], 'value', ('-s', '--long-s')),
            ['cmd',                '--more'])
