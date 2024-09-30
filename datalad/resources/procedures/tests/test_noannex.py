#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import pytest

from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    assert_false,
    assert_raises,
    assert_true,
    with_tempfile,
    with_tree,
)


def check_noannex(ds):
    assert_true(isinstance(ds.repo, GitRepo))
    assert_true((ds.pathobj / ".noannex").exists())
    assert_false((ds.pathobj / ".git" / "annex").exists())


@with_tempfile(mkdir=True)
def test_noannex_simple(path=None):
    ds = Dataset(path).create()
    assert_true(isinstance(ds.repo, AnnexRepo))
    ds.run_procedure('cfg_noannex')  # we are killing annex while ds.repo
    check_noannex(ds)


@with_tree(tree={
    'data': 'some'
})
def test_noannex_create_force(path=None):
    ds = Dataset(path).create(force=True, cfg_proc='noannex')
    check_noannex(ds)


@pytest.mark.xfail(reason="Under pytest gets IncompleteResultsError with CommandError inside "
                   "instead of actual CommandError")
@with_tree(tree={
    'data': 'some'
})
def test_noannex_fail_if_has_annexed(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    assert_true(isinstance(ds.repo, AnnexRepo))
    # internally procedure raises RuntimeError, but since we run it via runner, we
    # get CommandError here
    with assert_raises(CommandError):
        ds.run_procedure('cfg_noannex')  # we are killing annex while ds.repo
