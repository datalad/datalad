# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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

from datalad.tests.utils import (
    known_failure_direct_mode,
    known_failure_v6,
)

from os.path import join as opj
from os.path import relpath
from os import mkdir
from datalad.utils import chpwd

from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.support.exceptions import CommandError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.gitrepo import GitCommandError
from datalad.tests.utils import ok_, assert_false, neq_
from datalad.api import run
from datalad.interface.rerun import get_commit_runinfo, new_or_modified
from datalad.tests.utils import assert_raises
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import ok_file_under_git
from datalad.tests.utils import create_tree
from datalad.tests.utils import eq_
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_in_results
from datalad.tests.utils import skip_if_on_windows
from datalad.tests.utils import ignore_nose_capturing_stdout
from datalad.tests.utils import swallow_logs


@with_tempfile(mkdir=True)
def test_invalid_call(path):
    with chpwd(path):
        # no dataset, no luck
        assert_raises(NoDatasetArgumentFound, run, 'doesntmatter')
        # dirty dataset
        ds = Dataset(path).create()
        create_tree(ds.path, {'this': 'dirty'})
        assert_status('impossible', run('doesntmatter', on_failure='ignore'))


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_basics(path, nodspath):
    ds = Dataset(path).create()
    last_state = ds.repo.get_hexsha()
    # run inside the dataset
    with chpwd(path):
        # provoke command failure
        with assert_raises(CommandError) as cme:
            ds.run('7i3amhmuch9invalid')
            # let's not speculate that the exit code is always 127
            ok_(cme.code > 0)
        eq_(last_state, ds.repo.get_hexsha())
        # now one that must work
        res = ds.run('touch empty', message='TEST')
        ok_clean_git(ds.path)
        assert_result_count(res, 2)
        # TODO 'state' is still untracked!!!
        assert_result_count(res, 1, action='add', path=opj(ds.path, 'empty'), type='file')
        assert_result_count(res, 1, action='save', path=ds.path)
        commit_msg = ds.repo.repo.head.commit.message
        ok_(commit_msg.startswith('[DATALAD RUNCMD] TEST'))
        # crude test that we have a record for the PWD
        assert_in('"pwd": "."', commit_msg)
        last_state = ds.repo.get_hexsha()
        # now run a command that will not alter the dataset
        res = ds.run('touch empty', message='NOOP_TEST')
        assert_status('notneeded', res)
        eq_(last_state, ds.repo.get_hexsha())

    # run outside the dataset, should still work but with limitations
    with chpwd(nodspath):
        res = ds.run(['touch', 'empty2'], message='TEST')
        assert_status('ok', res)
        assert_result_count(res, 1, action='add', path=opj(ds.path, 'empty2'), type='file')

    # running without a command is a noop
    with chpwd(path):
        with swallow_logs(new_level=logging.WARN) as cml:
            ds.run()
            assert_in("No command given", cml.out)


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_rerun(path, nodspath):
    ds = Dataset(path).create()
    sub = ds.create('sub')
    probe_path = opj(sub.path, 'sequence')
    # run inside the dataset
    with chpwd(path):
        ds.run('echo x$(cat sub/sequence) > sub/sequence')
    # command ran once, all clean
    ok_clean_git(ds.path)
    eq_('x\n', open(probe_path).read())
    # now, for a rerun we can be anywhere, PWD and all are recorded
    # moreover, rerun must figure out which bits to unlock, even in
    # subdatasets
    with chpwd(nodspath):
        ds.rerun()
    ok_clean_git(ds.path)
    # ran twice now
    eq_('xx\n', open(probe_path).read())
    # Make a non-run commit.
    with open(opj(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.add("nonrun-file")
    # Now rerun the buried command.
    ds.rerun(revision="HEAD~", message="rerun buried")
    eq_('xxx\n', open(probe_path).read())
    # Also check that the messasge override worked.
    eq_(ds.repo.repo.head.commit.message.splitlines()[0],
        "[DATALAD RUNCMD] rerun buried")
    # Or a range of commits, skipping non-run commits.
    ds.rerun(since="HEAD~3")
    eq_('xxxxx\n', open(probe_path).read())
    # Or --since= to run all reachable commits.
    ds.rerun(since="")
    eq_('xxxxxxxxxx\n', open(probe_path).read())
    # If the history to rerun has a merge commit, we abort.
    ds.repo.checkout("HEAD~3", options=["-b", "topic"])
    with open(opj(path, "topic-file"), "w") as f:
        f.write("topic")
    ds.add("topic-file")
    ds.repo.checkout("master")
    ds.repo.merge("topic")
    ok_clean_git(ds.path)
    assert_raises(IncompleteResultsError, ds.rerun)


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
@known_failure_v6  #FIXME
def test_rerun_onto(path):
    ds = Dataset(path).create()

    grow_file = opj(path, "grows")

    ds.run('echo static-content > static')
    ds.repo.repo.git.tag("static")
    ds.run('echo x$(cat grows) > grows')
    ds.rerun()
    eq_('xx\n', open(grow_file).read())

    # If we run the "static" change on top of itself, we end up in the
    # same (but detached) place.
    ds.rerun(revision="static", onto="static")
    ok_(ds.repo.get_active_branch() is None)
    eq_(ds.repo.repo.git.rev_parse("HEAD"),
        ds.repo.repo.git.rev_parse("static"))

    # If we run the "static" change from the same "base", we end up
    # with a new commit.
    ds.repo.checkout("master")
    ds.rerun(revision="static", onto="static^")
    ok_(ds.repo.get_active_branch() is None)
    neq_(ds.repo.repo.git.rev_parse("HEAD"),
         ds.repo.repo.git.rev_parse("static"))
    assert_result_count(ds.diff(revision="HEAD..static"), 0)
    for revrange in ["..static", "static.."]:
        assert_result_count(
            ds.repo.repo.git.rev_list(revrange).split(), 1)

    # Unlike the static change, if we run the ever-growing change on
    # top of itself, we end up with a new commit.
    ds.repo.checkout("master")
    ds.rerun(onto="HEAD")
    ok_(ds.repo.get_active_branch() is None)
    neq_(ds.repo.repo.git.rev_parse("HEAD"),
         ds.repo.repo.git.rev_parse("master"))

    # An empty `onto` means use the parent of the first revision.
    ds.repo.checkout("master")
    ds.rerun(since="static^", onto="")
    ok_(ds.repo.get_active_branch() is None)
    for revrange in ["..master", "master.."]:
        assert_result_count(
            ds.repo.repo.git.rev_list(revrange).split(), 3)

    # An empty `onto` means use the parent of the first revision that
    # has a run command.
    ds.repo.checkout("master")
    ds.rerun(since="", onto="", branch="from-base")
    eq_(ds.repo.get_active_branch(), "from-base")
    assert_result_count(ds.diff(revision="master..from-base"), 0)
    eq_(ds.repo.get_merge_base(["static", "from-base"]),
        ds.repo.repo.git.rev_parse("static^"))


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
@known_failure_v6  #FIXME
def test_rerun_chain(path):
    ds = Dataset(path).create()
    commits = []

    grow_file = opj(path, "grows")
    ds.run('echo x$(cat grows) > grows')
    ds.repo.repo.git.tag("first-run")

    for _ in range(3):
        commits.append(ds.repo.get_hexsha())
        ds.rerun()
        _, info = get_commit_runinfo(ds.repo, "HEAD")
        assert info["chain"] == commits

    ds.rerun(revision="first-run")
    _, info = get_commit_runinfo(ds.repo, "HEAD")
    assert info["chain"] == commits[:1]


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
def test_rerun_old_flag_compatibility(path):
    ds = Dataset(path).create()
    ds.run("echo x$(cat grows) > grows")
    # Deprecated `datalad --rerun` still runs the last commit's
    # command.
    ds.run(rerun=True)
    eq_("xx\n", open(opj(path, "grows")).read())
    # Running with --rerun and a command ignores the command.
    with swallow_logs(new_level=logging.WARN) as cml:
        ds.run(rerun=True, cmd="ignored")
        assert_in("Ignoring provided command in --rerun mode", cml.out)
        eq_("xxx\n", open(opj(path, "grows")).read())


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
@known_failure_v6  #FIXME
def test_rerun_just_one_commit(path):
    ds = Dataset(path).create()

    # Check out an orphan branch so that we can test the "one commit
    # in a repo" case.
    ds.repo.checkout("orph", options=["--orphan"])
    ds.repo.repo.git.reset("--hard")

    ds.run('echo static-content > static')
    assert_result_count(ds.repo.repo.git.rev_list("HEAD").split(), 1)

    # Rerunning with just one commit doesn't raise an error ...
    ds.rerun()
    # ... but we're still at one commit because the content didn't
    # change.
    assert_result_count(ds.repo.repo.git.rev_list("HEAD").split(), 1)

    # We abort rather than trying to do anything when --onto='' and
    # --since='' are given together and the first commit contains a
    # run command.
    ds.repo.commit(msg="empty", options=["--allow-empty"])
    assert_raises(IncompleteResultsError, ds.rerun, since="", onto="")


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_rerun_branch(path):
    ds = Dataset(path).create()

    ds.repo.repo.git.tag("prerun")

    outfile = opj(path, "run-file")

    ds.run('echo x$(cat run-file) > run-file')
    ds.rerun()
    eq_('xx\n', open(outfile).read())

    with open(opj(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.add("nonrun-file")

    # Rerun the commands on a new branch that starts at the parent
    # commit of the first run.
    ds.rerun(since="prerun", onto="prerun", branch="rerun")

    eq_(ds.repo.get_active_branch(), "rerun")
    eq_('xx\n', open(outfile).read())

    # NOTE: This test depends on the non-run commit above following a run
    # commit.  Otherwise, all the metadata (e.g., author date) aside from the
    # parent commit that is used to generate the commit ID may be set when
    # running the tests, which would result in two commits rather than three.
    for revrange in ["rerun..master", "master..rerun"]:
        assert_result_count(
            ds.repo.repo.git.rev_list(revrange).split(), 3)
    eq_(ds.repo.get_merge_base(["master", "rerun"]),
        ds.repo.repo.git.rev_parse("prerun"))

    # Start rerun branch at tip of current branch.
    ds.repo.checkout("master")
    ds.rerun(since="prerun", branch="rerun2")
    eq_(ds.repo.get_active_branch(), "rerun2")
    eq_('xxxx\n', open(outfile).read())

    assert_result_count(
        ds.repo.repo.git.rev_list("master..rerun2").split(), 2)
    assert_result_count(
        ds.repo.repo.git.rev_list("rerun2..master").split(), 0)

    # Using an existing branch name fails.
    ds.repo.checkout("master")
    assert_raises(IncompleteResultsError,
                  ds.rerun, since="prerun", branch="rerun2")


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
@known_failure_v6  #FIXME
def test_rerun_cherry_pick(path):
    ds = Dataset(path).create()

    ds.repo.repo.git.tag("prerun")
    ds.run('echo abc > runfile')
    with open(opj(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.add("nonrun-file")

    for onto, text in [("HEAD", "skipping"), ("prerun", "cherry picking")]:
        results = ds.rerun(since="prerun", onto=onto)
        assert_in_results(results, status='ok', path=ds.path)
        assert any(r.get("message", "").endswith(text) for r in results)


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
@known_failure_v6  #FIXME
def test_rerun_outofdate_tree(path):
    ds = Dataset(path).create()
    input_file = opj(path, "foo")
    output_file = opj(path, "out")
    with open(input_file, "w") as f:
        f.write("abc\ndef")
    ds.add("foo", to_git=True)
    # Create inital run.
    ds.run('grep def foo > out')
    eq_('def\n', open(output_file).read())
    # Change tree so that it is no longer compatible.
    ds.remove("foo")
    # Now rerunning should fail because foo no longer exists.
    assert_raises(CommandError, ds.rerun, revision="HEAD~")


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
@known_failure_v6  #FIXME
def test_rerun_ambiguous_revision_file(path):
    ds = Dataset(path).create()
    ds.run('echo ambig > ambig')
    ds.repo.repo.git.tag("ambig")
    # Don't fail when "ambig" refers to both a file and revision.
    ds.rerun(since="", revision="ambig", branch="rerun")
    eq_(len(ds.repo.repo.git.rev_list("rerun").split()),
        len(ds.repo.repo.git.rev_list("ambig", "--").split()))


@ignore_nose_capturing_stdout
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
@known_failure_v6  #FIXME
def test_rerun_subdir(path):
    ds = Dataset(path).create()
    subdir = opj(path, 'subdir')
    mkdir(subdir)
    with chpwd(subdir):
        run("python -c 'open(\"test.dat\", \"wb\").close()'")
    ok_clean_git(ds.path)
    ok_file_under_git(opj(subdir, "test.dat"), annexed=True)
    rec_msg, runinfo = get_commit_runinfo(ds.repo)
    eq_(runinfo['pwd'], 'subdir')
    # now, rerun within root of the dataset
    with chpwd(ds.path):
        ds.rerun()
    ok_clean_git(ds.path)
    ok_file_under_git(opj(subdir, "test.dat"), annexed=True)
    # and not on top
    assert_raises(AssertionError, ok_file_under_git, opj(ds.path, "test.dat"), annexed=True)

    # but if we run ds.run -- runs within top of the dataset
    with chpwd(subdir):
        ds.run("python -c 'open(\"test2.dat\", \"wb\").close()'")
    ok_clean_git(ds.path)
    ok_file_under_git(opj(ds.path, "test2.dat"), annexed=True)
    rec_msg, runinfo = get_commit_runinfo(ds.repo)
    eq_(runinfo['pwd'], '.')
    # now, rerun within subdir -- smoke for now
    with chpwd(subdir):
        ds.rerun()


@with_tree(tree={"d": {"to_modify": "content1"},
                 "to_remove": "content2",
                 "to_modify": "content3",
                 "unchanged": "content4"})
def test_new_or_modified(path):
    def apfiles(aps):
        for ap in aps:
            yield relpath(ap["path"], path)

    ds = Dataset(path).create(force=True, no_annex=True)

    # Check out an orphan branch so that we can test the "one commit
    # in a repo" case.
    ds.repo.checkout("orph", options=["--orphan"])
    ds.repo.add(".", commit=True)
    assert_false(ds.repo.dirty)
    assert_result_count(ds.repo.repo.git.rev_list("HEAD").split(), 1)
    # Diffing doesn't fail when the branch contains a single commit.
    assert_in("to_modify", apfiles(new_or_modified(ds, "HEAD")))

    # New files are detected, deletions are not.
    ds.repo.remove(["to_remove"])
    ok_(ds.repo.dirty)

    with open(opj(path, "to_add"), "w") as f:
        f.write("content5")
    ds.repo.add(["to_add"], commit=True)
    ds.repo.commit("add one, remove another")

    eq_(list(apfiles(new_or_modified(ds, "HEAD"))),
        ["to_add"])

    # Modifications are detected.
    with open(opj(path, "to_modify"), "w") as f:
        f.write("updated 1")
    with open(opj(path, "d/to_modify"), "w") as f:
        f.write("updated 2")
    ds.repo.add(["to_modify", "d/to_modify"], commit=True)

    eq_(set(apfiles(new_or_modified(ds, "HEAD"))),
        {"to_modify", "d/to_modify"})

    # Non-HEAD revisions work.
    ds.repo.commit("empty", options=["--allow-empty"])
    assert_false(list(apfiles(new_or_modified(ds, "HEAD"))))
    eq_(set(apfiles(new_or_modified(ds, "HEAD~"))),
        {"to_modify", "d/to_modify"})


@with_tempfile(mkdir=True)
def test_rerun_commit_message_check(path):
    ds = Dataset(path).create()
    ds.repo.commit(options=["--allow-empty"], msg="""\
[DATALAD RUNCMD] no command

=== Do not change lines below ===
{
 "pwd": ".",
 "exit": 0
}
^^^ Do not change lines above ^^^""")

    ds.repo.commit(options=["--allow-empty"], msg="""\
[DATALAD RUNCMD] junk json

=== Do not change lines below ===
{
 "pwd": ".,
 "cmd": "echo ok >okfile",
 "exit": 0
}
^^^ Do not change lines above ^^^""")

    ds.repo.commit(options=["--allow-empty"], msg="""\
[DATALAD RUNCMD] fine

=== Do not change lines below ===
{
 "pwd": ".",
 "cmd": "echo ok >okfile",
 "exit": 0
}
^^^ Do not change lines above ^^^""")

    assert_raises(ValueError,
                  get_commit_runinfo, ds.repo, "HEAD~2")
    assert_raises(ValueError,
                  get_commit_runinfo, ds.repo, "HEAD~")

    get_commit_runinfo(ds.repo, "HEAD")
