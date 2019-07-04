# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
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

from datalad.tests.utils import known_failure_direct_mode

import os.path as op
from os.path import join as opj
from os.path import relpath
from os import mkdir, remove
import sys

from six import PY2
from six.moves import StringIO
from mock import patch

from datalad.utils import assure_unicode
from datalad.utils import chpwd

from datalad.cmdline.main import main
from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.support.exceptions import CommandError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils import ok_, assert_false, neq_
from datalad.api import install
from datalad.api import run
from datalad.interface.run import format_command
from datalad.interface.run import run_command
from datalad.interface.rerun import get_run_info
from datalad.interface.rerun import diff_revision, new_or_modified
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import ok_exists
from datalad.tests.utils import ok_file_under_git
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import create_tree
from datalad.tests.utils import eq_
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import assert_in_results
from datalad.tests.utils import known_failure_windows
from datalad.tests.utils import slow
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import OBSCURE_FILENAME


@with_tempfile(mkdir=True)
def test_invalid_call(path):
    with chpwd(path):
        # no dataset, no luck
        assert_raises(NoDatasetArgumentFound, run, 'doesntmatter')
        # dirty dataset
        ds = Dataset(path).create()
        create_tree(ds.path, {'this': 'dirty'})
        assert_status('impossible', run('doesntmatter', on_failure='ignore'))


@known_failure_windows
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_basics(path, nodspath):
    ds = Dataset(path).create()
    direct_mode = ds.repo.is_direct_mode()
    last_state = ds.repo.get_hexsha()
    # run inside the dataset
    with chpwd(path), \
            swallow_outputs():
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
        commit_msg = ds.repo.format_commit("%B")
        ok_(commit_msg.startswith('[DATALAD RUNCMD] TEST'))
        # crude test that we have a record for the PWD
        assert_in('"pwd": "."', commit_msg)
        last_state = ds.repo.get_hexsha()
        # now run a command that will not alter the dataset
        res = ds.run('touch empty', message='NOOP_TEST')
        # When in direct mode, check at the level of save rather than add
        # because the annex files show up as typechanges and adding them won't
        # necessarily have a "notneeded" status.
        assert_result_count(res, 1, action='save' if direct_mode else 'add',
                            status='notneeded')
        eq_(last_state, ds.repo.get_hexsha())
        # We can also run the command via a single-item list because this is
        # what the CLI interface passes in for quoted commands.
        res = ds.run(['touch empty'], message='NOOP_TEST')
        assert_result_count(res, 1, action='save' if direct_mode else 'add',
                            status='notneeded')

    # run outside the dataset, should still work but with limitations
    with chpwd(nodspath), \
            swallow_outputs():
        res = ds.run(['touch', 'empty2'], message='TEST')
        assert_result_count(res, 1, action='add', path=opj(ds.path, 'empty2'), type='file',
                            status='ok')
        assert_result_count(res, 1, action='save', status='ok')

    # running without a command is a noop
    with chpwd(path):
        with swallow_logs(new_level=logging.WARN) as cml:
            ds.run()
            assert_in("No command given", cml.out)


@with_tempfile(mkdir=True)
def test_py2_unicode_command(path):
    # Avoid OBSCURE_FILENAME to avoid windows-breakage (gh-2929).
    ds = Dataset(path).create()
    touch_cmd = "import sys; open(sys.argv[1], 'w').write('')"
    cmd_str = u"{} -c \"{}\" {}".format(sys.executable,
                                        touch_cmd,
                                        u"bβ0.dat")
    ds.run(cmd_str)
    ok_clean_git(ds.path)
    ok_exists(op.join(path, u"bβ0.dat"))

    ds.run([sys.executable, "-c", touch_cmd, u"bβ1.dat"])
    ok_clean_git(ds.path)
    ok_exists(op.join(path, u"bβ1.dat"))

    # Send in a list of byte-strings to mimic a py2 command-line invocation.
    ds.run([s.encode("utf-8")
            for s in [sys.executable, "-c", touch_cmd, u" β1 "]])
    ok_clean_git(ds.path)
    ok_exists(op.join(path, u" β1 "))

    with assert_raises(CommandError), swallow_outputs():
        ds.run(u"bβ2.dat")


@known_failure_windows
@with_tempfile(mkdir=True)
def test_sidecar(path):
    ds = Dataset(path).create()
    # Simple sidecar message checks.
    ds.run(["touch", "dummy0"], message="sidecar arg", sidecar=True)
    assert_not_in('"cmd":', ds.repo.format_commit("%B"))

    ds.config.set("datalad.run.record-sidecar", "false", where="local")
    ds.run(["touch", "dummy1"], message="sidecar config")
    assert_in('"cmd":', ds.repo.format_commit("%B"))

    ds.config.set("datalad.run.record-sidecar", "true", where="local")
    ds.run(["touch", "dummy1"], message="sidecar config")
    assert_not_in('"cmd":', ds.repo.format_commit("%B"))

    # Don't break when config.get() returns multiple values. Here it's two
    # values in .gitconfig, but a more realistic scenario is a value in
    # $repo/.git/config that overrides a setting in ~/.config/git/config.
    ds.config.add("datalad.run.record-sidecar", "false", where="local")
    ds.run(["touch", "dummy2"], message="sidecar config")
    assert_in('"cmd":', ds.repo.format_commit("%B"))


@slow  # 17.1880s
@known_failure_windows
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_rerun(path, nodspath):
    ds = Dataset(path).create()
    sub = ds.create('sub')
    probe_path = opj(sub.path, 'sequence')
    # run inside the dataset
    with chpwd(path), \
            swallow_outputs():
        ds.run('echo x$(cat sub/sequence) > sub/sequence')
    # command ran once, all clean
    ok_clean_git(ds.path)
    eq_('x\n', open(probe_path).read())
    # now, for a rerun we can be anywhere, PWD and all are recorded
    # moreover, rerun must figure out which bits to unlock, even in
    # subdatasets
    with chpwd(nodspath), \
            swallow_outputs():
        ds.rerun()
    ok_clean_git(ds.path)
    # ran twice now
    eq_('xx\n', open(probe_path).read())

    # Rerunning from a subdataset skips the command.
    _, sub_info = get_run_info(ds, sub.repo.repo.head.commit.message)
    eq_(ds.id, sub_info["dsid"])
    assert_result_count(
        sub.rerun(return_type="list", on_failure="ignore"),
        1, status="impossible", action="run", rerun_action="skip")
    eq_('xx\n', open(probe_path).read())

    # Rerun fails with a dirty repo.
    dirt = opj(path, "dirt")
    with open(dirt, "w") as fh:
        fh.write("")
    assert_status('impossible', ds.rerun(on_failure="ignore"))
    remove(dirt)
    ok_clean_git(ds.path)

    # Make a non-run commit.
    with open(opj(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.add("nonrun-file")
    # Now rerun the buried command.
    ds.rerun(revision="HEAD~", message="rerun buried")
    eq_('xxx\n', open(probe_path).read())
    # Also check that the messasge override worked.
    eq_(ds.repo.format_commit("%B").splitlines()[0],
        "[DATALAD RUNCMD] rerun buried")
    # Or a range of commits, skipping non-run commits.
    ds.rerun(since="HEAD~3")
    eq_('xxxxx\n', open(probe_path).read())
    # Or --since= to run all reachable commits.
    ds.rerun(since="")
    eq_('xxxxxxxxxx\n', open(probe_path).read())

    # We can get back a report of what would happen rather than actually
    # rerunning anything.
    report = ds.rerun(since="", report=True, return_type="list")
    # Nothing changed.
    eq_('xxxxxxxxxx\n', open(probe_path).read())
    assert_result_count(report, 1, rerun_action="skip")
    report[-1]["commit"] == ds.repo.get_hexsha()

    # If a file is dropped, we remove it instead of unlocking it.
    ds.drop(probe_path, check=False)
    with swallow_outputs():
        ds.rerun()

    eq_('x\n', open(probe_path).read())
    # If the history to rerun has a merge commit, we abort.
    ds.repo.checkout("HEAD~3", options=["-b", "topic"])
    with open(opj(path, "topic-file"), "w") as f:
        f.write("topic")
    ds.add("topic-file")
    ds.repo.checkout("master")
    ds.repo.merge("topic")
    ok_clean_git(ds.path)
    assert_raises(IncompleteResultsError, ds.rerun)


@with_tempfile(mkdir=True)
def test_rerun_empty_branch(path):
    GitRepo(path, create=True)
    ds = Dataset(path)
    assert_status("impossible", ds.rerun(on_failure="ignore"))


@known_failure_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_rerun_onto(path):
    ds = Dataset(path).create()

    grow_file = opj(path, "grows")

    # Make sure we can handle range-specifications that yield no results.
    for since in ["", "HEAD"]:
        assert_result_count(
            ds.rerun("HEAD", onto="", since=since, on_failure="ignore"),
            1, status="impossible", action="run")

    ds.run('echo static-content > static')
    ds.repo.tag("static")
    with swallow_outputs():
        ds.run('echo x$(cat grows) > grows')
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
    ds.repo.checkout("master")
    with swallow_outputs():
        ds.rerun(revision="static", onto="static^")
    ok_(ds.repo.get_active_branch() is None)
    neq_(ds.repo.get_hexsha(),
         ds.repo.get_hexsha("static"))
    assert_result_count(ds.diff(revision="HEAD..static"), 0)
    for revrange in ["..static", "static.."]:
        assert_result_count(
            ds.repo.repo.git.rev_list(revrange).split(), 1)

    # Unlike the static change, if we run the ever-growing change on
    # top of itself, we end up with a new commit.
    ds.repo.checkout("master")
    ds.rerun(onto="HEAD")
    ok_(ds.repo.get_active_branch() is None)
    neq_(ds.repo.get_hexsha(),
         ds.repo.get_hexsha("master"))

    # An empty `onto` means use the parent of the first revision.
    ds.repo.checkout("master")
    with swallow_outputs():
        ds.rerun(since="static^", onto="")
    ok_(ds.repo.get_active_branch() is None)
    for revrange in ["..master", "master.."]:
        assert_result_count(
            ds.repo.repo.git.rev_list(revrange).split(), 3)

    # An empty `onto` means use the parent of the first revision that
    # has a run command.
    ds.repo.checkout("master")
    with swallow_outputs():
        ds.rerun(since="", onto="", branch="from-base")
    eq_(ds.repo.get_active_branch(), "from-base")
    assert_result_count(ds.diff(revision="master..from-base"), 0)
    eq_(ds.repo.get_merge_base(["static", "from-base"]),
        ds.repo.get_hexsha("static^"))

    # We abort when an explicitly specified `onto` doesn't exist.
    ds.repo.checkout("master")
    assert_result_count(
        ds.rerun(since="", onto="doesnotexist", branch="from-base",
                 on_failure="ignore"),
        1, status="error", action="run")


@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_chain(path):
    ds = Dataset(path).create()
    commits = []

    grow_file = opj(path, "grows")
    with swallow_outputs():
        ds.run('echo x$(cat grows) > grows')
    ds.repo.tag("first-run")

    for _ in range(3):
        commits.append(ds.repo.get_hexsha())
        ds.rerun()
        _, info = get_run_info(ds, ds.repo.format_commit("%B"))
        assert info["chain"] == commits

    ds.rerun(revision="first-run")
    _, info = get_run_info(ds, ds.repo.format_commit("%B"))
    assert info["chain"] == commits[:1]


@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_old_flag_compatibility(path):
    ds = Dataset(path).create()
    with swallow_outputs():
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


@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_just_one_commit(path):
    ds = Dataset(path).create()

    # Check out an orphan branch so that we can test the "one commit
    # in a repo" case.
    ds.repo.checkout("orph", options=["--orphan"])
    ds.repo.repo.git.reset("--hard")
    ds.repo.config.reload()

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

    # --script propagates the error.
    with swallow_outputs():
        assert_raises(IncompleteResultsError,
                      ds.rerun, since="", onto="", script="-")
    # --dry-run propagates the error.
    assert_raises(IncompleteResultsError,
                  ds.rerun, since="", onto="",
                  report=True, return_type="list")


@known_failure_windows
@known_failure_direct_mode
@with_tempfile(mkdir=True)
def test_run_failure(path):
    ds = Dataset(path).create()
    subds = ds.create("sub")

    hexsha_initial = ds.repo.get_hexsha()

    with swallow_outputs():
        with assert_raises(CommandError):
            ds.run("echo x$(cat sub/grows) > sub/grows && false")
    eq_(hexsha_initial, ds.repo.get_hexsha())
    ok_(ds.repo.dirty)

    msgfile = opj(path, ds.repo.get_git_dir(ds.repo), "COMMIT_EDITMSG")
    ok_exists(msgfile)

    ds.add(".", recursive=True, message_file=msgfile)
    ok_clean_git(ds.path)
    neq_(hexsha_initial, ds.repo.get_hexsha())

    outfile = opj(subds.path, "grows")
    eq_('x\n', open(outfile).read())

    # There is no CommandError on rerun if the non-zero error matches the
    # original code.
    ds.rerun()
    eq_('xx\n', open(outfile).read())

    # On the other hand, we fail if we rerun a command and there is a non-zero
    # error that doesn't match.
    ds.run("[ ! -e bar ] && echo c >bar")
    ok_clean_git(ds.path)
    with assert_raises(CommandError):
        ds.rerun()

    # We don't show instructions if the caller specified us not to save.
    remove(msgfile)
    with assert_raises(CommandError):
        ds.run("false", explicit=True, outputs=None)
    assert_false(op.exists(msgfile))


@known_failure_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_rerun_branch(path):
    ds = Dataset(path).create()

    ds.repo.tag("prerun")

    outfile = opj(path, "run-file")

    with swallow_outputs():
        ds.run('echo x$(cat run-file) > run-file')
    ds.rerun()
    eq_('xx\n', open(outfile).read())

    with open(opj(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.add("nonrun-file")

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
    for revrange in ["rerun..master", "master..rerun"]:
        assert_result_count(
            ds.repo.repo.git.rev_list(revrange).split(), 3)
    eq_(ds.repo.get_merge_base(["master", "rerun"]),
        ds.repo.get_hexsha("prerun"))

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


@known_failure_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_rerun_cherry_pick(path):
    ds = Dataset(path).create()

    ds.repo.tag("prerun")
    ds.run('echo abc > runfile')
    with open(opj(path, "nonrun-file"), "w") as f:
        f.write("foo")
    ds.add("nonrun-file")

    for onto, action in [("HEAD", "skip"), ("prerun", "pick")]:
        results = ds.rerun(since="prerun", onto=onto)
        assert_in_results(results, status='ok', rerun_action=action)


@known_failure_windows
@with_tempfile(mkdir=True)
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
    with swallow_outputs():
        assert_raises(CommandError, ds.rerun, revision="HEAD~")


@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_ambiguous_revision_file(path):
    ds = Dataset(path).create()
    ds.run('echo ambig > ambig')
    ds.repo.tag("ambig")
    # Don't fail when "ambig" refers to both a file and revision.
    ds.rerun(since="", revision="ambig", branch="rerun")
    eq_(len(ds.repo.repo.git.rev_list("rerun").split()),
        len(ds.repo.repo.git.rev_list("ambig", "--").split()))


@with_tree(tree={"subdir": {}})
def test_rerun_subdir(path):
    # Note: Using with_tree rather than with_tempfile is matters. The latter
    # calls realpath on the path, which masks a failure in the
    # TMPDIR="/var/tmp/sym link" test case
    ds = Dataset(path).create(force=True)
    subdir = opj(path, 'subdir')
    with chpwd(subdir):
        run("touch test.dat")
    ok_clean_git(ds.path)

    # FIXME: A plain ok_file_under_git call doesn't properly resolve the file
    # in the TMPDIR="/var/tmp/sym link" test case. Temporarily call realpath.
    def ok_file_under_git_kludge(path, basename):
        ok_file_under_git(opj(op.realpath(path), basename), annexed=True)

    ok_file_under_git_kludge(subdir, "test.dat")

    rec_msg, runinfo = get_run_info(ds, ds.repo.format_commit("%B"))
    eq_(runinfo['pwd'], 'subdir')
    # now, rerun within root of the dataset
    with chpwd(ds.path):
        ds.rerun()
    ok_clean_git(ds.path)
    ok_file_under_git_kludge(subdir, "test.dat")
    # and not on top
    assert_raises(AssertionError, ok_file_under_git, opj(ds.path, "test.dat"), annexed=True)

    # but if we run ds.run -- runs within top of the dataset
    with chpwd(subdir):
        ds.run("touch test2.dat")
    ok_clean_git(ds.path)
    ok_file_under_git_kludge(ds.path, "test2.dat")
    rec_msg, runinfo = get_run_info(ds, ds.repo.format_commit("%B"))
    eq_(runinfo['pwd'], '.')
    # now, rerun within subdir -- smoke for now
    with chpwd(subdir):
        ds.rerun()


@with_tree(tree={"d": {"to_modify": "content1"},
                 "to_remove": "content2",
                 "to_modify": "content3",
                 "unchanged": "content4"})
def test_new_or_modified(path):
    def get_new_or_modified(*args, **kwargs):
        return [relpath(ap["path"], path)
                for ap in new_or_modified(diff_revision(*args, **kwargs))]

    ds = Dataset(path).create(force=True, no_annex=True)

    # Check out an orphan branch so that we can test the "one commit
    # in a repo" case.
    ds.repo.checkout("orph", options=["--orphan"])
    ds.add(".")
    assert_false(ds.repo.dirty)
    assert_result_count(ds.repo.repo.git.rev_list("HEAD").split(), 1)
    # Diffing doesn't fail when the branch contains a single commit.
    assert_in("to_modify", get_new_or_modified(ds, "HEAD"))

    # New files are detected, deletions are not.
    ds.repo.remove(["to_remove"])
    ok_(ds.repo.dirty)

    with open(opj(path, "to_add"), "w") as f:
        f.write("content5")
    ds.repo.add(["to_add"])
    ds.repo.commit("add one, remove another")

    eq_(get_new_or_modified(ds, "HEAD"),
        ["to_add"])

    # Modifications are detected.
    with open(opj(path, "to_modify"), "w") as f:
        f.write("updated 1")
    with open(opj(path, "d/to_modify"), "w") as f:
        f.write("updated 2")
    ds.add(["to_modify", "d/to_modify"])

    eq_(set(get_new_or_modified(ds, "HEAD")),
        {"to_modify", "d/to_modify"})

    # Non-HEAD revisions work.
    ds.repo.commit("empty", options=["--allow-empty"])
    assert_false(get_new_or_modified(ds, "HEAD"))
    eq_(set(get_new_or_modified(ds, "HEAD~")),
        {"to_modify", "d/to_modify"})


@known_failure_windows
@with_tempfile(mkdir=True)
def test_rerun_script(path):
    ds = Dataset(path).create()
    ds.run("echo a >foo")
    ds.run(["touch", "bar"], message='BAR', sidecar=True)
    # a run record sidecar file was added with the last commit
    assert(any(d['path'].startswith(opj(ds.path, '.datalad', 'runinfo'))
               for d in ds.rerun(report=True, return_type='item-or-list')['diff']))
    bar_hexsha = ds.repo.get_hexsha()

    script_file = opj(path, "commands.sh")

    ds.rerun(script=script_file)
    ok_exists(script_file)
    with open(script_file) as sf:
        lines = sf.readlines()
        assert_in("touch bar\n", lines)
        # The commit message is there too.
        assert_in("# BAR\n", lines)
        assert_in("# (record: {})\n".format(bar_hexsha), lines)
        assert_not_in("echo a >foo\n", lines)

    ds.rerun(since="", script=script_file)
    with open(script_file) as sf:
        lines = sf.readlines()
        assert_in("touch bar\n", lines)
        # Automatic commit messages aren't included.
        assert_not_in("# echo a >foo\n", lines)
        assert_in("echo a >foo\n", lines)

    # --script=- writes to stdout.
    with patch("sys.stdout", new_callable=StringIO) as cmout:
        ds.rerun(script="-")
        assert_in("touch bar",
                  cmout.getvalue().splitlines())


@slow  # ~10s
@known_failure_windows
@with_tree(tree={"input.dat": "input",
                 "extra-input.dat": "extra input",
                 "s0": {"s1_0": {"s2": {"a.dat": "a",
                                        "b.txt": "b"}},
                        "s1_1": {"s2": {"c.dat": "c",
                                        "d.txt": "d"}},
                        "ss": {"e.dat": "e"}}})
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_run_inputs_outputs(src, path):
    for subds in [("s0", "s1_0", "s2"),
                  ("s0", "s1_1", "s2"),
                  ("s0", "s1_0"),
                  ("s0", "s1_1"),
                  ("s0", "ss"),
                  ("s0",)]:
        Dataset(op.join(*((src,) + subds))).create(force=True)
    src_ds = Dataset(src).create(force=True)
    src_ds.add(".", recursive=True)

    ds = install(path, source=src,
                 result_xfm='datasets', return_type='item-or-list')
    assert_false(ds.repo.file_has_content("input.dat"))
    assert_false(ds.repo.file_has_content("extra-input.dat"))

    # The specified inputs and extra inputs will be retrieved before the run.
    # (Use run_command() to access the extra_inputs argument.)
    list(run_command("cat {inputs} {inputs} >doubled.dat",
                     dataset=ds,
                     inputs=["input.dat"], extra_inputs=["extra-input.dat"]))

    ok_clean_git(ds.path)
    ok_(ds.repo.file_has_content("input.dat"))
    ok_(ds.repo.file_has_content("extra-input.dat"))
    ok_(ds.repo.file_has_content("doubled.dat"))
    with open(opj(path, "doubled.dat")) as fh:
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

    with swallow_logs(new_level=logging.WARN) as cml:
        ds.run("touch dummy", inputs=["not-there"])
        assert_in("Input does not exist: ", cml.out)

    # Test different combinations of globs and explicit files.
    inputs = ["a.dat", "b.dat", "c.txt", "d.txt"]
    create_tree(ds.path, {i: i for i in inputs})

    ds.add(".")
    ds.repo.copy_to(inputs, remote="origin")
    ds.repo.drop(inputs, options=["--force"])

    test_cases = [(["*.dat"], ["a.dat", "b.dat"]),
                  (["*.dat", "c.txt"], ["a.dat", "b.dat", "c.txt"]),
                  (["*"], inputs)]

    for idx, (inputs_arg, expected_present) in enumerate(test_cases):
        assert_false(any(ds.repo.file_has_content(i) for i in inputs))

        ds.run("touch dummy{}".format(idx), inputs=inputs_arg)
        ok_(all(ds.repo.file_has_content(f) for f in expected_present))
        # Globs are stored unexpanded by default.
        assert_in(inputs_arg[0], ds.repo.format_commit("%B"))
        ds.repo.drop(inputs, options=["--force"])

    # --input can be passed a subdirectory.
    create_tree(ds.path, {"subdir": {"a": "subdir a",
                                     "b": "subdir b"}})
    ds.add("subdir")
    ds.repo.copy_to(["subdir/a", "subdir/b"], remote="origin")
    ds.repo.drop("subdir", options=["--force"])
    ds.run("touch subdir-dummy", inputs=[opj(ds.path, "subdir")])
    ok_(all(ds.repo.file_has_content(opj("subdir", f)) for f in ["a", "b"]))

    # Inputs are specified relative to a dataset's subdirectory.
    ds.repo.drop(opj("subdir", "a"), options=["--force"])
    with chpwd(opj(path, "subdir")):
        run("touch subdir-dummy1", inputs=["a"])
    ok_(ds.repo.file_has_content(opj("subdir", "a")))

    # --input=. runs "datalad get ."
    ds.run("touch dot-dummy", inputs=["."])
    eq_(ds.repo.get_annexed_files(),
        ds.repo.get_annexed_files(with_content_only=True))
    # On rerun, we get all files, even those that weren't in the tree at the
    # time of the run.
    create_tree(ds.path, {"after-dot-run": "after-dot-run content"})
    ds.add(".")
    ds.repo.copy_to(["after-dot-run"], remote="origin")
    ds.repo.drop(["after-dot-run"], options=["--force"])
    ds.rerun("HEAD^")
    ds.repo.file_has_content("after-dot-run")

    # --output will unlock files that are present.
    ds.repo.get("a.dat")
    ds.run("echo ' appended' >>a.dat", outputs=["a.dat"])
    with open(opj(path, "a.dat")) as fh:
        eq_(fh.read(), "a.dat appended\n")

    # --output will remove files that are not present.
    ds.repo.drop(["a.dat", "d.txt"], options=["--force"])
    ds.run("echo ' appended' >>a.dat", outputs=["a.dat"])
    with open(opj(path, "a.dat")) as fh:
        eq_(fh.read(), " appended\n")

    # --input can be combined with --output.
    ds.repo.repo.git.reset("--hard", "HEAD~2")
    ds.run("echo ' appended' >>a.dat", inputs=["a.dat"], outputs=["a.dat"])
    with open(opj(path, "a.dat")) as fh:
        eq_(fh.read(), "a.dat appended\n")

    with swallow_logs(new_level=logging.DEBUG) as cml:
        with swallow_outputs():
            ds.run("echo blah", outputs=["not-there"])
        assert_in("Filtered out non-existing path: ", cml.out)

    ds.create('sub')
    ds.run("echo sub_orig >sub/subfile")
    ds.run("echo sub_overwrite >sub/subfile", outputs=["sub/subfile"])
    ds.drop("sub/subfile", check=False)
    ds.run("echo sub_overwrite >sub/subfile", outputs=["sub/subfile"])

    # --input/--output globs can be stored in expanded form.
    ds.run("touch expand-dummy", inputs=["a.*"], outputs=["b.*"], expand="both")
    assert_in("a.dat", ds.repo.format_commit("%B"))
    assert_in("b.dat", ds.repo.format_commit("%B"))

    res = ds.rerun(report=True, return_type='item-or-list')
    eq_(res["run_info"]['inputs'], ["a.dat"])
    eq_(res["run_info"]['outputs'], ["b.dat"])

    # We install subdatasets to fully resolve globs.
    ds.uninstall("s0")
    assert_false(Dataset(op.join(path, "s0")).is_installed())
    ds.run("echo {inputs} >globbed-subds", inputs=["s0/s1_*/s2/*.dat"])
    ok_file_has_content(op.join(ds.path, "globbed-subds"),
                        "s0/s1_0/s2/a.dat s0/s1_1/s2/c.dat",
                        strip=True)

    ds_ss = Dataset(op.join(path, "s0", "ss"))
    assert_false(ds_ss.is_installed())
    ds.run("echo blah >{outputs}", outputs=["s0/ss/out"])
    ok_(ds_ss.is_installed())
    ok_file_has_content(op.join(ds.path, "s0", "ss", "out"),
                        "blah",
                        strip=True)


@known_failure_windows
@with_tempfile(mkdir=True)
def test_run_inputs_no_annex_repo(path):
    ds = Dataset(path).create(no_annex=True)
    # Running --input in a plain Git repo doesn't fail.
    ds.run("touch dummy", inputs=["*"])
    ok_exists(opj(ds.path, "dummy"))
    ds.rerun()


@slow  # ~10s
@known_failure_windows
@with_testrepos('basic_annex', flavors=['clone'])
def test_run_explicit(path):
    ds = Dataset(path)

    assert_false(ds.repo.file_has_content("test-annex.dat"))

    create_tree(ds.path, {"dirt_untracked": "untracked",
                          "dirt_modified": "modified"})
    ds.add("dirt_modified", to_git=True)
    with open(opj(path, "dirt_modified"), "a") as ofh:
        ofh.write(", more")

    # We need explicit=True to run with dirty repo.
    assert_status("impossible",
                  ds.run("cat test-annex.dat test-annex.dat >doubled.dat",
                         inputs=["test-annex.dat"],
                         on_failure="ignore"))

    hexsha_initial = ds.repo.get_hexsha()
    # If we specify test-annex.dat as an input, it will be retrieved before the
    # run.
    ds.run("cat test-annex.dat test-annex.dat >doubled.dat",
           inputs=["test-annex.dat"], explicit=True)
    ok_(ds.repo.file_has_content("test-annex.dat"))
    # We didn't commit anything because outputs weren't specified.
    assert_false(ds.repo.file_has_content("doubled.dat"))
    eq_(hexsha_initial, ds.repo.get_hexsha())

    # If an input doesn't exist, we just show the standard warning.
    with swallow_logs(new_level=logging.WARN) as cml:
        with swallow_outputs():
            ds.run("ls", inputs=["not-there"], explicit=True)
        assert_in("Input does not exist: ", cml.out)

    remove(opj(path, "doubled.dat"))

    hexsha_initial = ds.repo.get_hexsha()
    ds.run("cat test-annex.dat test-annex.dat >doubled.dat",
           inputs=["test-annex.dat"], outputs=["doubled.dat"],
           explicit=True)
    ok_(ds.repo.file_has_content("doubled.dat"))
    ok_(ds.repo.is_dirty(path="dirt_modified"))
    neq_(hexsha_initial, ds.repo.get_hexsha())

    # Saving explicit outputs works from subdirectories.
    subdir = opj(path, "subdir")
    mkdir(subdir)
    with chpwd(subdir):
        run("echo insubdir >foo", explicit=True, outputs=["foo"])
    ok_(ds.repo.file_has_content(opj("subdir", "foo")))


@known_failure_direct_mode
@known_failure_windows
@with_tree(tree={"to_modify": "to_modify"})
def test_rerun_explicit(path):
    ds = Dataset(path).create(force=True)

    ds.run("echo o >> foo", explicit=True, outputs=["foo"])
    with open(op.join(ds.path, "foo")) as ifh:
        orig_content = ifh.read()
        orig_head = ds.repo.get_hexsha()

    # Explicit rerun is allowed in a dirty tree.
    ok_(ds.repo.dirty)
    ds.rerun(explicit=True)
    eq_(orig_head, ds.repo.get_hexsha("master~1"))
    with open(op.join(ds.path, "foo")) as ifh:
        eq_(orig_content * 2, ifh.read())

    # --since also works.
    ds.rerun(since="", explicit=True)
    eq_(orig_head,
        # Added two rerun commits.
        ds.repo.get_hexsha("master~3"))

    # With just untracked changes, we can rerun with --onto.
    ds.rerun(since="", onto="", explicit=True)
    eq_(ds.repo.get_hexsha(orig_head + "^"),
        # Reran the four run commits from above on the initial base.
        ds.repo.get_hexsha("HEAD~4"))

    # But checking out a new HEAD can fail when there are modifications.
    ds.repo.checkout("master")
    ok_(ds.repo.dirty)
    ds.repo.add(["to_modify"], git=True)
    ds.save()
    assert_false(ds.repo.dirty)
    with open(op.join(ds.path, "to_modify"), "a") as ofh:
        ofh.write("more")
    ok_(ds.repo.dirty)

    with assert_raises(CommandError):
        ds.rerun(onto="", since="", explicit=True)


@known_failure_windows
@with_tree(tree={"a.in": "a", "b.in": "b", "c.out": "c",
                 "subdir": {}})
def test_placeholders(path):
    ds = Dataset(path).create(force=True)
    ds.add(".")
    ds.run("echo {inputs} >{outputs}", inputs=[".", "*.in"], outputs=["c.out"])
    ok_file_has_content(opj(path, "c.out"), "a.in b.in\n")

    hexsha_before = ds.repo.get_hexsha()
    ds.rerun()
    eq_(hexsha_before, ds.repo.get_hexsha())

    ds.run("echo {inputs[0]} >getitem", inputs=["*.in"])
    ok_file_has_content(opj(path, "getitem"), "a.in\n")

    ds.run("echo {pwd} >expanded-pwd")
    ok_file_has_content(opj(path, "expanded-pwd"), path,
                        strip=True)

    ds.run("echo {dspath} >expanded-dspath")
    ok_file_has_content(opj(path, "expanded-dspath"), ds.path,
                        strip=True)

    subdir_path = opj(path, "subdir")
    with chpwd(subdir_path):
        run("echo {pwd} >expanded-pwd")
    ok_file_has_content(opj(path, "subdir", "expanded-pwd"), subdir_path,
                        strip=True)
    eq_(get_run_info(ds, ds.repo.format_commit("%B"))[1]["pwd"],
        "subdir")

    # Double brackets can be used to escape placeholders.
    ds.run("touch {{inputs}}", inputs=["*.in"])
    ok_exists(opj(path, "{inputs}"))

    # rerun --script expands the placeholders.
    with patch("sys.stdout", new_callable=StringIO) as cmout:
        ds.rerun(script="-", since="")
        script_out = cmout.getvalue()
        assert_in("echo a.in b.in >c.out", script_out)
        assert_in("echo {} >expanded-pwd".format(subdir_path),
                  script_out)
        assert_in("echo {} >expanded-dspath".format(ds.path),
                  script_out)

    assert_result_count(
        ds.run("{unknown_placeholder}", on_failure="ignore"),
        1, status="impossible", action="run")

    # Configured placeholders.
    ds.config.add("datalad.run.substitutions.license", "gpl3", where="local")
    ds.run("echo {license} >configured-license")
    ok_file_has_content(opj(path, "configured-license"), "gpl3", strip=True)
    # --script handles configured placeholders.
    with patch("sys.stdout", new_callable=StringIO) as cmout:
        ds.rerun(script="-")
        assert_in("gpl3", cmout.getvalue())

    ds.run("echo {tmpdir} >tout")
    ok_file_has_content(op.join(path, "tout"), ".*datalad-run.*", re_=True)


@known_failure_windows
@with_tree(tree={OBSCURE_FILENAME + u".t": "obscure",
                 "bar.txt": "b",
                 "foo blah.txt": "f"})
def test_inputs_quotes_needed(path):
    ds = Dataset(path).create(force=True)
    ds.add(".")
    cmd = "import sys; open(sys.argv[-1], 'w').write('!'.join(sys.argv[1:]))"
    # The string form of a command works fine when the inputs/outputs have
    # spaces ...
    cmd_str = "{} -c \"{}\" {{inputs}} {{outputs[0]}}".format(
        sys.executable, cmd)
    ds.run(cmd_str, inputs=["*.t*"], outputs=["out0"], expand="inputs")
    expected = u"!".join(
        list(sorted([OBSCURE_FILENAME + u".t", "bar.txt", "foo blah.txt"])) +
        ["out0"])
    with open(op.join(path, "out0")) as ifh:
        eq_(assure_unicode(ifh.read()), expected)
    # ... but the list form of a command does not. (Don't test this failure
    # with the obscure file name because we'd need to know its composition to
    # predict the failure.)
    cmd_list = [sys.executable, "-c", cmd, "{inputs}", "{outputs[0]}"]
    ds.run(cmd_list, inputs=["*.txt"], outputs=["out0"])
    ok_file_has_content(opj(path, "out0"), "bar.txt foo!blah.txt!out0")


@known_failure_windows
@with_tree(tree={"foo": "f", "bar": "b"})
def test_inject(path):
    ds = Dataset(path).create(force=True)
    ok_(ds.repo.is_dirty())
    list(run_command("nonsense command",
                     dataset=ds,
                     inject=True,
                     extra_info={"custom_key": "custom_field"}))
    msg = ds.repo.format_commit("%B")
    assert_in("custom_key", msg)
    assert_in("nonsense command", msg)


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


@with_tempfile(mkdir=True)
def test_format_command_strip_leading_dashes(path):
    ds = Dataset(path).create()
    eq_(format_command(ds, ["--", "cmd", "--opt"]), "cmd --opt")
    eq_(format_command(ds, ["--"]), "")
    # Can repeat to escape.
    eq_(format_command(ds, ["--", "--", "ok"]), "-- ok")
    # String stays as is.
    eq_(format_command(ds, "--"), "--")


@with_tempfile(mkdir=True)
def test_run_cmdline_disambiguation(path):
    Dataset(path).create()
    with chpwd(path):
        # Without a positional argument starting a command, any option is
        # treated as an option to 'datalad run'.
        with swallow_outputs() as cmo:
            with patch("datalad.interface.run._execute_command") as exec_cmd:
                with assert_raises(SystemExit):
                    main(["datalad", "run", "--message"])
                exec_cmd.assert_not_called()
            assert_in("message: expected one", cmo.err)
        # If we want to pass an option as the first value of a command (e.g.,
        # because we are using a runscript with containers-run), we can do this
        # with "--".
        with patch("datalad.interface.run._execute_command") as exec_cmd:
            with assert_raises(SystemExit):
                main(["datalad", "run", "--", "--message"])
            exec_cmd.assert_called_once_with(
                "--message", path, expected_exit=None)

        # And a twist on above: Our parser mishandles --version (gh-3067),
        # treating 'datalad run CMD --version' as 'datalad --version'.
        version_stream = "err" if PY2 else "out"
        with swallow_outputs() as cmo:
            with assert_raises(SystemExit) as cm:
                main(["datalad", "run", "echo", "--version"])
            eq_(cm.exception.code, 0)
            out = getattr(cmo, version_stream)
        with swallow_outputs() as cmo:
            with assert_raises(SystemExit):
                main(["datalad", "--version"])
            version_out = getattr(cmo, version_stream)
        ok_(version_out)
        eq_(version_out, out)
        # We can work around that (i.e., make "--version" get passed as
        # command) with "--".
        with patch("datalad.interface.run._execute_command") as exec_cmd:
            with assert_raises(SystemExit):
                main(["datalad", "run", "--", "echo", "--version"])
            exec_cmd.assert_called_once_with(
                "echo --version", path, expected_exit=None)
