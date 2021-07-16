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

from io import StringIO
from os import mkdir
from os.path import (
    join as opj,
)

from nose.tools import assert_raises, assert_equal

from ..helpers import get_repo_instance, fail_with_short_help, _fix_datalad_ri
from ..helpers import strip_arg_from_argv

from datalad.tests.utils import (
    assert_is_instance,
    eq_,
    assert_cwd_unchanged,
    with_testrepos,
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


def test_fail_with_short_help():
    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(exit_code=3, out=out)
    assert_equal(cme.exception.code, 3)
    assert_equal(out.getvalue(), "")

    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(msg="Failed badly", out=out)
    assert_equal(cme.exception.code, 1)
    assert_equal(out.getvalue(), "error: Failed badly\n")

    # Suggestions, hint, etc
    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(
            msg="Failed badly",
            known=["mother", "mutter", "father", "son"],
            provided="muther",
            hint="You can become one",
            exit_code=0,  # no one forbids
            what="parent",
            out=out)
    assert_equal(cme.exception.code, 0)
    assert_equal(out.getvalue(),
                 "error: Failed badly\n"
                 "datalad: Unknown parent 'muther'.  See 'datalad --help'.\n\n"
                 "Did you mean any of these?\n"
                 "        mutter\n"
                 "        mother\n"
                 "        father\n"
                 "Hint: You can become one\n")


def test_fix_datalad_ri():
    assert_equal(_fix_datalad_ri('/'), '/')
    assert_equal(_fix_datalad_ri('/a/b'), '/a/b')
    assert_equal(_fix_datalad_ri('//'), '///')
    assert_equal(_fix_datalad_ri('///'), '///')
    assert_equal(_fix_datalad_ri('//a'), '///a')
    assert_equal(_fix_datalad_ri('///a'), '///a')
    assert_equal(_fix_datalad_ri('//a/b'), '///a/b')
    assert_equal(_fix_datalad_ri('///a/b'), '///a/b')