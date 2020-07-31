# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
from os import (
    mkdir,
    remove,
)
import sys

from unittest.mock import patch

from datalad.utils import (
    assure_unicode,
    chpwd,
    on_windows,
)

from datalad.cmdline.main import main
from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import (
    CommandError,
    NoDatasetFound,
)
from datalad.api import (
    run,
)
from datalad.core.local.run import (
    format_command,
    run_command,
)
from datalad.tests.utils import (
    assert_false,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    create_tree,
    DEFAULT_BRANCH,
    eq_,
    known_failure_appveyor,
    known_failure_githubci_win,
    known_failure_windows,
    neq_,
    OBSCURE_FILENAME,
    ok_,
    ok_exists,
    ok_file_has_content,
    slow,
    swallow_logs,
    swallow_outputs,
    with_tempfile,
    with_testrepos,
    with_tree,
)


@with_tempfile(mkdir=True)
def test_invalid_call(path):
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
def test_basics(path, nodspath):
    ds = Dataset(path).create()
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
        res = ds.run('cd .> empty', message='TEST')
        assert_repo_status(ds.path)
        assert_result_count(res, 2)
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


@known_failure_windows
# ^ For an unknown reason, appveyor started failing after we removed
#   receive.autogc=0 and gc.auto=0 from our common git options (gh-3482).
# moreover the usage of unicode in the file names also breaks this on windows
@with_tempfile(mkdir=True)
def test_py2_unicode_command(path):
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

    with assert_raises(CommandError), swallow_outputs():
        ds.run(u"bβ2.dat")


@with_tempfile(mkdir=True)
def test_sidecar(path):
    ds = Dataset(path).create()
    if ds.repo.is_managed_branch():
        if "8" < ds.repo.git_annex_version < "8.20200309":
            # git-annex's 1978a2420 (2020-03-09) fixed a bug where
            # annexed dotfiles could switch when annex.dotfiles=true
            # was not set in .git/config or git-annex:config.log.
            ds.repo.config.set("annex.dotfiles", "true",
                               where="local", reload=True)
    # Simple sidecar message checks.
    ds.run("cd .> dummy0", message="sidecar arg", sidecar=True)
    assert_not_in('"cmd":', ds.repo.format_commit("%B"))

    ds.config.set("datalad.run.record-sidecar", "false", where="local")
    ds.run("cd .> dummy1", message="sidecar config")

    assert_in('"cmd":', last_commit_msg(ds.repo))

    ds.config.set("datalad.run.record-sidecar", "true", where="local")
    ds.run("cd .> dummy2", message="sidecar config")
    assert_not_in('"cmd":', last_commit_msg(ds.repo))

    # Don't break when config.get() returns multiple values. Here it's two
    # values in .gitconfig, but a more realistic scenario is a value in
    # $repo/.git/config that overrides a setting in ~/.config/git/config.
    ds.config.add("datalad.run.record-sidecar", "false", where="local")
    ds.run("cd .> dummy3", message="sidecar config")
    assert_in('"cmd":', last_commit_msg(ds.repo))


@with_tree(tree={"to_remove": "abc"})
def test_run_save_deletion(path):
    ds = Dataset(path).create(force=True)
    ds.save()
    ds.run("{} to_remove".format("del" if on_windows else "rm"))
    assert_repo_status(ds.path)


@known_failure_appveyor  # causes appveyor (only) to crash, reason unknown
@with_tempfile(mkdir=True)
def test_run_from_subds(path):
    subds = Dataset(path).create().create("sub")
    subds.run("cd .> foo")
    assert_repo_status(subds.path)


@with_tree(tree={"sub": {"input": ""}})
def test_run_from_subds_gh3551(path):
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


# unexpected content of state "modified", likely a more fundamental issue with the
# testrepo setup
@known_failure_githubci_win
@with_testrepos('basic_annex', flavors=['clone'])
def test_run_explicit(path):
    ds = Dataset(path)

    assert_false(ds.repo.file_has_content("test-annex.dat"))

    create_tree(ds.path, {"dirt_untracked": "untracked",
                          "dirt_modified": "modified"})
    ds.save("dirt_modified", to_git=True)
    with open(op.join(path, "dirt_modified"), "a") as ofh:
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

    remove(op.join(path, "doubled.dat"))

    hexsha_initial = ds.repo.get_hexsha()
    ds.run("cat test-annex.dat test-annex.dat >doubled.dat",
           inputs=["test-annex.dat"], outputs=["doubled.dat"],
           explicit=True)
    ok_(ds.repo.file_has_content("doubled.dat"))
    assert_repo_status(ds.path, modified=["dirt_modified"], untracked=['dirt_untracked'])
    neq_(hexsha_initial, ds.repo.get_hexsha())

    # Saving explicit outputs works from subdirectories.
    subdir = op.join(path, "subdir")
    mkdir(subdir)
    with chpwd(subdir):
        run("echo insubdir >foo", explicit=True, outputs=["foo"])
    ok_(ds.repo.file_has_content(op.join("subdir", "foo")))


@known_failure_windows  # due to use of obscure filename that breaks the runner on Win
@with_tree(tree={OBSCURE_FILENAME + u".t": "obscure",
                 "bar.txt": "b",
                 "foo blah.txt": "f"})
def test_inputs_quotes_needed(path):
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
        eq_(assure_unicode(ifh.read()), expected)
    # ... but the list form of a command does not. (Don't test this failure
    # with the obscure file name because we'd need to know its composition to
    # predict the failure.)
    cmd_list = [sys.executable, "-c", cmd, "{inputs}", "{outputs[0]}"]
    ds.run(cmd_list, inputs=["*.txt"], outputs=["out0"])
    ok_file_has_content(op.join(path, "out0"), "bar.txt foo!blah.txt!out0")


@with_tree(tree={"foo": "f", "bar": "b"})
def test_inject(path):
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
def test_format_command_strip_leading_dashes(path):
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
def test_run_cmdline_disambiguation(path):
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
                path, expected_exit=None)

        # And a twist on above: Our parser mishandles --version (gh-3067),
        # treating 'datalad run CMD --version' as 'datalad --version'.
        version_stream = "out"
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
        with patch("datalad.core.local.run._execute_command") as exec_cmd:
            with assert_raises(SystemExit):
                main(["datalad", "run", "--", "echo", "--version"])
            exec_cmd.assert_called_once_with(
                '"echo" "--version"' if on_windows else "echo --version",
                path, expected_exit=None)


@with_tempfile(mkdir=True)
def test_run_path_semantics(path):
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
