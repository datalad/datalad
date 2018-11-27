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

import os.path as op
from os import (
    mkdir,
    remove,
)
import sys

from six.moves import StringIO
from mock import patch

from datalad.utils import (
    assure_unicode,
    chpwd,
)

from datalad_revolution.dataset import RevolutionDataset as Dataset
from datalad_revolution.tests.utils import assert_repo_status
from datalad.support.exceptions import (
    NoDatasetArgumentFound,
    CommandError,
)
from datalad.api import (
    install,
    rev_run as run,
)
from datalad.interface.run import (
    GlobbedPaths,
    run_command,
)
from datalad.interface.rerun import (
    get_run_info,
    diff_revision,
    new_or_modified,
)
from datalad.tests.utils import (
    assert_raises,
    assert_false,
    assert_dict_equal,
    with_tempfile,
    with_tree,
    ok_,
    ok_exists,
    ok_file_has_content,
    create_tree,
    eq_,
    neq_,
    assert_status,
    assert_result_count,
    assert_in,
    assert_not_in,
    swallow_logs,
    swallow_outputs,
    known_failure_windows,
    ignore_nose_capturing_stdout,
    slow,
    with_testrepos,
    OBSCURE_FILENAME,
)


@with_tempfile(mkdir=True)
def test_invalid_call(path):
    with chpwd(path):
        # no dataset, no luck
        assert_raises(NoDatasetArgumentFound, run, 'doesntmatter')
        # dirty dataset
        ds = Dataset(path).rev_create()
        create_tree(ds.path, {'this': 'dirty'})
        assert_status('impossible', run('doesntmatter', on_failure='ignore'))


@ignore_nose_capturing_stdout
@known_failure_windows
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_basics(path, nodspath):
    ds = Dataset(path).rev_create()
    last_state = ds.repo.get_hexsha()
    # run inside the dataset
    with chpwd(path), \
            swallow_outputs():
        # provoke command failure
        with assert_raises(CommandError) as cme:
            ds.rev_run('7i3amhmuch9invalid')
            # let's not speculate that the exit code is always 127
            ok_(cme.code > 0)
        eq_(last_state, ds.repo.get_hexsha())
        # now one that must work
        res = ds.rev_run('touch empty', message='TEST')
        assert_repo_status(ds.path)
        assert_result_count(res, 2)
        # TODO 'state' is still untracked!!!
        assert_result_count(res, 1, action='add', path=op.join(ds.path, 'empty'), type='file')
        assert_result_count(res, 1, action='save', path=ds.path)
        commit_msg = ds.repo.repo.head.commit.message
        ok_(commit_msg.startswith('[DATALAD RUNCMD] TEST'))
        # crude test that we have a record for the PWD
        assert_in('"pwd": "."', commit_msg)
        last_state = ds.repo.get_hexsha()
        # now run a command that will not alter the dataset
        res = ds.rev_run('touch empty', message='NOOP_TEST')
        # When in direct mode, check at the level of save rather than add
        # because the annex files show up as typechanges and adding them won't
        # necessarily have a "notneeded" status.
        assert_result_count(res, 1, action='save',
                            status='notneeded')
        eq_(last_state, ds.repo.get_hexsha())
        # We can also run the command via a single-item list because this is
        # what the CLI interface passes in for quoted commands.
        res = ds.rev_run(['touch empty'], message='NOOP_TEST')
        assert_result_count(res, 1, action='save',
                            status='notneeded')

    # run outside the dataset, should still work but with limitations
    with chpwd(nodspath), \
            swallow_outputs():
        res = ds.rev_run(['touch', 'empty2'], message='TEST')
        assert_result_count(res, 1, action='add', path=op.join(ds.path, 'empty2'), type='file',
                            status='ok')
        assert_result_count(res, 1, action='save', status='ok')

    # running without a command is a noop
    with chpwd(path):
        with swallow_logs(new_level=logging.WARN) as cml:
            ds.rev_run()
            assert_in("No command given", cml.out)

    # Simple sidecar message checks.
    ds.rev_run(["touch", "dummy0"], message="sidecar arg", sidecar=True)
    assert_not_in('"cmd":', ds.repo.repo.head.commit.message)

    real_get = ds.config.get

    def mocked_get(key, default=None):
        if key == "datalad.run.record-sidecar":
            return True
        return real_get(key, default)

    with patch.object(ds.config, "get", mocked_get):
        ds.rev_run(["touch", "dummy1"], message="sidecar config")
    assert_not_in('"cmd":', ds.repo.repo.head.commit.message)


@ignore_nose_capturing_stdout
@known_failure_windows
@with_tempfile(mkdir=True)
def test_run_failure(path):
    ds = Dataset(path).rev_create()

    hexsha_initial = ds.repo.get_hexsha()

    with assert_raises(CommandError):
        ds.rev_run("echo x$(cat grows) > grows && false")
    eq_(hexsha_initial, ds.repo.get_hexsha())
    ok_(ds.repo.dirty)

    msgfile = op.join(path, ds.repo.get_git_dir(ds.repo), "COMMIT_EDITMSG")
    ok_exists(msgfile)

    ds.rev_save(message_file=msgfile)
    assert_repo_status(ds.path)
    neq_(hexsha_initial, ds.repo.get_hexsha())

    outfile = op.join(ds.path, "grows")
    eq_('x\n', open(outfile).read())


@with_tree(tree={"d": {"to_modify": "content1"},
                 "to_remove": "content2",
                 "to_modify": "content3",
                 "unchanged": "content4"})
def test_new_or_modified(path):
    def get_new_or_modified(*args, **kwargs):
        return [op.relpath(ap["path"], path)
                for ap in new_or_modified(diff_revision(*args, **kwargs))]

    ds = Dataset(path).rev_create(force=True, no_annex=True)

    # Check out an orphan branch so that we can test the "one commit
    # in a repo" case.
    ds.repo.checkout("orph", options=["--orphan"])
    ds.rev_save()
    assert_false(ds.repo.dirty)
    assert_result_count(ds.repo.repo.git.rev_list("HEAD").split(), 1)
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
    ds.rev_save(["to_modify", "d/to_modify"])

    eq_(set(get_new_or_modified(ds, "HEAD")),
        {"to_modify", "d/to_modify"})

    # Non-HEAD revisions work.
    ds.repo.commit("empty", options=["--allow-empty"])
    assert_false(get_new_or_modified(ds, "HEAD"))
    eq_(set(get_new_or_modified(ds, "HEAD~")),
        {"to_modify", "d/to_modify"})


@slow  # ~10s
@ignore_nose_capturing_stdout
@known_failure_windows
@with_tree(tree={"test-annex.dat": "content",
                 "s0": {"s1_0": {"s2": {"a.dat": "a",
                                        "b.txt": "b"}},
                        "s1_1": {"s2": {"c.dat": "c",
                                        "d.txt": "d"}},
                        "ss": {"e.dat": "e"}}})
@with_tempfile(mkdir=True)
def test_run_inputs_outputs(src, path):
    for subds in [("s0", "s1_0", "s2"),
                  ("s0", "s1_1", "s2"),
                  ("s0", "s1_0"),
                  ("s0", "s1_1"),
                  ("s0", "ss"),
                  ("s0",)]:
        Dataset(op.join(*((src,) + subds))).rev_create(force=True)
    src_ds = Dataset(src).rev_create(force=True)
    # TODO this chaneg would break the test! A bug is hidden somewhere
    #src_ds.rev_save(recursive=True)
    src_ds.add('.', recursive=True)

    ds = install(path, source=src,
                 result_xfm='datasets', return_type='item-or-list')
    ds = Dataset(ds.path)
    assert_false(ds.repo.file_has_content("test-annex.dat"))

    # If we specify test-annex.dat as an input, it will be retrieved before the
    # run.
    ds.rev_run("cat test-annex.dat test-annex.dat >doubled.dat",
           inputs=["test-annex.dat"])

    assert_repo_status(ds.path)
    ok_(ds.repo.file_has_content("test-annex.dat"))
    ok_(ds.repo.file_has_content("doubled.dat"))

    # Rerunning the commit will also get the input file.
    ds.repo.drop("test-annex.dat", options=["--force"])
    assert_false(ds.repo.file_has_content("test-annex.dat"))
    ds.rerun()
    ok_(ds.repo.file_has_content("test-annex.dat"))

    with swallow_logs(new_level=logging.WARN) as cml:
        ds.rev_run("touch dummy", inputs=["not-there"])
        assert_in("Input does not exist: ", cml.out)

    # Test different combinations of globs and explicit files.
    inputs = ["a.dat", "b.dat", "c.txt", "d.txt"]
    create_tree(ds.path, {i: i for i in inputs})

    ds.rev_save()
    ds.repo.copy_to(inputs, remote="origin")
    ds.repo.drop(inputs, options=["--force"])

    test_cases = [(["*.dat"], ["a.dat", "b.dat"]),
                  (["*.dat", "c.txt"], ["a.dat", "b.dat", "c.txt"]),
                  (["*"], inputs)]

    for idx, (inputs_arg, expected_present) in enumerate(test_cases):
        assert_false(any(ds.repo.file_has_content(i) for i in inputs))

        ds.rev_run("touch dummy{}".format(idx), inputs=inputs_arg)
        ok_(all(ds.repo.file_has_content(f) for f in expected_present))
        # Globs are stored unexpanded by default.
        assert_in(inputs_arg[0], ds.repo.repo.head.commit.message)
        ds.repo.drop(inputs, options=["--force"])

    # --input can be passed a subdirectory.
    create_tree(ds.path, {"subdir": {"a": "subdir a",
                                     "b": "subdir b"}})
    ds.rev_save("subdir")
    ds.repo.copy_to(["subdir/a", "subdir/b"], remote="origin")
    ds.repo.drop("subdir", options=["--force"])
    ds.rev_run("touch subdir-dummy", inputs=[op.join(ds.path, "subdir")])
    ok_(all(ds.repo.file_has_content(op.join("subdir", f)) for f in ["a", "b"]))

    # Inputs are specified relative to a dataset's subdirectory.
    ds.repo.drop(op.join("subdir", "a"), options=["--force"])
    with chpwd(op.join(path, "subdir")):
        run("touch subdir-dummy1", inputs=["a"])
    ok_(ds.repo.file_has_content(op.join("subdir", "a")))

    # --input=. runs "datalad get ."
    ds.rev_run("touch dot-dummy", inputs=["."])
    eq_(ds.repo.get_annexed_files(),
        ds.repo.get_annexed_files(with_content_only=True))
    # On rerun, we get all files, even those that weren't in the tree at the
    # time of the run.
    create_tree(ds.path, {"after-dot-run": "after-dot-run content"})
    ds.rev_save()
    ds.repo.copy_to(["after-dot-run"], remote="origin")
    ds.repo.drop(["after-dot-run"], options=["--force"])
    ds.rerun("HEAD^")
    ds.repo.file_has_content("after-dot-run")

    # --output will unlock files that are present.
    ds.repo.get("a.dat")
    ds.rev_run("echo ' appended' >>a.dat", outputs=["a.dat"])
    with open(op.join(path, "a.dat")) as fh:
        eq_(fh.read(), "a.dat appended\n")

    # --output will remove files that are not present.
    ds.repo.drop(["a.dat", "d.txt"], options=["--force"])
    ds.rev_run("echo ' appended' >>a.dat", outputs=["a.dat"])
    with open(op.join(path, "a.dat")) as fh:
        eq_(fh.read(), " appended\n")

    # --input can be combined with --output.
    ds.repo.repo.git.reset("--hard", "HEAD~2")
    ds.rev_run("echo ' appended' >>a.dat", inputs=["a.dat"], outputs=["a.dat"])
    with open(op.join(path, "a.dat")) as fh:
        eq_(fh.read(), "a.dat appended\n")

    with swallow_logs(new_level=logging.DEBUG) as cml:
        ds.rev_run("echo blah", outputs=["not-there"])
        assert_in("Filtered out non-existing path: ", cml.out)

    ds.rev_create('sub')
    ds.rev_run("echo sub_orig >sub/subfile")
    ds.rev_run("echo sub_overwrite >sub/subfile", outputs=["sub/subfile"])
    ds.drop("sub/subfile", check=False)
    ds.rev_run("echo sub_overwrite >sub/subfile", outputs=["sub/subfile"])

    # --input/--output globs can be stored in expanded form.
    ds.rev_run("touch expand-dummy", inputs=["a.*"], outputs=["b.*"], expand="both")
    assert_in("a.dat", ds.repo.repo.head.commit.message)
    assert_in("b.dat", ds.repo.repo.head.commit.message)

    res = ds.rerun(report=True, return_type='item-or-list')
    eq_(res["run_info"]['inputs'], ["a.dat"])
    eq_(res["run_info"]['outputs'], ["b.dat"])

    # We install subdatasets to fully resolve globs.
    ds.uninstall("s0")
    assert_false(Dataset(op.join(path, "s0")).is_installed())
    ds.rev_run("echo {inputs} >globbed-subds", inputs=["s0/s1_*/s2/*.dat"])
    ok_file_has_content(op.join(ds.path, "globbed-subds"),
                        "s0/s1_0/s2/a.dat s0/s1_1/s2/c.dat",
                        strip=True)

    ds_ss = Dataset(op.join(path, "s0", "ss"))
    assert_false(ds_ss.is_installed())
    ds.rev_run("echo blah >{outputs}", outputs=["s0/ss/out"])
    ok_(ds_ss.is_installed())
    ok_file_has_content(op.join(ds.path, "s0", "ss", "out"),
                        "blah",
                        strip=True)


@ignore_nose_capturing_stdout
@known_failure_windows
@with_tempfile(mkdir=True)
def test_run_inputs_no_annex_repo(path):
    ds = Dataset(path).rev_create(no_annex=True)
    # Running --input in a plain Git repo doesn't fail.
    ds.rev_run("touch dummy", inputs=["*"])
    ok_exists(op.join(ds.path, "dummy"))
    ds.rerun()


@slow  # ~10s
@ignore_nose_capturing_stdout
@known_failure_windows
@with_testrepos('basic_annex', flavors=['clone'])
def test_run_explicit(path):
    ds = Dataset(path)

    assert_false(ds.repo.file_has_content("test-annex.dat"))

    create_tree(ds.path, {"dirt_untracked": "untracked",
                          "dirt_modified": "modified"})
    ds.rev_save("dirt_modified", to_git=True)
    with open(op.join(path, "dirt_modified"), "a") as ofh:
        ofh.write(", more")

    # We need explicit=True to run with dirty repo.
    assert_status("impossible",
                  ds.rev_run("cat test-annex.dat test-annex.dat >doubled.dat",
                         inputs=["test-annex.dat"],
                         on_failure="ignore"))

    hexsha_initial = ds.repo.get_hexsha()
    # If we specify test-annex.dat as an input, it will be retrieved before the
    # run.
    ds.rev_run("cat test-annex.dat test-annex.dat >doubled.dat",
           inputs=["test-annex.dat"], explicit=True)
    ok_(ds.repo.file_has_content("test-annex.dat"))
    # We didn't commit anything because outputs weren't specified.
    assert_false(ds.repo.file_has_content("doubled.dat"))
    eq_(hexsha_initial, ds.repo.get_hexsha())

    # If an input doesn't exist, we just show the standard warning.
    with swallow_logs(new_level=logging.WARN) as cml:
        ds.rev_run("ls", inputs=["not-there"], explicit=True)
        assert_in("Input does not exist: ", cml.out)

    remove(op.join(path, "doubled.dat"))

    hexsha_initial = ds.repo.get_hexsha()
    ds.rev_run("cat test-annex.dat test-annex.dat >doubled.dat",
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


@ignore_nose_capturing_stdout
@known_failure_windows
@with_tree(tree={"a.in": "a", "b.in": "b", "c.out": "c",
                 "subdir": {}})
def test_placeholders(path):
    ds = Dataset(path).rev_create(force=True)
    ds.rev_save()
    assert_repo_status(ds.path, untracked=['subdir'])
    ds.rev_run("echo {inputs} >{outputs}", inputs=[".", "*.in"], outputs=["c.out"])
    ok_file_has_content(op.join(path, "c.out"), "a.in b.in\n")

    hexsha_before = ds.repo.get_hexsha()
    ds.rerun()
    eq_(hexsha_before, ds.repo.get_hexsha())

    ds.rev_run("echo {inputs[0]} >getitem", inputs=["*.in"])
    ok_file_has_content(op.join(path, "getitem"), "a.in\n")

    ds.rev_run("echo {pwd} >expanded-pwd")
    ok_file_has_content(op.join(path, "expanded-pwd"), path,
                        strip=True)

    ds.rev_run("echo {dspath} >expanded-dspath")
    ok_file_has_content(op.join(path, "expanded-dspath"), ds.path,
                        strip=True)

    subdir_path = op.join(path, "subdir")
    with chpwd(subdir_path):
        run("echo {pwd} >expanded-pwd")
    ok_file_has_content(op.join(path, "subdir", "expanded-pwd"), subdir_path,
                        strip=True)
    eq_(get_run_info(ds, ds.repo.repo.head.commit.message)[1]["pwd"],
        "subdir")

    # Double brackets can be used to escape placeholders.
    ds.rev_run("touch {{inputs}}", inputs=["*.in"])
    ok_exists(op.join(path, "{inputs}"))

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
        ds.rev_run("{unknown_placeholder}", on_failure="ignore"),
        1, status="impossible", action="run")

    # Configured placeholders.
    ds.config.add("datalad.run.substitutions.license", "gpl3", where="local")
    ds.rev_run("echo {license} >configured-license")
    ok_file_has_content(op.join(path, "configured-license"), "gpl3", strip=True)
    # --script handles configured placeholders.
    with patch("sys.stdout", new_callable=StringIO) as cmout:
        ds.rerun(script="-")
        assert_in("gpl3", cmout.getvalue())


@ignore_nose_capturing_stdout
@known_failure_windows
@with_tree(tree={OBSCURE_FILENAME + u".t": "obscure",
                 "bar.txt": "b",
                 "foo blah.txt": "f"})
def test_inputs_quotes_needed(path):
    ds = Dataset(path).rev_create(force=True)
    ds.rev_save(".")
    cmd = "import sys; open(sys.argv[-1], 'w').write('!'.join(sys.argv[1:]))"
    # The string form of a command works fine when the inputs/outputs have
    # spaces ...
    cmd_str = "{} -c \"{}\" {{inputs}} {{outputs[0]}}".format(
        sys.executable, cmd)
    ds.rev_run(cmd_str, inputs=["*.t*"], outputs=["out0"])
    expected = u"!".join(
        list(sorted([OBSCURE_FILENAME + u".t", "bar.txt", "foo blah.txt"])) +
        ["out0"])
    with open(op.join(path, "out0")) as ifh:
        eq_(assure_unicode(ifh.read()), expected)
    # ... but the list form of a command does not. (Don't test this failure
    # with the obscure file name because we'd need to know its composition to
    # predict the failure.)
    cmd_list = [sys.executable, "-c", cmd, "{inputs}", "{outputs[0]}"]
    ds.rev_run(cmd_list, inputs=["*.txt"], outputs=["out0"])
    ok_file_has_content(op.join(path, "out0"), "bar.txt foo!blah.txt!out0")


@ignore_nose_capturing_stdout
@known_failure_windows
@with_tree(tree={"foo": "f", "bar": "b"})
def test_inject(path):
    ds = Dataset(path).rev_create(force=True)
    assert_repo_status(ds.path, untracked=['foo', 'bar'])
    list(run_command("nonsense command",
                     dataset=ds,
                     inject=True,
                     extra_info={"custom_key": "custom_field"}))
    msg = ds.repo.format_commit("%B")
    assert_in("custom_key", msg)
    assert_in("nonsense command", msg)


def test_globbedpaths_get_sub_patterns():
    gp = GlobbedPaths([], "doesn't matter")
    for pat, expected in [
            # If there are no patterns in the directory component, we get no
            # sub-patterns.
            ("", []),
            ("nodir", []),
            (op.join("nomagic", "path"), []),
            (op.join("nomagic", "path*"), []),
            # Create sub-patterns from leading path, successively dropping the
            # right-most component.
            (op.join("s*", "path"), ["s*" + op.sep]),
            (op.join("s", "ss*", "path"), [op.join("s", "ss*") + op.sep]),
            (op.join("s", "ss*", "path*"), [op.join("s", "ss*") + op.sep]),
            (op.join("s", "ss*" + op.sep), []),
            (op.join("s*", "ss", "path*"),
             [op.join("s*", "ss") + op.sep,
              "s*" + op.sep]),
            (op.join("s?", "ss", "sss*", "path*"),
             [op.join("s?", "ss", "sss*") + op.sep,
              op.join("s?", "ss") + op.sep,
              "s?" + op.sep])]:
        eq_(gp._get_sub_patterns(pat), expected)


@with_tree(tree={"1.txt": "",
                 "2.dat": "",
                 "3.txt": ""})
def test_globbedpaths(path):
    for patterns, expected in [
            (["1.txt", "2.dat"], {"1.txt", "2.dat"}),
            (["*.txt", "*.dat"], {"1.txt", "2.dat", "3.txt"}),
            (["*.txt"], {"1.txt", "3.txt"})]:
        gp = GlobbedPaths(patterns, pwd=path)
        eq_(set(gp.expand()), expected)
        eq_(set(gp.expand(full=True)),
            {op.join(path, p) for p in expected})

    # Full patterns still get returned as relative to pwd.
    gp = GlobbedPaths([op.join(path, "*.dat")], pwd=path)
    eq_(gp.expand(), ["2.dat"])

    # "." gets special treatment.
    gp = GlobbedPaths([".", "*.dat"], pwd=path)
    eq_(set(gp.expand()), {"2.dat", "."})
    eq_(gp.expand(dot=False), ["2.dat"])
    gp = GlobbedPaths(["."], pwd=path, expand=False)
    eq_(gp.expand(), ["."])
    eq_(gp.paths, ["."])

    # We can the glob outputs.
    glob_results = {"z": "z",
                    "a": ["x", "d", "b"]}
    with patch('glob.glob', glob_results.get):
        gp = GlobbedPaths(["z", "a"])
        eq_(gp.expand(), ["z", "b", "d", "x"])

    # glob expansion for paths property is determined by expand argument.
    for expand, expected in [(True, ["2.dat"]), (False, ["*.dat"])]:
        gp = GlobbedPaths(["*.dat"], pwd=path, expand=expand)
        eq_(gp.paths, expected)

    with swallow_logs(new_level=logging.DEBUG) as cml:
        GlobbedPaths(["not here"], pwd=path).expand()
        assert_in("No matching files found for 'not here'", cml.out)


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
