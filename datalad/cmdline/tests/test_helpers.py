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

from os import mkdir
from os.path import (
    join as opj,
)
from ..helpers import get_repo_instance
from ..helpers import strip_arg_from_argv

from datalad.tests.utils import (
    assert_is_instance,
    eq_,
    assert_cwd_unchanged,
    with_testrepos,
    known_failure_appveyor,
)
from ...support.annexrepo import AnnexRepo
from ...support.gitrepo import GitRepo
from ...utils import chpwd, getpwd
from ...utils import Path


@assert_cwd_unchanged
@with_testrepos('^basic_git$', flavors=['clone'])
def test_get_repo_instance_git(path):
    real_path = Path(path).resolve()

    # get instance from path
    repo = get_repo_instance(path, GitRepo)
    assert_is_instance(repo, GitRepo)
    eq_(repo.pathobj, real_path)

    old_pwd = getpwd()

    # get instance from current dir
    chpwd(path)
    repo = get_repo_instance()
    assert_is_instance(repo, GitRepo)
    eq_(repo.pathobj, real_path)

    # get instance from current subdir
    new_subdir = opj(path, "subdir")
    mkdir(new_subdir)
    chpwd(new_subdir)
    eq_(new_subdir, getpwd())
    repo = get_repo_instance()
    assert_is_instance(repo, GitRepo)
    eq_(repo.pathobj, real_path)

    chpwd(old_pwd)


@known_failure_appveyor  # passes on adina's win10 box
@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=['clone'])
def test_get_repo_instance_annex(path):
    real_path = Path(path).resolve()

    # get instance from path
    repo = get_repo_instance(path, AnnexRepo)
    assert_is_instance(repo, AnnexRepo)
    eq_(repo.pathobj, real_path)

    old_pwd = getpwd()

    # get instance from current dir
    chpwd(path)
    repo = get_repo_instance()
    assert_is_instance(repo, AnnexRepo)
    eq_(repo.pathobj, real_path)

    # get instance from current subdir
    new_subdir = opj(path, "subdir")
    mkdir(new_subdir)
    chpwd(new_subdir)
    eq_(new_subdir, getpwd())
    repo = get_repo_instance()
    assert_is_instance(repo, AnnexRepo)
    eq_(repo.pathobj, real_path)

    chpwd(old_pwd)


def test_strip_arg_from_argv():
    eq_(strip_arg_from_argv(['-s', 'value'], 'value', ('-s',)), [])
    eq_(strip_arg_from_argv(['-s', 'value'], 'value', ('-s', '--long-s')), [])
    eq_(strip_arg_from_argv(
            ['cmd', '-s', 'value', '--more'], 'value', ('-s', '--long-s')),
            ['cmd',                '--more'])
