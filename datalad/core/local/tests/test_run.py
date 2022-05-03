# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Partial testing of `run` commands.

Note: Tests of `run` that involve `rerun` are in interface.tests.test_run.
"""

__docformat__ = 'restructuredtext'

import logging
import os
import os.path as op
import sys
from os import (
    mkdir,
    remove,
)
from unittest.mock import patch

from datalad.api import (
    clone,
    run,
)
from datalad.cli.main import main
from datalad.core.local.run import (
    _format_iospecs,
    _get_substitutions,
    format_command,
    run_command,
)
from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import (
    CommandError,
    IncompleteResultsError,
    NoDatasetFound,
)
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    OBSCURE_FILENAME,
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
    patch_config,
    swallow_logs,
    swallow_outputs,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    chpwd,
    ensure_unicode,
    on_windows,
)

cat_command = 'cat' if not on_windows else 'type'


@with_tempfile(mkdir=True)
def test_invalid_call(path=None):
    with chpwd(path):
        # no dataset, no luck
        assert_raises(NoDatasetFound, run, 'doesntmatter')
        # dirty dataset
        ds = Dataset(path).create()
        create_tree(ds.path, {'this': 'dirty'})
        assert_status('impossible', run('doesntmatter', on_failure='ignore'))


def last_commit_msg(repo):
    # ATTN: Pass branch explicitly so that this check works when we're on an
    # adjusted branch too (e.g., when this test is executed under Windows).
    return repo.format_commit("%B", DEFAULT_BRANCH)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_basics(path=None, nodspath=None):
    ds = Dataset(path).create()
    last_state = ds.repo.get_hexsha()
    # run inside the dataset
    with chpwd(path), \
            swallow_outputs():
        # provoke command failure
        res = ds.run('7i3amhmuch9invalid', on_failure="ignore",
                     result_renderer=None)
        assert_result_count(res, 1, action="run", status="error")
        run_res = [r for r in res if r["action"] == "run"][0]
        # let's not speculate that the exit code is always 127
        ok_(run_res["run_info"]["exit"] > 0)
        eq_(last_state, ds.repo.get_hexsha())
        # now one that must work
        res = ds.run('cd .> empty', message='TEST')
        assert_repo_status(ds.path)
        assert_result_count(res, 3)
        # TODO 'state' is still untracked!!!
        assert_result_count(res, 1, action='add',
                            path=op.join(ds.path, 'empty'), type='file')
        assert_result_count(res, 1, action='save', path=ds.path)
        commit_msg = last_commit_msg(ds.repo)
        ok_(commit_msg.startswith('[DATALAD RUNCMD] TEST'))
        # crude test that we have a record for the PWD
        assert_in('"pwd": "."', commit_msg)
        last_state = ds.repo.get_hexsha()
        # now run a command that will not alter the dataset
        noop_cmd = ':'
        res = ds.run(noop_cmd, message='NOOP_TEST')
        assert_result_count(res, 1, action='save', status='notneeded')
        eq_(last_state, ds.repo.get_hexsha())
        # We can also run the command via a single-item list because this is
        # what the CLI interface passes in for quoted commands.
        res = ds.run([noop_cmd], message='NOOP_TEST')
        assert_result_count(res, 1, action='save', status='notneeded')

    # run outside the dataset, should still work but with limitations
    with chpwd(nodspath), \
            swallow_outputs():
        res = ds.run('cd . > empty2', message='TEST')
        assert_result_count(res, 1, action='add',
                            path=op.join(ds.path, 'empty2'),
                            type='file', status='ok')
        assert_result_count(res, 1, action='save', status='ok')

    # running without a command is a noop
    with chpwd(path):
        with swallow_logs(new_level=logging.WARN) as cml:
            ds.run()
            assert_in("No command given", cml.out)

    # running without a command is a noop
    with chpwd(path):
        with swallow_logs(new_level=logging.INFO) as cml:
            assert_raises(
                IncompleteResultsError,
                ds.run,
                '7i3amhmuch9invalid',
                # this is on_failure=stop by default
            )
            # must give recovery hint in Python notation
            assert_in("can save the changes with \"Dataset(", cml.out)

    with chpwd(path):
        # make sure that an invalid input declaration prevents command
        # execution by default
        assert_raises(
            IncompleteResultsError,
            ds.run, 'cd .> dummy0', inputs=['not-here'])
        ok_(not (ds.pathobj / 'dummy0').exists())
        # but the default behavior can be changed
        assert_raises(
            IncompleteResultsError,
            ds.run, 'cd .> dummy0', inputs=['not-here'],
            on_failure='continue')
        # it has stilled failed, but the command got executed nevertheless
        ok_((ds.pathobj / 'dummy0').exists())


@known_failure_windows
# ^ For an unknown reason, appveyor started failing after we removed
#   receive.autogc=0 and gc.auto=0 from our common git options (gh-3482).
# moreover the usage of unicode in the file names also breaks this on windows
@with_tempfile(mkdir=True)
def test_py2_unicode_command(path=None):
    # Avoid OBSCURE_FILENAME to avoid windows-breakage (gh-2929).
    ds = Dataset(path).create()
    touch_cmd = "import sys; open(sys.argv[1], 'w').write('')"
    cmd_str = u"{} -c \"{}\" {}".format(sys.executable,
                                        touch_cmd,
                                        u"bβ0.dat")
    ds.run(cmd_str)
    assert_repo_status(ds.path)
    ok_exists(op.join(path, u"bβ0.dat"))

    # somewhat desperate attempt to detect our own Github CI tests on a
    # crippled filesystem (VFAT) that is so crippled that it doesn't handle
    # what is needed here. It just goes mad with encoded bytestrings:
    # CommandError: ''python -c '"'"'import sys; open(sys.argv[1], '"'"'"'"'"'"'"'"'w'"'"'"'"'"'"'"'"').write('"'"'"'"'"'"'"'"''"'"'"'"'"'"'"'"')'"'"' '"'"' β1 '"'"''' failed with exitcode 1 under /crippledfs/
    if not on_windows and os.environ.get('TMPDIR', None) != '/crippledfs':  # FIXME
        ds.run([sys.executable, "-c", touch_cmd, u"bβ1.dat"])
        assert_repo_status(ds.path)
        ok_exists(op.join(path, u"bβ1.dat"))

        # Send in a list of byte-strings to mimic a py2 command-line
        # invocation.
        ds.run([s.encode("utf-8")
                for s in [sys.executable, "-c", touch_cmd, u" β1 "]])
        assert_repo_status(ds.path)
        ok_exists(op.join(path, u" β1 "))

    assert_in_results(
        ds.run(u"bβ2.dat", result_renderer=None, on_failure="ignore"),
        status="error", action="run")


@with_tempfile(mkdir=True)
def test_sidecar(path=None):
    ds = Dataset(path).create()
    # Simple sidecar message checks.
    ds.run("cd .> dummy0", message="sidecar arg", sidecar=True)
    assert_not_in('"cmd":', ds.repo.format_commit("%B"))

    ds.config.set("datalad.run.record-sidecar", "false", scope="local")
    ds.run("cd .> dummy1", message="sidecar config")

    assert_in('"cmd":', last_commit_msg(ds.repo))

    ds.config.set("datalad.run.record-sidecar", "true", scope="local")
    ds.run("cd .> dummy2", message="sidecar config")
    assert_not_in('"cmd":', last_commit_msg(ds.repo))

    # Don't break when config.get() returns multiple values. Here it's two
    # values in .gitconfig, but a more realistic scenario is a value in
    # $repo/.git/config that overrides a setting in ~/.config/git/config.
    ds.config.add("datalad.run.record-sidecar", "false", scope="local")
    ds.run("cd .> dummy3", message="sidecar config")
    assert_in('"cmd":', last_commit_msg(ds.repo))


    # make sure sidecar file is committed when explicitly specifying outputs
    ds.run("cd .> dummy4",
           outputs=["dummy4"],
           sidecar=True,
           explicit=True,
           message="sidecar + specified outputs")
    assert_not_in('"cmd":', last_commit_msg(ds.repo))
    assert_repo_status(ds.path)




@with_tree(tree={"to_remove": "abc"})
def test_run_save_deletion(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    ds.run("{} to_remove".format("del" if on_windows else "rm"))
    assert_repo_status(ds.path)


@with_tempfile(mkdir=True)
def test_run_from_subds(path=None):
    subds = Dataset(path).create().create("sub")
    subds.run("cd .> foo")
    assert_repo_status(subds.path)


@with_tree(tree={"sub": {"input": ""}})
def test_run_from_subds_gh3551(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    ds.create("output")
    with chpwd(op.join(ds.path, "sub")):
        assert_in_results(
            run("echo",
                inputs=[op.join(op.pardir, "sub", "input")],
                outputs=[op.join(op.pardir, "output")],
                return_type="list", result_filter=None, result_xfm=None),
            action="get",
            status="notneeded")
    assert_repo_status(ds.path)

    subds_path = op.join("output", "subds")
    ds.create(subds_path)
    with chpwd(op.join(ds.path, "sub")):
        output_dir = op.join(op.pardir, "output", "subds")
        # The below command is trying to be compatible. It could be made better
        # (e.g., actually using the input file) by someone that knows something
        # about Windows.
        assert_in_results(
            run("cd .> {}".format(op.join(output_dir, "f")),
                inputs=[op.join(op.pardir, "sub", "input")],
                outputs=[output_dir],
                return_type="list", result_filter=None, result_xfm=None),
            action="save",
            status="ok")
    assert_repo_status(ds.path)
    subds = Dataset(op.join(ds.path, subds_path))
    ok_exists(op.join(subds.path, "f"))
    if not ds.repo.is_managed_branch():  # FIXME
        # This check fails on Windows:
        # https://github.com/datalad/datalad/pull/3747/checks?check_run_id=248506560#step:8:254
        ok_(subds.repo.file_has_content("f"))


@with_tempfile(mkdir=True)
def test_run_assume_ready(path=None):
    ds = Dataset(path).create()
    repo = ds.repo
    adjusted = repo.is_managed_branch()

    # --assume-ready=inputs

    (repo.pathobj / "f1").write_text("f1")
    ds.save()

    def cat_cmd(fname):
        return [sys.executable, "-c",
                "import sys; print(open(sys.argv[-1]).read())",
                fname]

    assert_in_results(
        ds.run(cat_cmd("f1"), inputs=["f1"]),
        action="get", type="file")
    # Same thing, but without the get() call.
    assert_not_in_results(
        ds.run(cat_cmd("f1"), inputs=["f1"], assume_ready="inputs"),
        action="get", type="file")

    ds.drop("f1", reckless='kill')
    if not adjusted:
        # If the input is not actually ready, the command will fail.
        assert_in_results(
            ds.run(cat_cmd("f1"), inputs=["f1"], assume_ready="inputs",
                   on_failure="ignore", result_renderer=None),
            action="run", status="error")

    # --assume-ready=outputs

    def unlink_and_write_cmd(fname):
        # This command doesn't care whether the output file is unlocked because
        # it removes it ahead of time anyway.
        return [sys.executable, "-c",
                "import sys; import os; import os.path as op; "
                "f = sys.argv[-1]; op.lexists(f) and os.unlink(f); "
                "open(f, mode='w').write(str(sys.argv))",
                fname]

    (repo.pathobj / "f2").write_text("f2")
    ds.save()

    res = ds.run(unlink_and_write_cmd("f2"), outputs=["f2"])
    if not adjusted:
        assert_in_results(res, action="unlock", type="file")
    # Same thing, but without the unlock() call.
    res = ds.run(unlink_and_write_cmd("f2"), outputs=["f2"],
                 assume_ready="outputs")
    assert_not_in_results(res, action="unlock", type="file")

    # --assume-ready=both

    res = ds.run(unlink_and_write_cmd("f2"),
                 outputs=["f2"], inputs=["f2"])
    assert_in_results(res, action="get", type="file")
    if not adjusted:
        assert_in_results(res, action="unlock", type="file")

    res = ds.run(unlink_and_write_cmd("f2"),
                 outputs=["f2"], inputs=["f2"],
                 assume_ready="both")
    assert_not_in_results(res, action="get", type="file")
    assert_not_in_results(res, action="unlock", type="file")


@with_tempfile()
@with_tempfile()
def test_run_explicit(origpath=None, path=None):
    origds = Dataset(origpath).create()
    (origds.pathobj / "test-annex.dat").write_text('content')
    origds.save()
    ds = clone(origpath, path)

    assert_false(ds.repo.file_has_content("test-annex.dat"))

    create_tree(ds.path, {"dirt_untracked": "untracked",
                          "dirt_modified": "modified"})
    ds.save("dirt_modified", to_git=True)
    with open(op.join(path, "dirt_modified"), "a") as ofh:
        ofh.write(", more")

    # We need explicit=True to run with dirty repo.
    assert_status(
        "impossible",
        ds.run(f"{cat_command} test-annex.dat test-annex.dat >doubled.dat",
               inputs=["test-annex.dat"],
               on_failure="ignore"))

    hexsha_initial = ds.repo.get_hexsha()
    # If we specify test-annex.dat as an input, it will be retrieved before the
    # run.
    ds.run(f"{cat_command} test-annex.dat test-annex.dat >doubled.dat",
           inputs=["test-annex.dat"], explicit=True,
           result_renderer='disabled')
    ok_(ds.repo.file_has_content("test-annex.dat"))
    # We didn't commit anything because outputs weren't specified.
    assert_false(ds.repo.file_has_content("doubled.dat"))
    eq_(hexsha_initial, ds.repo.get_hexsha())

    # If an input doesn't exist, we just show the standard warning.
    with assert_raises(IncompleteResultsError):
        ds.run("ls", inputs=["not-there"], explicit=True,
               on_failure="stop", result_renderer='disabled')

    remove(op.join(path, "doubled.dat"))

    hexsha_initial = ds.repo.get_hexsha()
    ds.run(f"{cat_command} test-annex.dat test-annex.dat >doubled.dat",
           inputs=["test-annex.dat"], outputs=["doubled.dat"],
           explicit=True, result_renderer='disabled')
    ok_(ds.repo.file_has_content("doubled.dat"))
    assert_repo_status(ds.path, modified=["dirt_modified"],
                       untracked=['dirt_untracked'])
    neq_(hexsha_initial, ds.repo.get_hexsha())

    # Saving explicit outputs works from subdirectories.
    subdir = op.join(path, "subdir")
    mkdir(subdir)
    with chpwd(subdir):
        run("echo insubdir >foo", explicit=True, outputs=["foo"],
            result_renderer='disabled')
    ok_(ds.repo.file_has_content(op.join("subdir", "foo")))


@with_tree(tree={OBSCURE_FILENAME + u".t": "obscure",
                 "bar.txt": "b",
                 "foo blah.txt": "f"})
def test_inputs_quotes_needed(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
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
        eq_(ensure_unicode(ifh.read()), expected)
    # ... but the list form of a command does not. (Don't test this failure
    # with the obscure file name because we'd need to know its composition to
    # predict the failure.)
    cmd_list = [sys.executable, "-c", cmd, "{inputs}", "{outputs[0]}"]
    ds.run(cmd_list, inputs=["*.txt"], outputs=["out0"])
    ok_file_has_content(op.join(path, "out0"), "bar.txt foo!blah.txt!out0")


@with_tree(tree={"foo": "f", "bar": "b"})
def test_inject(path=None):
    ds = Dataset(path).create(force=True)
    assert_repo_status(ds.path, untracked=['foo', 'bar'])
    list(run_command("nonsense command",
                     dataset=ds,
                     inject=True,
                     extra_info={"custom_key": "custom_field"}))
    msg = last_commit_msg(ds.repo)
    assert_in("custom_key", msg)
    assert_in("nonsense command", msg)


@with_tempfile(mkdir=True)
def test_format_command_strip_leading_dashes(path=None):
    ds = Dataset(path).create()
    eq_(format_command(ds, ["--", "cmd", "--opt"]),
        '"cmd" "--opt"' if on_windows else "cmd --opt")
    eq_(format_command(ds, ["--"]), "")
    # Can repeat to escape.
    eq_(format_command(ds, ["--", "--", "ok"]),
         '"--" "ok"' if on_windows else "-- ok")
    # String stays as is.
    eq_(format_command(ds, "--"), "--")


@with_tempfile(mkdir=True)
def test_run_cmdline_disambiguation(path=None):
    Dataset(path).create()
    with chpwd(path):
        # Without a positional argument starting a command, any option is
        # treated as an option to 'datalad run'.
        with swallow_outputs() as cmo:
            with patch("datalad.core.local.run._execute_command") as exec_cmd:
                with assert_raises(SystemExit):
                    main(["datalad", "run", "--message"])
                exec_cmd.assert_not_called()
            assert_in("message: expected one", cmo.err)
        # If we want to pass an option as the first value of a command (e.g.,
        # because we are using a runscript with containers-run), we can do this
        # with "--".
        with patch("datalad.core.local.run._execute_command") as exec_cmd:
            with assert_raises(SystemExit):
                main(["datalad", "run", "--", "--message"])
            exec_cmd.assert_called_once_with(
                '"--message"' if on_windows else "--message",
                path)

        # Our parser used to mishandle --version (gh-3067),
        # treating 'datalad run CMD --version' as 'datalad --version'.
        # but that is no longer the case and echo --version should work with or
        # without explicit "--" separator
        for sep in [[], ['--']]:
            with patch("datalad.core.local.run._execute_command") as exec_cmd:
                with assert_raises(SystemExit):
                    main(["datalad", "run"] + sep + ["echo", "--version"])
                exec_cmd.assert_called_once_with(
                    '"echo" "--version"' if on_windows else "echo --version",
                    path)


@with_tempfile(mkdir=True)
def test_run_path_semantics(path=None):
    # Test that we follow path resolution from gh-3435: paths are relative to
    # dataset if a dataset instance is given and relative to the current
    # working directory otherwise.

    ds0 = Dataset(op.join(path, "ds0")).create()
    ds0_subdir = op.join(ds0.path, "s0")
    os.mkdir(ds0_subdir)

    # Although not useful, we can specify `dataset` as a string that lines up
    # with the one from the current directory.
    with chpwd(ds0_subdir):
        run("cd .> one", dataset="..")
        run("cd .> one", outputs=["one"], dataset=ds0.path)
    ok_exists(op.join(ds0_subdir, "one"))
    assert_repo_status(ds0.path)

    # Specify string dataset argument, running from another dataset ...

    ds1 = Dataset(op.join(path, "ds1")).create()
    ds1_subdir = op.join(ds1.path, "s1")
    os.mkdir(ds1_subdir)

    # ... producing output file in specified dataset
    with chpwd(ds1_subdir):
        run("cd .> {}".format(op.join(ds0.path, "two")),
            dataset=ds0.path)
    ok_exists(op.join(ds0.path, "two"))
    assert_repo_status(ds0.path)

    # ... producing output file in specified dataset and passing output file as
    # relative to current directory
    with chpwd(ds1_subdir):
        out = op.join(ds0.path, "three")
        run("cd .> {}".format(out), dataset=ds0.path, explicit=True,
            outputs=[op.relpath(out, ds1_subdir)])
    ok_exists(op.join(ds0.path, "three"))
    assert_repo_status(ds0.path)

    # ... producing output file outside of specified dataset, leaving it
    # untracked in the other dataset
    assert_repo_status(ds1.path)
    with chpwd(ds1_subdir):
        run("cd .> four", dataset=ds0.path)
    assert_repo_status(ds1.path, untracked=[ds1_subdir])

    # If we repeat above with an instance instead of the string, the directory
    # for the run is the specified dataset.
    with chpwd(ds1_subdir):
        run("cd .> five", dataset=ds0)
    ok_exists(op.join(ds0.path, "five"))
    assert_repo_status(ds0.path)


@with_tempfile(mkdir=True)
def test_run_remove_keeps_leading_directory(path=None):
    ds = Dataset(op.join(path, "ds")).create()
    repo = ds.repo

    (ds.pathobj / "d").mkdir()
    output = (ds.pathobj / "d" / "foo")
    output.write_text("foo")
    ds.save()

    output_rel = str(output.relative_to(ds.pathobj))
    repo.drop(output_rel, options=["--force"])

    assert_in_results(
        ds.run("cd .> {}".format(output_rel), outputs=[output_rel],
               result_renderer='disabled'),
        action="run.remove", status="ok")

    assert_repo_status(ds.path)

    # Remove still gets saved() if command doesn't generate the output (just as
    # it would if git-rm were used instead of unlink).
    repo.drop(output_rel, options=["--force"])
    assert_in_results(
        ds.run("cd .> something-else", outputs=[output_rel],
               result_renderer='disabled'),
        action="run.remove", status="ok")
    assert_repo_status(ds.path)


@with_tempfile(mkdir=True)
def test_run_reglob_outputs(path=None):
    ds = Dataset(path).create()
    repo = ds.repo
    (ds.pathobj / "write_text.py").write_text("""
import sys
assert len(sys.argv) == 2
name = sys.argv[1]
with open(name + ".txt", "w") as fh:
    fh.write(name)
""")
    ds.save(to_git=True)
    cmd = [sys.executable, "write_text.py"]

    ds.run(cmd + ["foo"], outputs=["*.txt"], expand="outputs")
    assert_in("foo.txt", last_commit_msg(repo))

    ds.run(cmd + ["bar"], outputs=["*.txt"], explicit=True)
    ok_exists(str(ds.pathobj / "bar.txt"))
    assert_repo_status(ds.path)


@with_tempfile(mkdir=True)
def test_run_unexpanded_placeholders(path=None):
    ds = Dataset(path).create()
    cmd = [sys.executable, "-c",
           "import sys; open(sys.argv[1], 'w').write(' '.join(sys.argv[2:]))"]

    # It's weird, but for lack of better options, inputs and outputs that don't
    # have matches are available unexpanded.

    with assert_raises(IncompleteResultsError):
        ds.run(cmd + ["arg1", "{inputs}"], inputs=["foo*"],
               on_failure="continue")
    assert_repo_status(ds.path)
    ok_file_has_content(op.join(path, "arg1"), "foo*")

    ds.run(cmd + ["arg2", "{outputs}"], outputs=["bar*"])
    assert_repo_status(ds.path)
    ok_file_has_content(op.join(path, "arg2"), "bar*")

    ds.run(cmd + ["arg3", "{outputs[1]}"], outputs=["foo*", "bar"])
    ok_file_has_content(op.join(path, "arg3"), "bar")


@with_tempfile(mkdir=True)
def test_run_empty_repo(path=None):
    ds = Dataset(path).create()
    cmd = [sys.executable, "-c", "open('foo', 'w').write('')"]
    # Using "*" in a completely empty repo will fail.
    with assert_raises(IncompleteResultsError):
        ds.run(cmd, inputs=["*"], on_failure="stop")
    assert_repo_status(ds.path)
    # "." will work okay, though.
    assert_status("ok", ds.run(cmd, inputs=["."]))
    assert_repo_status(ds.path)
    ok_exists(str(ds.pathobj / "foo"))


@with_tree(tree={"foo": "f", "bar": "b"})
def test_dry_run(path=None):
    ds = Dataset(path).create(force=True)

    # The dataset is reported as dirty, and the custom result render relays
    # that to the default renderer.
    with swallow_outputs() as cmo:
        with assert_raises(IncompleteResultsError):
            ds.run("blah ", dry_run="basic")
        assert_in("run(impossible)", cmo.out)
        assert_not_in("blah", cmo.out)

    ds.save()

    # unknown dry-run mode
    assert_raises(ValueError, ds.run, 'blah', dry_run='absurd')

    with swallow_outputs() as cmo:
        ds.run("blah ", dry_run="basic")
        assert_in("Dry run", cmo.out)
        assert_in("location", cmo.out)
        assert_in("blah", cmo.out)
        assert_not_in("expanded inputs", cmo.out)
        assert_not_in("expanded outputs", cmo.out)

    with swallow_outputs() as cmo:
        ds.run("blah {inputs} {outputs}", dry_run="basic",
               inputs=["fo*"], outputs=["b*r"])
        assert_in(
            'blah "foo" "bar"' if on_windows else "blah foo bar",
            cmo.out)
        assert_in("expanded inputs", cmo.out)
        assert_in("['foo']", cmo.out)
        assert_in("expanded outputs", cmo.out)
        assert_in("['bar']", cmo.out)

    # Just the command.
    with swallow_outputs() as cmo:
        ds.run("blah ", dry_run="command")
        assert_not_in("Dry run", cmo.out)
        assert_in("blah", cmo.out)
        assert_not_in("inputs", cmo.out)

    # The output file wasn't unlocked.
    assert_repo_status(ds.path)

    # Subdaset handling

    subds = ds.create("sub")
    (subds.pathobj / "baz").write_text("z")
    ds.save(recursive=True)

    # If a subdataset is installed, it works as usual.
    with swallow_outputs() as cmo:
        ds.run("blah {inputs}", dry_run="basic", inputs=["sub/b*"])
        assert_in(
            'blah "sub\\baz"' if on_windows else 'blah sub/baz',
            cmo.out)

    # However, a dry run will not do the install/reglob procedure.
    ds.drop("sub", what='all', reckless='kill', recursive=True)
    with swallow_outputs() as cmo:
        ds.run("blah {inputs}", dry_run="basic", inputs=["sub/b*"])
        assert_in("sub/b*", cmo.out)
        assert_not_in("baz", cmo.out)


@with_tree(tree={OBSCURE_FILENAME + ".t": "obscure",
                 "normal.txt": "normal"})
def test_io_substitution(path=None):
    files = [OBSCURE_FILENAME + ".t", "normal.txt"]
    ds = Dataset(path).create(force=True)
    ds.save()
    # prefix the content of any given file with 'mod::'
    cmd = "import sys; from pathlib import Path; t = [(Path(p), 'mod::' + Path(p).read_text()) for p in sys.argv[1:]]; [k.write_text(v) for k, v in t]"
    cmd_str = "{} -c \"{}\" {{inputs}}".format(sys.executable, cmd)
    # this should run and not crash with permission denied
    ds.run(cmd_str, inputs=["{outputs}"], outputs=["*.t*"],
           result_renderer='disabled')
    # all filecontent got the prefix
    for f in files:
        ok_((ds.pathobj / f).read_text().startswith('mod::'))

    # we could just ds.rerun() now, and it should work, but this would make
    # rerun be a dependency of a core test
    # instead just double-run, but with a non-list input-spec.
    # should have same outcome
    ds.run(cmd_str, inputs="{outputs}", outputs="*.t*",
           result_renderer='disabled')
    for f in files:
        ok_((ds.pathobj / f).read_text().startswith('mod::mod::'))


def test_format_iospecs():
    seq = ['one', 'two']
    eq_(seq, _format_iospecs(['{dummy}'], dummy=seq))
    # garbage when combined with longer spec-sequences
    # but this is unavoidable without introducing a whitelist
    # of supported value types -- which would limit flexibility
    eq_(["['one', 'two']", 'other'],
        _format_iospecs(['{dummy}', 'other'], dummy=seq))


def test_substitution_config():
    # use a shim to avoid having to create an actual dataset
    # the tested function only needs a `ds.config` to be a ConfigManager
    from datalad import cfg

    class dset:
        config = cfg

    # empty be default
    eq_(_get_substitutions(dset), {})
    # basic access
    with patch_config({"datalad.run.substitutions.dummy": 'ork'}):
        eq_(_get_substitutions(dset), dict(dummy='ork'))
    # can report multi-value
    with patch_config({"datalad.run.substitutions.dummy": ['a', 'b']}):
        eq_(_get_substitutions(dset), dict(dummy=['a', 'b']))

        # verify combo with iospec formatting
        eq_(_format_iospecs(['{dummy}'],
                            **_get_substitutions(dset)),
            ['a', 'b'])
