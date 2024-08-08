# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad {re,}run

"""

__docformat__ = 'restructuredtext'

import logging
import os.path as op
import sys
from io import StringIO
from os import remove
from unittest.mock import patch

import pytest

from datalad.api import (
    install,
    run,
)
from datalad.core.local.run import run_command
from datalad.core.local.tests.test_run import last_commit_msg
from datalad.distribution.dataset import Dataset
from datalad.local.rerun import (
    diff_revision,
    get_run_info,
    new_or_modified,
)
from datalad.support.exceptions import (
    CommandError,
    IncompleteResultsError,
)
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    SkipTest,
    assert_dict_equal,
    assert_false,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_not_in_results,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    create_tree,
    eq_,
    known_failure_windows,
    neq_,
    ok_,
    ok_exists,
    ok_file_has_content,
    ok_file_under_git,
    skip_if_adjusted_branch,
    slow,
    swallow_logs,
    swallow_outputs,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    Path,
    chpwd,
    on_windows,
)

cat_command = 'cat' if not on_windows else 'type'
touch_command = "touch " if not on_windows else "type nul > "
grep_command = 'grep ' if not on_windows else 'findstr '

@slow  # 17.1880s
@known_failure_windows
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_rerun(path=None, nodspath=None):
    ds = Dataset(path).create()
    sub = ds.create('sub')
    probe_path = op.join(sub.path, 'sequence')
    # run inside the dataset
    with chpwd(path), \
            swallow_outputs():
        ds.run(f'echo x$({cat_command} sub/sequence) > sub/sequence')
    # command ran once, all clean
    assert_repo_status(ds.path)
    eq_('x\n', open(probe_path).read())
    # now, for a rerun we can be anywhere, PWD and all are recorded
    # moreover, rerun must figure out which bits to unlock, even in
    # subdatasets
    with chpwd(nodspath), \
            swallow_outputs():
        ds.rerun()
    assert_repo_status(ds.path)
    # ran twice now
    eq_('xx\n', open(probe_path).read())

    # Rerunning from a subdataset skips the command.
    _, sub_info = get_run_info(ds, last_commit_msg(sub.repo))
    eq_(ds.id, sub_info["dsid"])
    assert_result_count(
        sub.rerun(return_type="list", on_failure="ignore"),
        1, status="impossible", action="run", rerun_action="skip")
    eq_('xx\n', open(probe_path).read())

    # Rerun fails with a dirty repo.
    dirt = op.join(path, "dirt")
    with open(dirt, "w") as fh:
        fh.write("")
    assert_status('impossible', ds.rerun(on_failure="ignore"))
    remove(dirt)
    assert_repo_status(ds.path)

    # Make a non-run commit.
    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.save("nonrun-file")
    # Now rerun the buried command.
    ds.rerun(revision=DEFAULT_BRANCH + "~", message="rerun buried")
    eq_('xxx\n', open(probe_path).read())
    # Also check that the message override worked.
    eq_(last_commit_msg(ds.repo).splitlines()[0],
        "[DATALAD RUNCMD] rerun buried")
    # Or a range of commits, skipping non-run commits.
    ds.rerun(since=DEFAULT_BRANCH + "~3")
    eq_('xxxxx\n', open(probe_path).read())
    # Or --since= to run all reachable commits.
    ds.rerun(since="")
    eq_('xxxxxxxxxx\n', open(probe_path).read())

    # We can get back a report of what would happen rather than actually
    # rerunning anything.
    report = ds.rerun(since="", report=True, return_type="list")
    # The "diff" section of the report doesn't include the unchanged files that
    # would come in "-f json diff" output.
    for entry in report:
        if entry["rerun_action"] == "run":
            # None of the run commits touch .datalad/config or any other config
            # file.
            assert_false(any(r["path"].endswith("config")
                             for r in entry["diff"]))

    # Nothing changed.
    eq_('xxxxxxxxxx\n', open(probe_path).read())
    assert_result_count(report, 1, rerun_action="skip-or-pick")
    report[-1]["commit"] == ds.repo.get_hexsha()

    # If a file is dropped, we remove it instead of unlocking it.
    ds.drop(probe_path, reckless='kill')
    with swallow_outputs():
        ds.rerun()

    eq_('x\n', open(probe_path).read())


@with_tempfile(mkdir=True)
def test_rerun_empty_branch(path=None):
    GitRepo(path, create=True)
    ds = Dataset(path)
    assert_status("impossible", ds.rerun(on_failure="ignore"))


@with_tempfile(mkdir=True)
def test_rerun_onto(path=None):
    ds = Dataset(path).create()
    if ds.repo.is_managed_branch():
        assert_status('impossible',
                      ds.rerun(onto="triggers-abort", on_failure="ignore"))
        raise SkipTest("Test incompatible with adjusted branch")

    # Make sure we have more than one commit. The one commit case is checked
    # elsewhere.
    ds.repo.commit(msg="noop commit", options=["--allow-empty"])

    grow_file = op.join(path, "grows")

    # Make sure we can handle range-specifications that yield no results.
    for since in ["", "HEAD"]:
        assert_result_count(
            ds.rerun("HEAD", onto="", since=since, on_failure="ignore"),
            1, status="impossible", action="run")

    ds.run('echo static-content > static')
    ds.repo.tag("static")
    with swallow_outputs():
        ds.run(f'echo x$({cat_command} grows) > grows')
    ds.rerun()
    eq_('xx\n', open(grow_file).read())

    # If we run the "static" change on top of itself, we end up in the
    # same (but detached) place.
    ds.rerun(revision="static", onto="static")
    ok_(ds.repo.get_active_branch() is None)
    eq_(ds.repo.get_hexsha(),
        ds.repo.get_hexsha("static"))

    # If we run the "static" change from the same "base", we end up
    # with a new commit.
    ds.repo.checkout(DEFAULT_BRANCH)
    with swallow_outputs():
        ds.rerun(revision="static", onto="static^")
    ok_(ds.repo.get_active_branch() is None)
    neq_(ds.repo.get_hexsha(),
         ds.repo.get_hexsha("static"))
    ok_(all(r["state"] == "clean" for r in ds.diff(fr="HEAD", to="static")))
    for revrange in ["..static", "static.."]:
        eq_(len(ds.repo.get_revisions(revrange)), 1)

    # Unlike the static change, if we run the ever-growing change on
    # top of itself, we end up with a new commit.
    ds.repo.checkout(DEFAULT_BRANCH)
    ds.rerun(onto="HEAD")
    ok_(ds.repo.get_active_branch() is None)
    neq_(ds.repo.get_hexsha(),
         ds.repo.get_hexsha(DEFAULT_BRANCH))

    # An empty `onto` means use the parent of the first revision.
    ds.repo.checkout(DEFAULT_BRANCH)
    with swallow_outputs():
        ds.rerun(since="static^", onto="")
    ok_(ds.repo.get_active_branch() is None)
    for revrange in [".." + DEFAULT_BRANCH, DEFAULT_BRANCH + ".."]:
        eq_(len(ds.repo.get_revisions(revrange)), 3)

    # An empty `onto` means use the parent of the first revision that
    # has a run command.
    ds.repo.checkout(DEFAULT_BRANCH)
    with swallow_outputs():
        ds.rerun(since="", onto="", branch="from-base")
    eq_(ds.repo.get_active_branch(), "from-base")
    ok_(all(r["state"] == "clean"
            for r in ds.diff(fr=DEFAULT_BRANCH, to="from-base")))
    eq_(ds.repo.get_merge_base(["static", "from-base"]),
        ds.repo.get_hexsha("static^"))

    # We abort when an explicitly specified `onto` doesn't exist.
    ds.repo.checkout(DEFAULT_BRANCH)
    assert_result_count(
        ds.rerun(since="", onto="doesnotexist", branch="from-base",
                 on_failure="ignore"),
        1, status="error", action="run")


@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_chain(path=None):
    ds = Dataset(path).create()
    commits = []

    with swallow_outputs():
        ds.run(f'echo x$({cat_command} grows) > grows')
    ds.repo.tag("first-run", commit=DEFAULT_BRANCH)

    for _ in range(3):
        commits.append(ds.repo.get_hexsha(DEFAULT_BRANCH))
        ds.rerun()
        _, info = get_run_info(ds, last_commit_msg(ds.repo))
        eq_(info["chain"], commits)

    ds.rerun(revision="first-run")
    _, info = get_run_info(ds, last_commit_msg(ds.repo))
    eq_(info["chain"], commits[:1])


@with_tempfile(mkdir=True)
def test_rerun_just_one_commit(path=None):
    ds = Dataset(path).create()
    if ds.repo.is_managed_branch():
        assert_status('impossible',
                      ds.rerun(branch="triggers-abort", on_failure="ignore"))
        raise SkipTest("Test incompatible with adjusted branch")

    ds.repo.checkout("orph", options=["--orphan"])
    ds.repo.call_git(["reset", "--hard"])
    ds.repo.config.reload()

    ds.run('echo static-content > static')
    eq_(len(ds.repo.get_revisions("HEAD")), 1)
    assert_raises(IncompleteResultsError, ds.rerun)
    assert_raises(IncompleteResultsError, ds.rerun, since="", onto="")

    # --script propagates the error.
    with swallow_outputs():
        assert_raises(IncompleteResultsError,
                      ds.rerun, since="", onto="", script="-")
    # --dry-run propagates the error.
    assert_raises(IncompleteResultsError,
                  ds.rerun, since="", onto="",
                  report=True, return_type="list")


@with_tempfile(mkdir=True)
def test_run_failure(path=None):
    ds = Dataset(path).create()
    subds = ds.create("sub")

    hexsha_initial = ds.repo.get_hexsha()

    if on_windows:
        # this does not do exactly the same as the cmd on other systems
        # but is close enough to make running the test worthwhile
        cmd_failing = "echo x>{} & false".format(op.join("sub", "grows"))
    else:
        cmd_failing = ("echo x$(cat {0}) > {0} && false"
                       .format(op.join("sub", "grows")))

    with assert_raises(IncompleteResultsError):
        ds.run(cmd_failing, result_renderer=None)
    eq_(hexsha_initial, ds.repo.get_hexsha())
    ok_(ds.repo.dirty)

    msgfile = op.join(path, ds.repo.get_git_dir(ds.repo), "COMMIT_EDITMSG")
    ok_exists(msgfile)

    ds.save(recursive=True, message_file=msgfile)
    assert_repo_status(ds.path)
    neq_(hexsha_initial, ds.repo.get_hexsha())

    outfile = op.join(subds.path, "grows")
    eq_('x \n' if on_windows else 'x\n', open(outfile).read())

    if on_windows:
        # FIXME: Make the remaining code compatible with Windows.
        return

    # There is no CommandError on rerun if the non-zero error matches the
    # original code.
    ds.rerun()
    eq_('xx\n', open(outfile).read())

    # On the other hand, we fail if we rerun a command and there is a non-zero
    # error that doesn't match.
    ds.run("[ ! -e bar ] && echo c >bar")
    assert_repo_status(ds.path)
    assert_in_results(ds.rerun(result_renderer=None, on_failure="ignore"),
                      action="run", status="error")

    # We don't show instructions if the caller specified us not to save.
    remove(msgfile)
    with assert_raises(IncompleteResultsError):
        ds.run("false", explicit=True, outputs=None, on_failure="stop")
    assert_false(op.exists(msgfile))


@with_tempfile(mkdir=True)
def test_rerun_branch(path=None):
    ds = Dataset(path).create()
    if ds.repo.is_managed_branch():
        assert_status('impossible',
                      ds.rerun(branch="triggers-abort", on_failure="ignore"))
        raise SkipTest("Test incompatible with adjusted branch")

    ds.repo.tag("prerun")

    outfile = op.join(path, "run-file")

    with swallow_outputs():
        ds.run(f'echo x$({cat_command} run-file) > run-file')
    ds.rerun()
    eq_('xx\n', open(outfile).read())

    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.save("nonrun-file")

    # Rerun the commands on a new branch that starts at the parent
    # commit of the first run.
    with swallow_outputs():
        ds.rerun(since="prerun", onto="prerun", branch="rerun")

    eq_(ds.repo.get_active_branch(), "rerun")
    eq_('xx\n', open(outfile).read())

    # NOTE: This test depends on the non-run commit above following a run
    # commit.  Otherwise, all the metadata (e.g., author date) aside from the
    # parent commit that is used to generate the commit ID may be set when
    # running the tests, which would result in two commits rather than three.
    for revrange in ["rerun.." + DEFAULT_BRANCH, DEFAULT_BRANCH + "..rerun"]:
        eq_(len(ds.repo.get_revisions(revrange)), 3)
    eq_(ds.repo.get_merge_base([DEFAULT_BRANCH, "rerun"]),
        ds.repo.get_hexsha("prerun"))

    # Start rerun branch at tip of current branch.
    ds.repo.checkout(DEFAULT_BRANCH)
    ds.rerun(since="prerun", branch="rerun2")
    eq_(ds.repo.get_active_branch(), "rerun2")
    eq_('xxxx\n', open(outfile).read())

    eq_(len(ds.repo.get_revisions(DEFAULT_BRANCH + "..rerun2")), 2)
    eq_(len(ds.repo.get_revisions("rerun2.." + DEFAULT_BRANCH)), 0)

    # Using an existing branch name fails.
    ds.repo.checkout(DEFAULT_BRANCH)
    assert_raises(IncompleteResultsError,
                  ds.rerun, since="prerun", branch="rerun2")


@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_cherry_pick(path=None):
    ds = Dataset(path).create()

    ds.repo.tag("prerun")
    ds.run('echo abc > runfile')
    with open(op.join(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.save("nonrun-file")

    for onto, action in [("HEAD", "skip"), ("prerun", "pick")]:
        results = ds.rerun(since="prerun", onto=onto)
        assert_in_results(results, status='ok', rerun_action=action)


@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_rerun_invalid_merge_run_commit(path=None):
    ds = Dataset(path).create()
    ds.run("echo foo >>foo")
    ds.run("echo invalid >>invalid")
    run_msg = last_commit_msg(ds.repo)
    run_hexsha = ds.repo.get_hexsha()
    ds.repo.call_git(["reset", "--hard", DEFAULT_BRANCH + "~"])
    with open(op.join(ds.path, "non-run"), "w") as nrfh:
        nrfh.write("non-run")
    ds.save()
    # Assign two parents to the invalid run commit.
    commit = ds.repo.call_git_oneline(
        ["commit-tree", run_hexsha + "^{tree}", "-m", run_msg,
         "-p", run_hexsha + "^",
         "-p", ds.repo.get_hexsha()])
    ds.repo.call_git(["reset", "--hard", commit])
    hexsha_orig = ds.repo.get_hexsha()
    with swallow_logs(new_level=logging.WARN) as cml:
        ds.rerun(since="")
        assert_in("has run information but is a merge commit", cml.out)
    eq_(len(ds.repo.get_revisions(hexsha_orig + ".." + DEFAULT_BRANCH)), 1)


@with_tempfile(mkdir=True)
def test_rerun_outofdate_tree(path=None):
    ds = Dataset(path).create()
    input_file = op.join(path, "foo")
    output_file = op.join(path, "out")
    with open(input_file, "w") as f:
        f.write("abc\ndef")
    ds.save("foo", to_git=True)
    # Create initial run.
    ds.run(f'{grep_command} def foo > out')
    assert_in('def', open(output_file).read())
    # Change tree so that it is no longer compatible.
    ds.remove("foo")
    # Now rerunning should fail because foo no longer exists.
    assert_in_results(
        ds.rerun(revision=DEFAULT_BRANCH + "~",
                 result_renderer=None, on_failure="ignore"),
        status="error", action="run")


@with_tempfile(mkdir=True)
def test_rerun_ambiguous_revision_file(path=None):
    ds = Dataset(path).create()
    ds.run('echo ambig > ambig')
    ds.repo.tag("ambig", commit=DEFAULT_BRANCH)
    # Don't fail when "ambig" refers to both a file and revision.
    ds.rerun(since="", revision="ambig")
    eq_(len(ds.repo.get_revisions(DEFAULT_BRANCH)),
        len(ds.repo.get_revisions("ambig")))


@with_tree(tree={"subdir": {}})
def test_rerun_subdir(path=None):
    # Note: Using with_tree rather than with_tempfile is matters. The latter
    # calls realpath on the path, which masks a failure in the
    # TMPDIR="/var/tmp/sym link" test case
    ds = Dataset(path).create(force=True)
    subdir = op.join(path, 'subdir')
    with chpwd(subdir):
        run(touch_command + "test.dat")
    assert_repo_status(ds.path)

    # FIXME: A plain ok_file_under_git call doesn't properly resolve the file
    # in the TMPDIR="/var/tmp/sym link" test case. Temporarily call realpath.
    def ok_file_under_git_kludge(path, basename):
        ok_file_under_git(op.join(str(Path(path).resolve()), basename), annexed=True)

    ok_file_under_git_kludge(subdir, "test.dat")

    rec_msg, runinfo = get_run_info(ds, last_commit_msg(ds.repo))
    eq_(runinfo['pwd'], 'subdir')
    # now, rerun within root of the dataset
    with chpwd(ds.path):
        ds.rerun()
    assert_repo_status(ds.path)
    ok_file_under_git_kludge(subdir, "test.dat")
    # and not on top
    assert_raises(AssertionError, ok_file_under_git,
                  op.join(ds.path, "test.dat"), annexed=True)

    # but if we run ds.run -- runs within top of the dataset
    with chpwd(subdir):
        ds.run(touch_command + "test2.dat")
    assert_repo_status(ds.path)
    ok_file_under_git_kludge(ds.path, "test2.dat")
    rec_msg, runinfo = get_run_info(ds, last_commit_msg(ds.repo))
    eq_(runinfo['pwd'], '.')
    # now, rerun within subdir -- smoke for now
    with chpwd(subdir):
        ds.rerun()


@with_tree(tree={"d": {"to_modify": "content1"},
                 "to_remove": "content2",
                 "to_modify": "content3",
                 "unchanged": "content4"})
def test_new_or_modified(path=None):
    def get_new_or_modified(*args, **kwargs):
        return [op.relpath(ap["path"], path)
                for ap in new_or_modified(diff_revision(*args, **kwargs))]

    ds = Dataset(path).create(force=True, annex=False)

    # Check out an orphan branch so that we can test the "one commit
    # in a repo" case.
    ds.repo.checkout("orph", options=["--orphan"])
    ds.save()
    assert_false(ds.repo.dirty)
    eq_(len(ds.repo.get_revisions("HEAD")), 1)
    # Diffing doesn't fail when the branch contains a single commit.
    assert_in("to_modify", get_new_or_modified(ds, "HEAD"))

    # New files are detected, deletions are not.
    ds.repo.remove(["to_remove"])
    ok_(ds.repo.dirty)

    with open(op.join(path, "to_add"), "w") as f:
        f.write("content5")
    ds.repo.add(["to_add"])
    ds.repo.commit("add one, remove another")

    eq_(get_new_or_modified(ds, "HEAD"),
        ["to_add"])

    # Modifications are detected.
    with open(op.join(path, "to_modify"), "w") as f:
        f.write("updated 1")
    with open(op.join(path, "d/to_modify"), "w") as f:
        f.write("updated 2")
    ds.save(["to_modify", "d/to_modify"])

    eq_(set(get_new_or_modified(ds, "HEAD")),
        {"to_modify", op.join("d", "to_modify")})

    # Non-HEAD revisions work.
    ds.repo.commit("empty", options=["--allow-empty"])
    assert_false(get_new_or_modified(ds, "HEAD"))
    eq_(set(get_new_or_modified(ds, "HEAD~")),
        {"to_modify", op.join("d", "to_modify")})


@with_tempfile(mkdir=True)
def test_rerun_script(path=None):
    ds = Dataset(path).create()
    ds.run("echo a >foo")
    ds.run([touch_command + "bar"], message='BAR', sidecar=True)
    # a run record sidecar file was added with the last commit
    assert(any(d['path'].startswith(op.join(ds.path, '.datalad', 'runinfo'))
               for d in ds.rerun(report=True, return_type='item-or-list')['diff']))
    bar_hexsha = ds.repo.get_hexsha(DEFAULT_BRANCH)

    script_file = op.join(path, "commands.sh")

    ds.rerun(script=script_file)
    ok_exists(script_file)
    with open(script_file) as sf:
        lines = sf.readlines()
        assert_in(touch_command + "bar\n", lines)
        # The commit message is there too.
        assert_in("# BAR\n", lines)
        assert_in("# (record: {})\n".format(bar_hexsha), lines)
        assert_not_in("echo a >foo\n", lines)

    ds.rerun(since="", script=script_file)
    with open(script_file) as sf:
        lines = sf.readlines()
        assert_in(touch_command + "bar\n", lines)
        # Automatic commit messages aren't included.
        assert_not_in("# echo a >foo\n", lines)
        assert_in("echo a >foo\n", lines)

    # --script=- writes to stdout.
    with patch("sys.stdout", new_callable=StringIO) as cmout:
        ds.rerun(script="-")
        assert_in(touch_command + "bar",
                  cmout.getvalue().splitlines())


@slow  # ~10s
@known_failure_windows
@pytest.mark.xfail(reason="push fails due to IncompleteResultsError "
                          "[remote rejected] (branch is currently checked out)")
# ^ Issue only happens on appveyor, Python itself implodes. Cannot be
#   reproduced on a real win7 box
# Comment above looks outdated. Last trial on Appveyor failed, but seems related
# to unresolved globs:
# https://ci.appveyor.com/project/mih/datalad/builds/37951288/job/yxx47i3vtola2wek
@with_tree(tree={"input.dat": "input",
                 "extra-input.dat": "extra input",
                 "s0": {"s1_0": {"s2": {"a.dat": "a",
                                        "b.txt": "b"}},
                        "s1_1": {"s2": {"c.dat": "c",
                                        "d.txt": "d"}},
                        "ss": {"e.dat": "e"}}})
@with_tempfile(mkdir=True)
def test_run_inputs_outputs(src=None, path=None):
    for subds in [("s0", "s1_0", "s2"),
                  ("s0", "s1_1", "s2"),
                  ("s0", "s1_0"),
                  ("s0", "s1_1"),
                  ("s0", "ss"),
                  ("s0",)]:
        Dataset(op.join(*((src,) + subds))).create(force=True).save()
    src_ds = Dataset(src).create(force=True)
    src_ds.save()

    ds = install(path, source=src,
                 result_xfm='datasets', return_type='item-or-list')
    assert_false(ds.repo.file_has_content("input.dat"))
    assert_false(ds.repo.file_has_content("extra-input.dat"))

    # The specified inputs and extra inputs will be retrieved before the run.
    # (Use run_command() to access the extra_inputs argument.)
    list(run_command("{} {{inputs}} {{inputs}} >doubled.dat"
                     .format('type' if on_windows else 'cat'),
                     dataset=ds,
                     inputs=["input.dat"], extra_inputs=["extra-input.dat"]))

    assert_repo_status(ds.path)
    ok_(ds.repo.file_has_content("input.dat"))
    ok_(ds.repo.file_has_content("extra-input.dat"))
    ok_(ds.repo.file_has_content("doubled.dat"))
    with open(op.join(path, "doubled.dat")) as fh:
        content = fh.read()
        assert_in("input", content)
        assert_not_in("extra-input", content)

    # Rerunning the commit will also get the input file.
    ds.repo.drop(["input.dat", "extra-input.dat"], options=["--force"])
    assert_false(ds.repo.file_has_content("input.dat"))
    assert_false(ds.repo.file_has_content("extra-input.dat"))
    ds.rerun()
    ok_(ds.repo.file_has_content("input.dat"))
    ok_(ds.repo.file_has_content("extra-input.dat"))

    # Test different combinations of globs and explicit files.
    inputs = ["a.dat", "b.dat", "c.txt", "d.txt"]
    create_tree(ds.path, {i: i for i in inputs})

    ds.save()
    ds.push(inputs, to=DEFAULT_REMOTE)
    ds.repo.drop(inputs, options=["--force"])

    test_cases = [(["*.dat"], ["a.dat", "b.dat"]),
                  (["*.dat", "c.txt"], ["a.dat", "b.dat", "c.txt"]),
                  (["*"], inputs)]

    for idx, (inputs_arg, expected_present) in enumerate(test_cases):
        assert_false(any(ds.repo.file_has_content(i) for i in inputs))

        ds.run("cd .> dummy{}".format(idx), inputs=inputs_arg)
        ok_(all(ds.repo.file_has_content(f) for f in expected_present))
        # Globs are stored unexpanded by default.
        assert_in(inputs_arg[0], last_commit_msg(ds.repo))
        ds.repo.drop(inputs, options=["--force"])

    # --input can be passed a subdirectory.
    create_tree(ds.path, {"subdir": {"a": "subdir a",
                                     "b": "subdir b"}})
    ds.save("subdir")
    ds.push(["subdir/a", "subdir/b"], to=DEFAULT_REMOTE)
    ds.repo.drop("subdir", options=["--force"])
    ds.run("cd .> subdir-dummy", inputs=[op.join(ds.path, "subdir")])
    ok_(all(ds.repo.file_has_content(op.join("subdir", f)) for f in ["a", "b"]))

    # Inputs are specified relative to a dataset's subdirectory.
    ds.repo.drop(op.join("subdir", "a"), options=["--force"])
    with chpwd(op.join(path, "subdir")):
        run("cd .> subdir-dummy1", inputs=["a"])
    ok_(ds.repo.file_has_content(op.join("subdir", "a")))

    # --input=. runs "datalad get ."
    ds.run("cd .> dot-dummy", inputs=["."])
    eq_(ds.repo.get_annexed_files(),
        ds.repo.get_annexed_files(with_content_only=True))
    # On rerun, we get all files, even those that weren't in the tree at the
    # time of the run.
    create_tree(ds.path, {"after-dot-run": "after-dot-run content"})
    ds.save()
    ds.push(["after-dot-run"], to=DEFAULT_REMOTE)
    ds.repo.drop(["after-dot-run"], options=["--force"])
    ds.rerun(DEFAULT_BRANCH + "^")
    ds.repo.file_has_content("after-dot-run")

    # --output will unlock files that are present.
    ds.repo.get("a.dat")
    ds.run("echo ' appended' >>a.dat", outputs=["a.dat"])
    with open(op.join(path, "a.dat")) as fh:
        eq_(fh.read(), "a.dat' appended' \n" if on_windows else "a.dat appended\n" )

    # --output will remove files that are not present.
    ds.repo.drop(["a.dat", "d.txt"], options=["--force"])
    ds.run("echo ' appended' >>a.dat", outputs=["a.dat"])
    if not on_windows:
        # MIH doesn't yet understand how to port this
        with open(op.join(path, "a.dat")) as fh:
            eq_(fh.read(), " appended\n" )

    # --input can be combined with --output.
    ds.run("echo ' appended' >>a.dat", inputs=["a.dat"], outputs=["a.dat"])
    if not on_windows:
        # MIH doesn't yet understand how to port this
        with open(op.join(path, "a.dat")) as fh:
            eq_(fh.read(), " appended\n appended\n")

    ds.create('sub')
    ds.run("echo sub_orig >sub/subfile")
    ds.run("echo sub_overwrite >sub/subfile", outputs=["sub/subfile"])
    ds.drop("sub/subfile", reckless='kill')
    ds.run("echo sub_overwrite >sub/subfile", outputs=["sub/subfile"])

    # --input/--output globs can be stored in expanded form.
    ds.run("cd .> expand-dummy", inputs=["a.*"], outputs=["b.*"], expand="both")
    assert_in("a.dat", last_commit_msg(ds.repo))
    assert_in("b.dat", last_commit_msg(ds.repo))

    res = ds.rerun(report=True, return_type='item-or-list')
    eq_(res["run_info"]['inputs'], ["a.dat"])
    eq_(res["run_info"]['outputs'], ["b.dat"])

    # We uninstall subdatasets to fully resolve globs.
    ds.drop("s0", what='all', reckless='kill', recursive=True)
    assert_false(Dataset(op.join(path, "s0")).is_installed())
    ds.run("echo {inputs} >globbed-subds", inputs=["s0/s1_*/s2/*.dat"])
    ok_file_has_content(
        op.join(ds.path, "globbed-subds"),
        "'s0\\s1_0\\s2\\a.dat' 's0\\s1_1\\s2\\c.dat'" if on_windows
        else "s0/s1_0/s2/a.dat s0/s1_1/s2/c.dat",
        strip=True)

    ds_ss = Dataset(op.join(path, "s0", "ss"))
    assert_false(ds_ss.is_installed())
    ds.run("echo blah >{outputs}", outputs=["s0/ss/out"])
    ok_(ds_ss.is_installed())
    ok_file_has_content(op.join(ds.path, "s0", "ss", "out"),
                        "blah",
                        strip=True)


@with_tree({"foo": "foo"})
def test_run_inputs_no_annex_repo(path=None):
    ds = Dataset(path).create(annex=False, force=True)
    ds.save()
    # Running --input in a plain Git repo doesn't fail.
    ds.run("cd .> dummy", inputs=["*"])
    ok_exists(op.join(ds.path, "dummy"))
    ds.rerun()


@skip_if_adjusted_branch
@with_tree(tree={"to_modify": "to_modify"})
def test_rerun_explicit(path=None):
    ds = Dataset(path).create(force=True)

    ds.run("echo o >> foo", explicit=True, outputs=["foo"])
    with open(op.join(ds.path, "foo")) as ifh:
        orig_content = ifh.read()
        orig_head = ds.repo.get_hexsha(DEFAULT_BRANCH)

    # Explicit rerun is allowed in a dirty tree.
    ok_(ds.repo.dirty)
    ds.rerun(explicit=True)
    eq_(orig_head, ds.repo.get_hexsha(DEFAULT_BRANCH + "~1"))
    with open(op.join(ds.path, "foo")) as ifh:
        eq_(orig_content * 2, ifh.read())

    # --since also works.
    ds.rerun(since="", explicit=True)
    eq_(orig_head,
        # Added two rerun commits.
        ds.repo.get_hexsha(DEFAULT_BRANCH + "~3"))

    # With just untracked changes, we can rerun with --onto.
    ds.rerun(since="", onto="", explicit=True)
    eq_(ds.repo.get_hexsha(orig_head + "^"),
        # Reran the four run commits from above on the initial base.
        ds.repo.get_hexsha("HEAD~4"))

    # But checking out a new HEAD can fail when there are modifications.
    ds.repo.checkout(DEFAULT_BRANCH)
    ok_(ds.repo.dirty)
    ds.repo.add(["to_modify"], git=True)
    ds.save()
    assert_false(ds.repo.dirty)
    with open(op.join(ds.path, "to_modify"), "a") as ofh:
        ofh.write("more")
    ok_(ds.repo.dirty)

    with assert_raises(CommandError):
        ds.rerun(onto="", since="", explicit=True)


@with_tempfile(mkdir=True)
def test_rerun_assume_ready(path=None):
    ds = Dataset(path).create()
    repo = ds.repo
    (repo.pathobj / "f1").write_text("f1\n")
    ds.save()

    def double_in_both_cmd(src, dest1, dest2):
        return [
            sys.executable, "-c",
            "import sys; import os; import os.path as op; "
            "content = open(sys.argv[-3]).read() * 2; "
            "d1 = sys.argv[-2]; d2 = sys.argv[-1]; "
            "op.lexists(d1) and os.unlink(d1); "
            "op.lexists(d2) and os.unlink(d2); "
            "open(d1, 'w').write(content); open(d2, 'w').write(content)",
            src, dest1, dest2]

    ds.run(double_in_both_cmd("f1", "out1", "out2"), outputs=["out1"])
    # Drop the content so that we remove instead of unlock, making the test is
    # more meaningful on an adjusted branch.
    ds.drop(["out1", "out2"], reckless='kill')
    # --assume-ready affects both explicitly specified and automatic outputs.
    res = ds.rerun(assume_ready="outputs")
    assert_not_in_results(res, action="remove")


# underlying code cannot deal with adjusted branches
# https://github.com/datalad/datalad/pull/3817
@known_failure_windows
@with_tree(tree={"a.in": "a", "b.in": "b", "c.out": "c",
                 "subdir": {}})
def test_placeholders(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    assert_repo_status(ds.path)
    # ATTN windows is sensitive to spaces before redirect symbol
    ds.run("echo {inputs}>{outputs}", inputs=[".", "*.in"], outputs=["c.out"])
    ok_file_has_content(op.join(path, "c.out"), "a.in b.in\n")

    hexsha_before = ds.repo.get_hexsha()
    ds.rerun()
    eq_(hexsha_before, ds.repo.get_hexsha())

    # ATTN windows is sensitive to spaces before redirect symbol
    ds.run("echo {inputs[0]}>getitem", inputs=["*.in"])
    ok_file_has_content(op.join(path, "getitem"), "a.in\n")

    ds.run("echo {pwd} >expanded-pwd")
    ok_file_has_content(op.join(path, "expanded-pwd"), path,
                        strip=True)

    ds.run("echo {dspath} >expanded-dspath")
    ok_file_has_content(op.join(path, "expanded-dspath"), ds.path,
                        strip=True)

    subdir_path = op.join(path, "subdir")
    with chpwd(subdir_path):
        run("echo {pwd} >expanded-pwd")
    ok_file_has_content(op.join(path, "subdir", "expanded-pwd"), subdir_path,
                        strip=True)
    eq_(get_run_info(ds, last_commit_msg(ds.repo))[1]["pwd"],
        "subdir")

    # Double brackets can be used to escape placeholders.
    ds.run("cd .> {{inputs}}", inputs=["*.in"])
    ok_exists(op.join(path, "{inputs}"))

    # rerun --script expands the placeholders.
    with patch("sys.stdout", new_callable=StringIO) as cmout:
        ds.rerun(script="-", since="")
        script_out = cmout.getvalue()
        assert_in("echo a.in b.in>c.out", script_out)
        assert_in("echo {} >expanded-pwd".format(subdir_path),
                  script_out)
        assert_in("echo {} >expanded-dspath".format(ds.path),
                  script_out)

    assert_result_count(
        ds.run("{unknown_placeholder}", on_failure="ignore"),
        1, status="impossible", action="run")

    # Configured placeholders.
    ds.config.add("datalad.run.substitutions.license", "gpl3", scope="local")
    ds.run("echo {license} >configured-license")
    ok_file_has_content(op.join(path, "configured-license"), "gpl3",
                        strip=True)
    # --script handles configured placeholders.
    with patch("sys.stdout", new_callable=StringIO) as cmout:
        ds.rerun(script="-")
        assert_in("gpl3", cmout.getvalue())

    ds.run("echo {tmpdir} >tout")
    ok_file_has_content(op.join(path, "tout"), ".*datalad-run.*", re_=True)


def test_rerun_commit_message_check():
    assert_raises(ValueError,
                  get_run_info,
                  None,
                  """\
[DATALAD RUNCMD] no command

=== Do not change lines below ===
{
 "pwd": ".",
 "exit": 0
}
^^^ Do not change lines above ^^^""")

    assert_raises(ValueError,
                  get_run_info,
                  None,
                  """\
[DATALAD RUNCMD] junk json

=== Do not change lines below ===
{
 "pwd": ".,
 "cmd": "echo ok >okfile",
 "exit": 0
}
^^^ Do not change lines above ^^^""")

    subject, info = get_run_info(
        None,
        """\
[DATALAD RUNCMD] fine

=== Do not change lines below ===
{
 "pwd": ".",
 "cmd": "echo ok >okfile",
 "exit": 0
}
^^^ Do not change lines above ^^^""")
    eq_(subject, "fine")
    assert_dict_equal(info,
                      {"pwd": ".", "cmd": "echo ok >okfile", "exit": 0})
