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
from datalad.tests.utils import ok_, assert_false
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
from datalad.tests.utils import skip_if_on_windows
from datalad.tests.utils import ignore_nose_capturing_stdout


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
    ds.rerun(revision="HEAD~")
    eq_('xxx\n', open(probe_path).read())
    # Or a range of commits, skipping non-run commits.
    ds.rerun(revision="HEAD~3..")
    eq_('xxxxx\n', open(probe_path).read())


@ignore_nose_capturing_stdout
@skip_if_on_windows
@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
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
    ds.repo.add(".", commit=True)
    assert_false(ds.repo.dirty)

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
