# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test `datalad rerun` on histories with merges.
"""

__docformat__ = 'restructuredtext'

import os.path as op

from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    assert_false,
    eq_,
    neq_,
    ok_,
    skip_if_adjusted_branch,
    slow,
    with_tempfile,
)

# Notation in graphs:
#
# The initial graph is made up of the following commits:
#
# - x_n: commit x without a run command
# - x_r: commit x with a run command
#
# When re-executing a command creates a new commit, it is labeled as one of the
# following:
#
# - x_C: cherry picked
# - x_M: merge commit
# - x_R: run commit


@slow
@with_tempfile(mkdir=True)
def test_rerun_fastforwardable(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds_repo.checkout(DEFAULT_BRANCH, options=["-b", "side"])
    ds.run("echo foo >foo")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side", options=["-m", "Merge side", "--no-ff"])
    #  o                 c_n
    #  |\
    #  | o               b_r
    #  |/
    #  o                 a_n

    ds.rerun(since="", onto="")
    #  o                 c_M
    #  |\
    #  | o               b_R
    #  |/
    #  o                 a_n
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^"),
        ds_repo.get_hexsha("HEAD^"))
    ok_(ds_repo.commit_exists("HEAD^2"))

    ds_repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="", onto=DEFAULT_BRANCH + "^2")
    #  o                 b_r
    #  o                 a_n
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
        ds_repo.get_hexsha())

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    #  o                 c_n
    #  |\
    #  | o               b_r
    #  |/
    #  o                 a_n
    eq_(ds_repo.get_active_branch(), DEFAULT_BRANCH)
    eq_(hexsha_before,
        ds_repo.get_hexsha())


@slow
@with_tempfile(mkdir=True)
def test_rerun_fastforwardable_mutator(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds_repo.checkout(DEFAULT_BRANCH, options=["-b", "side"])
    ds.run("echo foo >>foo")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side", options=["-m", "Merge side", "--no-ff"])
    #  o                 c_n
    #  |\
    #  | o               b_r
    #  |/
    #  o                 a_n

    ds.rerun(since="", onto=DEFAULT_BRANCH + "^2")
    #  o                 b_R
    #  o                 b_r
    #  o                 a_n
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
         ds_repo.get_hexsha())

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    #  o                 b_R
    #  o                 c_n
    #  |\
    #  | o               b_r
    #  |/
    #  o                 a_n
    eq_(ds_repo.get_active_branch(), DEFAULT_BRANCH)
    assert_false(ds_repo.commit_exists(DEFAULT_BRANCH + "^2"))
    eq_(hexsha_before,
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^"))


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_left_right_runs(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds_repo.checkout(DEFAULT_BRANCH, options=["-b", "side"])
    ds.run("echo foo >foo")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds.run("echo bar >bar")
    ds_repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n

    ds.rerun(since="", onto="")
    # o                 d_M
    # |\
    # o |               c_R
    # | o               b_R
    # |/
    # o                 a_n
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^"),
         ds_repo.get_hexsha("HEAD^"))
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
         ds_repo.get_hexsha("HEAD^2"))

    ds_repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="", onto=DEFAULT_BRANCH + "^")
    # o                 d_M
    # |\
    # | o               b_R
    # |/
    # o                 c_r
    # o                 a_n
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^"),
        ds_repo.get_hexsha("HEAD^"))
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
         ds_repo.get_hexsha("HEAD^2"))

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n
    eq_(hexsha_before, ds_repo.get_hexsha())


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_run_left_mutator_right(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds_repo.checkout(DEFAULT_BRANCH, options=["-b", "side"])
    ds.run("echo ichange >>ichange")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds.run("echo idont >idont")
    ds_repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n

    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 b_R
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n
    eq_(ds_repo.get_hexsha(hexsha_before),
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^"))


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_nonrun_left_run_right(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("blah")
    ds.save()
    ds_repo.checkout(DEFAULT_BRANCH + "~", options=["-b", "side"])
    ds.run("echo foo >foo")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # | o               c_r
    # o |               b_n
    # |/
    # o                 a_n

    ds.rerun(since="", onto="")
    # o                 d_M
    # |\
    # | o               c_R
    # o |               b_n
    # |/
    # o                 a_n
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^"),
        ds_repo.get_hexsha("HEAD^"))
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
         ds_repo.get_hexsha("HEAD^2"))

    ds_repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="", onto=DEFAULT_BRANCH + "^2")
    # o                 d_n
    # |\
    # | o               c_r
    # o |               b_n
    # |/
    # o                 a_n
    ok_(ds_repo.get_active_branch() is None)
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH),
        ds_repo.get_hexsha())
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^"),
        ds_repo.get_hexsha("HEAD^"))
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
        ds_repo.get_hexsha("HEAD^2"))

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 d_n
    # |\
    # | o               c_r
    # o |               b_n
    # |/
    # o                 a_n
    eq_(hexsha_before, ds_repo.get_hexsha())


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_run_left_nonrun_right(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds.run("echo foo >foo")
    ds_repo.checkout(DEFAULT_BRANCH + "~", options=["-b", "side"])
    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("blah")
    ds.save()
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # | o               c_n
    # o |               b_r
    # |/
    # o                 a_n

    ds.rerun(since="", onto="")
    # o                 d_M
    # |\
    # | o               c_n
    # o |               b_R
    # |/
    # o                 a_n
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^"),
         ds_repo.get_hexsha("HEAD^"))
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
        ds_repo.get_hexsha("HEAD^2"))

    ds_repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="", onto=DEFAULT_BRANCH + "^2")
    # o                 b_R
    # o                 c_n
    # o                 a_n
    assert_false(ds_repo.commit_exists("HEAD^2"))
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
        ds_repo.get_hexsha("HEAD^"))

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 d_n
    # |\
    # | o               c_n
    # o |               b_r
    # |/
    # o                 a_n
    eq_(hexsha_before, ds_repo.get_hexsha())


# @slow  # ~5sec on Yarik's laptop
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_mutator_left_nonrun_right(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds.run("echo foo >>foo")
    ds_repo.checkout(DEFAULT_BRANCH + "~", options=["-b", "side"])
    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("blah")
    ds.save()
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # | o               c_n
    # o |               b_r
    # |/
    # o                 a_n

    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 b_R
    # o                 d_n
    # |\
    # | o               c_n
    # o |               b_r
    # |/
    # o                 a_n
    assert_false(ds_repo.commit_exists(DEFAULT_BRANCH + "^2"))
    eq_(hexsha_before,
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^"))


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_mutator_stem_nonrun_merges(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds.run("echo foo >>foo")
    with open(op.join(path, "nonrun-file0"), "w") as f:
        f.write("blah")
    ds.save()
    ds_repo.checkout(DEFAULT_BRANCH + "~", options=["-b", "side"])
    with open(op.join(path, "nonrun-file1"), "w") as f:
        f.write("more blah")
    ds.save()
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side", options=["-m", "Merge side"])
    # o                 e_n
    # |\
    # | o               d_n
    # o |               c_n
    # |/
    # o                 b_r
    # o                 a_n

    ds.rerun(since="", onto="")
    # o                 e_M
    # |\
    # | o               d_C
    # o |               c_C
    # |/
    # o                 b_R
    # o                 a_n
    ok_(ds_repo.commit_exists("HEAD^2"))
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH),
         ds_repo.get_hexsha())

    ds_repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="", onto=DEFAULT_BRANCH + "^2")
    # o                 c_C
    # o                 b_R
    # o                 d_n
    # o                 b_r
    # o                 a_n
    assert_false(ds_repo.commit_exists("HEAD^2"))
    eq_(ds_repo.get_hexsha("HEAD~2"),
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"))

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 b_R
    # o                 e_n
    # |\
    # | o               d_n
    # o |               c_n
    # |/
    # o                 b_r
    # o                 a_n
    eq_(hexsha_before,
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^"))
    assert_false(ds_repo.commit_exists("HEAD^2"))


# @slow  # ~4.5sec
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_exclude_side(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds_repo.checkout(DEFAULT_BRANCH, options=["-b", "side"])
    ds.run("echo foo >foo")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds.run("echo bar >bar")
    ds_repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n

    ds.rerun("HEAD", since=DEFAULT_BRANCH + "^2", onto="")
    # o                 d_M
    # |\
    # o |               c_R
    # | o               b_r
    # |/
    # o                 a_n
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH),
         ds_repo.get_hexsha())
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^"),
         ds_repo.get_hexsha("HEAD^"))
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"),
        ds_repo.get_hexsha("HEAD^2"))


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_unrelated_run_left_nonrun_right(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds.run("echo foo >foo")
    ds_repo.checkout(DEFAULT_BRANCH + "~", options=["--orphan", "side"])
    ds.save(message="squashed")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side",
                  options=["-m", "Merge side", "--allow-unrelated-histories"])
    # o                 d_n
    # |\
    # | o               c_n
    # o                 b_r
    # o                 a_n

    ds.rerun(since="", onto="")
    # o                 d_M
    # |\
    # | o               c_n
    # o                 b_R
    # o                 a_n
    neq_(ds_repo.get_hexsha("HEAD^"),
         ds_repo.get_hexsha(DEFAULT_BRANCH + "^"))
    eq_(ds_repo.get_hexsha("HEAD^2"),
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"))
    assert_false(ds_repo.commit_exists("HEAD^2^"))

    ds_repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="", onto=DEFAULT_BRANCH + "^2")
    # o                 b_R
    # o                 c_n
    assert_false(ds_repo.commit_exists("HEAD^2"))
    eq_(ds_repo.get_hexsha("HEAD^"),
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"))

    ds_repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="")
    # o                 d_n
    # |\
    # | o               c_n
    # o                 b_r
    # o                 a_n
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH),
        ds_repo.get_hexsha())


# @slow  # ~3.5sec on Yarik's laptop
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_unrelated_mutator_left_nonrun_right(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds.run("echo foo >>foo")
    ds_repo.checkout(DEFAULT_BRANCH + "~", options=["--orphan", "side"])
    ds.save(message="squashed")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side",
                  options=["-m", "Merge side", "--allow-unrelated-histories"])
    # o                 d_n
    # |\
    # | o               c_n
    # o                 b_r
    # o                 a_n

    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 b_R
    # o                 d_n
    # |\
    # | o               c_n
    # o                 b_r
    # o                 a_n
    eq_(hexsha_before,
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^"))


@slow
@with_tempfile(mkdir=True)
def test_rerun_unrelated_nonrun_left_run_right(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds_repo.checkout(DEFAULT_BRANCH, options=["--orphan", "side"])
    ds.save(message="squashed")
    ds.run("echo foo >foo")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side",
                  options=["-m", "Merge side", "--allow-unrelated-histories"])
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n

    ds.rerun(since="", onto="")
    # o                 d_M
    # |\
    # | o               c_R
    # | o               b_n
    # o                 a_n
    ok_(ds_repo.commit_exists("HEAD^2"))
    neq_(ds_repo.get_hexsha(DEFAULT_BRANCH),
         ds_repo.get_hexsha())
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^"),
        ds_repo.get_hexsha("HEAD^"))
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH + "^2^"),
        ds_repo.get_hexsha("HEAD^2^"))
    assert_false(ds_repo.commit_exists("HEAD^2^^"))

    ds_repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="", onto=DEFAULT_BRANCH + "^2")
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n
    eq_(ds_repo.get_hexsha(DEFAULT_BRANCH),
        ds_repo.get_hexsha())
    assert_false(ds_repo.commit_exists("HEAD^2^^"))

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n
    eq_(hexsha_before, ds_repo.get_hexsha())


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_unrelated_nonrun_left_mutator_right(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds_repo.checkout(DEFAULT_BRANCH, options=["--orphan", "side"])
    ds.save(message="squashed")
    ds.run("echo foo >>foo")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side",
                  options=["-m", "Merge side", "--allow-unrelated-histories"])
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n

    ds.rerun(since="", onto=DEFAULT_BRANCH + "^2")
    # o                 d_M
    # |\
    # | o               c_R
    # | o               c_r
    # | o               b_n
    # o                 a_n
    eq_(ds_repo.get_hexsha("HEAD^2^"),
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"))
    assert_false(ds_repo.commit_exists("HEAD^2~3"))

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    # o                 c_R
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n
    eq_(ds_repo.get_hexsha("HEAD^"),
        hexsha_before)
    assert_false(ds_repo.commit_exists("HEAD^2"))


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_multifork(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds_repo.checkout(DEFAULT_BRANCH, options=["-b", "side"])
    ds.run("echo foo >foo")
    ds_repo.checkout("side", options=["-b", "side-nonrun"])
    with open(op.join(path, "nonrun-file0"), "w") as f:
        f.write("blah 0")
    ds.save()
    ds_repo.checkout("side")
    with open(op.join(path, "nonrun-file1"), "w") as f:
        f.write("blah 1")
    ds.save()
    ds.run("echo bar >bar")
    ds_repo.checkout("side~1", options=["-b", "side-side"])
    with open(op.join(path, "nonrun-file2"), "w") as f:
        f.write("blah 2")
    ds.save()
    ds.run("echo onside0 >onside0")
    ds_repo.checkout("side")
    ds_repo.merge("side-side")
    ds.run("echo after-side-side >after-side-side")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.merge("side", options=["--no-ff"])
    ds_repo.merge("side-nonrun")
    # o                 k_n
    # |\
    # | o               j_n
    # o |               i_n
    # |\ \
    # | o |             h_r
    # | o |             g_n
    # | |\ \
    # | | o |           f_r
    # | | o |           e_n
    # | o | |           d_r
    # | |/ /
    # | o |             c_n
    # | |/
    # | o               b_r
    # |/
    # o                 a_n

    ds.rerun(since="", onto="")
    # o                 k_M
    # |\
    # | o               j_n
    # o |               i_M
    # |\ \
    # | o |             h_R
    # | o |             g_M
    # | |\ \
    # | | o |           f_R
    # | | o |           e_n
    # | o | |           d_R
    # | |/ /
    # | o |             c_n
    # | |/
    # | o               b_R
    # |/
    # o                 a_n
    eq_(ds_repo.get_hexsha("HEAD~2"),
        ds_repo.get_hexsha(DEFAULT_BRANCH + "~2"))
    neq_(ds_repo.get_hexsha("HEAD^2"),
         ds_repo.get_hexsha(DEFAULT_BRANCH + "^2"))
    neq_(ds_repo.get_hexsha("HEAD^^2"),
         ds_repo.get_hexsha(DEFAULT_BRANCH + "^^2"))
    assert_false(ds_repo.commit_exists("HEAD^^2^2"))
    eq_(ds_repo.get_hexsha("HEAD^2^^"),
        ds_repo.get_hexsha(DEFAULT_BRANCH + "^2^^"))

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    eq_(hexsha_before, ds_repo.get_hexsha())


@slow
# test implementation requires checkout of non-adjusted branch
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_octopus(path=None):
    ds = Dataset(path).create()
    # keep direct repo accessor to speed things up
    ds_repo = ds.repo
    ds.run("echo foo >>foo")
    with open(op.join(ds.path, "non-run"), "w") as nrfh:
        nrfh.write("non-run")
    ds.save()
    ds_repo.checkout(DEFAULT_BRANCH + "~", options=["-b", "topic-1"])
    ds.run("echo bar >bar")
    ds_repo.checkout(DEFAULT_BRANCH + "~", options=["-b", "topic-2"])
    ds.run("echo baz >baz")
    ds_repo.checkout(DEFAULT_BRANCH)
    ds_repo.call_git(
        ["merge", "-m", "Merge octopus", "topic-1", "topic-2"])
    # o-.               f_M
    # |\ \
    # | | o             e_r
    # | o |             d_r
    # | |/
    # o |               c_n
    # |/
    # o                 b_r
    # o                 a_n

    ds.rerun(since="", onto="")
    neq_(ds_repo.get_hexsha("HEAD^3"),
         ds_repo.get_hexsha(DEFAULT_BRANCH + "^3"))
    eq_(ds_repo.get_hexsha("HEAD~3"),
        ds_repo.get_hexsha(DEFAULT_BRANCH + "~3"))

    ds_repo.checkout(DEFAULT_BRANCH)
    hexsha_before = ds_repo.get_hexsha()
    ds.rerun(since="")
    eq_(hexsha_before,
        ds_repo.get_hexsha(DEFAULT_BRANCH + "~"))
