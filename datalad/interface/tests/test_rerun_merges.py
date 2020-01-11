# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
from datalad.tests.utils import assert_false
from datalad.tests.utils import eq_
from datalad.tests.utils import known_failure_windows
from datalad.tests.utils import neq_
from datalad.tests.utils import ok_
from datalad.tests.utils import slow
from datalad.tests.utils import with_tempfile

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
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_fastforwardable(path):
    ds = Dataset(path).create()
    ds.repo.checkout("master", options=["-b", "side"])
    ds.run("echo foo >foo")
    ds.repo.checkout("master")
    ds.repo.merge("side", options=["-m", "Merge side", "--no-ff"])
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
    eq_(ds.repo.get_hexsha("master^"),
        ds.repo.get_hexsha("HEAD^"))
    ok_(ds.repo.commit_exists("HEAD^2"))

    ds.repo.checkout("master")
    ds.rerun(since="", onto="master^2")
    #  o                 b_r
    #  o                 a_n
    eq_(ds.repo.get_hexsha("master^2"),
        ds.repo.get_hexsha())

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    #  o                 c_n
    #  |\
    #  | o               b_r
    #  |/
    #  o                 a_n
    eq_(ds.repo.get_active_branch(), "master")
    eq_(hexsha_before,
        ds.repo.get_hexsha())


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_fastforwardable_mutator(path):
    ds = Dataset(path).create()
    ds.repo.checkout("master", options=["-b", "side"])
    ds.run("echo foo >>foo")
    ds.repo.checkout("master")
    ds.repo.merge("side", options=["-m", "Merge side", "--no-ff"])
    #  o                 c_n
    #  |\
    #  | o               b_r
    #  |/
    #  o                 a_n

    ds.rerun(since="", onto="master^2")
    #  o                 b_R
    #  o                 b_r
    #  o                 a_n
    neq_(ds.repo.get_hexsha("master^2"),
         ds.repo.get_hexsha())

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    #  o                 b_R
    #  o                 c_n
    #  |\
    #  | o               b_r
    #  |/
    #  o                 a_n
    eq_(ds.repo.get_active_branch(), "master")
    assert_false(ds.repo.commit_exists("master^2"))
    eq_(hexsha_before,
        ds.repo.get_hexsha("master^"))


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_left_right_runs(path):
    ds = Dataset(path).create()
    ds.repo.checkout("master", options=["-b", "side"])
    ds.run("echo foo >foo")
    ds.repo.checkout("master")
    ds.run("echo bar >bar")
    ds.repo.merge("side", options=["-m", "Merge side"])
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
    neq_(ds.repo.get_hexsha("master^"),
         ds.repo.get_hexsha("HEAD^"))
    neq_(ds.repo.get_hexsha("master^2"),
         ds.repo.get_hexsha("HEAD^2"))

    ds.repo.checkout("master")
    ds.rerun(since="", onto="master^")
    # o                 d_M
    # |\
    # | o               b_R
    # |/
    # o                 c_r
    # o                 a_n
    eq_(ds.repo.get_hexsha("master^"),
        ds.repo.get_hexsha("HEAD^"))
    neq_(ds.repo.get_hexsha("master^2"),
         ds.repo.get_hexsha("HEAD^2"))

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n
    eq_(hexsha_before, ds.repo.get_hexsha())


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_run_left_mutator_right(path):
    ds = Dataset(path).create()
    ds.repo.checkout("master", options=["-b", "side"])
    ds.run("echo ichange >>ichange")
    ds.repo.checkout("master")
    ds.run("echo idont >idont")
    ds.repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n

    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    # o                 b_R
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n
    eq_(ds.repo.get_hexsha(hexsha_before),
        ds.repo.get_hexsha("master^"))


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_nonrun_left_run_right(path):
    ds = Dataset(path).create()
    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("blah")
    ds.save()
    ds.repo.checkout("master~", options=["-b", "side"])
    ds.run("echo foo >foo")
    ds.repo.checkout("master")
    ds.repo.merge("side", options=["-m", "Merge side"])
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
    eq_(ds.repo.get_hexsha("master^"),
        ds.repo.get_hexsha("HEAD^"))
    neq_(ds.repo.get_hexsha("master^2"),
         ds.repo.get_hexsha("HEAD^2"))

    ds.repo.checkout("master")
    ds.rerun(since="", onto="master^2")
    # o                 d_n
    # |\
    # | o               c_r
    # o |               b_n
    # |/
    # o                 a_n
    ok_(ds.repo.get_active_branch() is None)
    eq_(ds.repo.get_hexsha("master"),
        ds.repo.get_hexsha())
    eq_(ds.repo.get_hexsha("master^"),
        ds.repo.get_hexsha("HEAD^"))
    eq_(ds.repo.get_hexsha("master^2"),
        ds.repo.get_hexsha("HEAD^2"))

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    # o                 d_n
    # |\
    # | o               c_r
    # o |               b_n
    # |/
    # o                 a_n
    eq_(hexsha_before, ds.repo.get_hexsha())


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_run_left_nonrun_right(path):
    ds = Dataset(path).create()
    ds.run("echo foo >foo")
    ds.repo.checkout("master~", options=["-b", "side"])
    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("blah")
    ds.save()
    ds.repo.checkout("master")
    ds.repo.merge("side", options=["-m", "Merge side"])
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
    neq_(ds.repo.get_hexsha("master^"),
         ds.repo.get_hexsha("HEAD^"))
    eq_(ds.repo.get_hexsha("master^2"),
        ds.repo.get_hexsha("HEAD^2"))

    ds.repo.checkout("master")
    ds.rerun(since="", onto="master^2")
    # o                 b_R
    # o                 c_n
    # o                 a_n
    assert_false(ds.repo.commit_exists("HEAD^2"))
    eq_(ds.repo.get_hexsha("master^2"),
        ds.repo.get_hexsha("HEAD^"))

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    # o                 d_n
    # |\
    # | o               c_n
    # o |               b_r
    # |/
    # o                 a_n
    eq_(hexsha_before, ds.repo.get_hexsha())


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_mutator_left_nonrun_right(path):
    ds = Dataset(path).create()
    ds.run("echo foo >>foo")
    ds.repo.checkout("master~", options=["-b", "side"])
    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("blah")
    ds.save()
    ds.repo.checkout("master")
    ds.repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # | o               c_n
    # o |               b_r
    # |/
    # o                 a_n

    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    # o                 b_R
    # o                 d_n
    # |\
    # | o               c_n
    # o |               b_r
    # |/
    # o                 a_n
    assert_false(ds.repo.commit_exists("master^2"))
    eq_(hexsha_before,
        ds.repo.get_hexsha("master^"))


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_mutator_stem_nonrun_merges(path):
    ds = Dataset(path).create()
    ds.run("echo foo >>foo")
    with open(op.join(path, "nonrun-file0"), "w") as f:
        f.write("blah")
    ds.save()
    ds.repo.checkout("master~", options=["-b", "side"])
    with open(op.join(path, "nonrun-file1"), "w") as f:
        f.write("more blah")
    ds.save()
    ds.repo.checkout("master")
    ds.repo.merge("side", options=["-m", "Merge side"])
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
    ok_(ds.repo.commit_exists("HEAD^2"))
    neq_(ds.repo.get_hexsha("master"),
         ds.repo.get_hexsha())

    ds.repo.checkout("master")
    ds.rerun(since="", onto="master^2")
    # o                 c_C
    # o                 b_R
    # o                 d_n
    # o                 b_r
    # o                 a_n
    assert_false(ds.repo.commit_exists("HEAD^2"))
    eq_(ds.repo.get_hexsha("HEAD~2"),
        ds.repo.get_hexsha("master^2"))

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
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
        ds.repo.get_hexsha("master^"))
    assert_false(ds.repo.commit_exists("HEAD^2"))


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_exclude_side(path):
    ds = Dataset(path).create()
    ds.repo.checkout("master", options=["-b", "side"])
    ds.run("echo foo >foo")
    ds.repo.checkout("master")
    ds.run("echo bar >bar")
    ds.repo.merge("side", options=["-m", "Merge side"])
    # o                 d_n
    # |\
    # o |               c_r
    # | o               b_r
    # |/
    # o                 a_n

    ds.rerun("HEAD", since="master^2", onto="")
    # o                 d_M
    # |\
    # o |               c_R
    # | o               b_r
    # |/
    # o                 a_n
    neq_(ds.repo.get_hexsha("master"),
         ds.repo.get_hexsha())
    neq_(ds.repo.get_hexsha("master^"),
         ds.repo.get_hexsha("HEAD^"))
    eq_(ds.repo.get_hexsha("master^2"),
        ds.repo.get_hexsha("HEAD^2"))


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_unrelated_run_left_nonrun_right(path):
    ds = Dataset(path).create()
    ds.run("echo foo >foo")
    ds.repo.checkout("master~", options=["--orphan", "side"])
    ds.save(message="squashed")
    ds.repo.checkout("master")
    ds.repo.merge("side",
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
    neq_(ds.repo.get_hexsha("HEAD^"),
         ds.repo.get_hexsha("master^"))
    eq_(ds.repo.get_hexsha("HEAD^2"),
        ds.repo.get_hexsha("master^2"))
    assert_false(ds.repo.commit_exists("HEAD^2^"))

    ds.repo.checkout("master")
    ds.rerun(since="", onto="master^2")
    # o                 b_R
    # o                 c_n
    assert_false(ds.repo.commit_exists("HEAD^2"))
    eq_(ds.repo.get_hexsha("HEAD^"),
        ds.repo.get_hexsha("master^2"))

    ds.repo.checkout("master")
    ds.rerun(since="")
    # o                 d_n
    # |\
    # | o               c_n
    # o                 b_r
    # o                 a_n
    eq_(ds.repo.get_hexsha("master"),
        ds.repo.get_hexsha())


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_unrelated_mutator_left_nonrun_right(path):
    ds = Dataset(path).create()
    ds.run("echo foo >>foo")
    ds.repo.checkout("master~", options=["--orphan", "side"])
    ds.save(message="squashed")
    ds.repo.checkout("master")
    ds.repo.merge("side",
                  options=["-m", "Merge side", "--allow-unrelated-histories"])
    # o                 d_n
    # |\
    # | o               c_n
    # o                 b_r
    # o                 a_n

    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    # o                 b_R
    # o                 d_n
    # |\
    # | o               c_n
    # o                 b_r
    # o                 a_n
    eq_(hexsha_before,
        ds.repo.get_hexsha("master^"))


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_unrelated_nonrun_left_run_right(path):
    ds = Dataset(path).create()
    ds.repo.checkout("master", options=["--orphan", "side"])
    ds.save(message="squashed")
    ds.run("echo foo >foo")
    ds.repo.checkout("master")
    ds.repo.merge("side",
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
    ok_(ds.repo.commit_exists("HEAD^2"))
    neq_(ds.repo.get_hexsha("master"),
         ds.repo.get_hexsha())
    eq_(ds.repo.get_hexsha("master^"),
        ds.repo.get_hexsha("HEAD^"))
    eq_(ds.repo.get_hexsha("master^2^"),
        ds.repo.get_hexsha("HEAD^2^"))
    assert_false(ds.repo.commit_exists("HEAD^2^^"))

    ds.repo.checkout("master")
    ds.rerun(since="", onto="master^2")
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n
    eq_(ds.repo.get_hexsha("master"),
        ds.repo.get_hexsha())
    assert_false(ds.repo.commit_exists("HEAD^2^^"))

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n
    eq_(hexsha_before, ds.repo.get_hexsha())


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_unrelated_nonrun_left_mutator_right(path):
    ds = Dataset(path).create()
    ds.repo.checkout("master", options=["--orphan", "side"])
    ds.save(message="squashed")
    ds.run("echo foo >>foo")
    ds.repo.checkout("master")
    ds.repo.merge("side",
                  options=["-m", "Merge side", "--allow-unrelated-histories"])
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n

    ds.rerun(since="", onto="master^2")
    # o                 d_M
    # |\
    # | o               c_R
    # | o               c_r
    # | o               b_n
    # o                 a_n
    eq_(ds.repo.get_hexsha("HEAD^2^"),
        ds.repo.get_hexsha("master^2"))
    assert_false(ds.repo.commit_exists("HEAD^2~3"))

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    # o                 c_R
    # o                 d_n
    # |\
    # | o               c_r
    # | o               b_n
    # o                 a_n
    eq_(ds.repo.get_hexsha("HEAD^"),
        hexsha_before)
    assert_false(ds.repo.commit_exists("HEAD^2"))


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_multifork(path):
    ds = Dataset(path).create()
    ds.repo.checkout("master", options=["-b", "side"])
    ds.run("echo foo >foo")
    ds.repo.checkout("side", options=["-b", "side-nonrun"])
    with open(op.join(path, "nonrun-file0"), "w") as f:
        f.write("blah 0")
    ds.save()
    ds.repo.checkout("side")
    with open(op.join(path, "nonrun-file1"), "w") as f:
        f.write("blah 1")
    ds.save()
    ds.run("echo bar >bar")
    ds.repo.checkout("side~1", options=["-b", "side-side"])
    with open(op.join(path, "nonrun-file2"), "w") as f:
        f.write("blah 2")
    ds.save()
    ds.run("echo onside0 >onside0")
    ds.repo.checkout("side")
    ds.repo.merge("side-side")
    ds.run("echo after-side-side >after-side-side")
    ds.repo.checkout("master")
    ds.repo.merge("side", options=["--no-ff"])
    ds.repo.merge("side-nonrun")
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
    eq_(ds.repo.get_hexsha("HEAD~2"),
        ds.repo.get_hexsha("master~2"))
    neq_(ds.repo.get_hexsha("HEAD^2"),
         ds.repo.get_hexsha("master^2"))
    neq_(ds.repo.get_hexsha("HEAD^^2"),
         ds.repo.get_hexsha("master^^2"))
    assert_false(ds.repo.commit_exists("HEAD^^2^2"))
    eq_(ds.repo.get_hexsha("HEAD^2^^"),
        ds.repo.get_hexsha("master^2^^"))

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    eq_(hexsha_before, ds.repo.get_hexsha())


@slow
@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_octopus(path):
    ds = Dataset(path).create()
    ds.run("echo foo >>foo")
    with open(op.join(ds.path, "non-run"), "w") as nrfh:
        nrfh.write("non-run")
    ds.save()
    ds.repo.checkout("master~", options=["-b", "topic-1"])
    ds.run("echo bar >bar")
    ds.repo.checkout("master~", options=["-b", "topic-2"])
    ds.run("echo baz >baz")
    ds.repo.checkout("master")
    ds.repo.call_git(
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
    neq_(ds.repo.get_hexsha("HEAD^3"),
         ds.repo.get_hexsha("master^3"))
    eq_(ds.repo.get_hexsha("HEAD~3"),
        ds.repo.get_hexsha("master~3"))

    ds.repo.checkout("master")
    hexsha_before = ds.repo.get_hexsha()
    ds.rerun(since="")
    eq_(hexsha_before,
        ds.repo.get_hexsha("master~"))
