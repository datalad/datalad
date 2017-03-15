# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test command call wrapper
"""

from mock import patch
import os
from os.path import dirname, join as opj
import sys
import logging
import shlex

from .utils import ok_, eq_, assert_is, assert_equal, assert_false, \
    assert_true, assert_greater, assert_raises, assert_in, SkipTest

from ..cmd import Runner, link_file_load
from ..cmd import GitRunner
from ..support.exceptions import CommandError
from ..support.protocol import DryRunProtocol
from .utils import with_tempfile, assert_cwd_unchanged, \
    ignore_nose_capturing_stdout, swallow_outputs, swallow_logs, \
    on_linux, on_osx, on_windows, with_testrepos
from .utils import lgr

from .utils import local_testrepo_flavors


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_runner_dry(tempfile):

    dry = DryRunProtocol()
    runner = Runner(protocol=dry)

    # test dry command call
    cmd = 'echo Testing dry run > %s' % tempfile
    with swallow_logs(new_level=logging.DEBUG) as cml:
        ret = runner.run(cmd)
        cml.assert_logged("{DryRunProtocol} Running: %s" % cmd, regex=False)
    assert_equal(("DRY", "DRY"), ret,
                 "Output of dry run (%s): %s" % (cmd, ret))
    assert_equal(shlex.split(cmd, posix=not on_windows), dry[0]['command'])
    assert_false(os.path.exists(tempfile))

    # test dry python function call
    output = runner.call(os.path.join, 'foo', 'bar')
    assert_is(None, output, "Dry call of: os.path.join, 'foo', 'bar' "
                            "returned: %s" % output)
    assert_in('join', dry[1]['command'][0])
    assert_equal("args=('foo', 'bar')", dry[1]['command'][1])


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_runner(tempfile):

    # test non-dry command call
    runner = Runner()
    cmd = 'echo Testing real run > %r' % tempfile
    ret = runner.run(cmd)
    assert_true(os.path.exists(tempfile),
                "Run of: %s resulted with non-existing file %s" %
                (cmd, tempfile))

    # test non-dry python function call
    output = runner.call(os.path.join, 'foo', 'bar')
    assert_equal(os.path.join('foo', 'bar'), output,
                 "Call of: os.path.join, 'foo', 'bar' returned %s" % output)


@ignore_nose_capturing_stdout
def test_runner_instance_callable_dry():

    cmd_ = ['echo', 'Testing', '__call__', 'with', 'string']
    for cmd in [cmd_, ' '.join(cmd_)]:
        dry = DryRunProtocol()
        runner = Runner(protocol=dry)
        ret = runner(cmd)
        # (stdout, stderr) is returned.  But in dry -- ("DRY","DRY")
        eq_(ret, ("DRY", "DRY"))
        assert_equal(cmd_, dry[0]['command'],
                     "Dry run of Runner.__call__ didn't record command: %s.\n"
                     "Buffer: %s" % (cmd, dry))

    ret = runner(os.path.join, 'foo', 'bar')
    eq_(ret, None)

    assert_in('join', dry[1]['command'][0],
              "Dry run of Runner.__call__ didn't record function join()."
              "Buffer: %s" % dry)
    assert_equal("args=('foo', 'bar')", dry[1]['command'][1],
                 "Dry run of Runner.__call__ didn't record function join()."
                 "Buffer: %s" % dry)


@ignore_nose_capturing_stdout
def test_runner_instance_callable_wet():

    runner = Runner()
    cmd = [sys.executable, "-c", "print('Testing')"]

    out = runner(cmd)
    eq_(out[0].rstrip(), ('Testing'))
    eq_(out[1], '')

    ret = runner(os.path.join, 'foo', 'bar')
    eq_(ret, os.path.join('foo', 'bar'))


@ignore_nose_capturing_stdout
def test_runner_log_stderr():
    # TODO: no idea of how to check correct logging via any kind of
    # assertion yet.

    runner = Runner()
    cmd = 'echo stderr-Message should be logged >&2'
    ret = runner.run(cmd, log_stderr=True, expect_stderr=True)

    cmd = 'echo stderr-Message should not be logged >&2'
    with swallow_outputs() as cmo:
        with swallow_logs(new_level=logging.INFO) as cml:
            ret = runner.run(cmd, log_stderr=False)
            eq_(cmo.err.rstrip(), "stderr-Message should not be logged")
            eq_(cml.out, "")


@ignore_nose_capturing_stdout
def test_runner_log_stdout():
    # TODO: no idea of how to check correct logging via any kind of
    # assertion yet.

    runner = Runner()
    cmd_ = ['echo', 'stdout-Message should be logged']
    for cmd in [cmd_, ' '.join(cmd_)]:
        # should be identical runs, either as a string or as a list
        kw = {}
        # on Windows it can't find echo if ran outside the shell
        if on_windows and isinstance(cmd, list):
            kw['shell'] = True
        with swallow_logs(logging.DEBUG) as cm:
            ret = runner.run(cmd, log_stdout=True, **kw)
            cm.assert_logged("Running: %s" % cmd, level='DEBUG', regex=False)
            from datalad import cfg
            if cfg.getbool('datalad.log', 'outputs', default=False):
                if not on_windows:
                    # we can just count on sanity
                    cm.assert_logged("stdout| stdout-"
                                     "Message should be logged", regex=False)
                else:
                    # echo outputs quoted lines for some reason, so relax check
                    ok_("stdout-Message should be logged" in cm.lines[1])

    cmd = 'echo stdout-Message should not be logged'
    with swallow_outputs() as cmo:
        with swallow_logs(new_level=logging.INFO) as cml:
            ret = runner.run(cmd, log_stdout=False)
            eq_(cmo.out, "stdout-Message should not be logged\n")
            eq_(cml.out, "")


@ignore_nose_capturing_stdout
def check_runner_heavy_output(log_online):
    # TODO: again, no automatic detection of this resulting in being
    # stucked yet.

    runner = Runner()
    cmd = '%s %s' % (sys.executable, opj(dirname(__file__), "heavyoutput.py"))

    with swallow_outputs() as cm, swallow_logs():
        ret = runner.run(cmd, log_stderr=False, log_stdout=False,
                         expect_stderr=True)
        eq_(cm.err, cm.out)  # they are identical in that script
        eq_(cm.out[:10], "[0, 1, 2, ")
        eq_(cm.out[-15:], "997, 998, 999]\n")

    # for some reason swallow_logs is not effective, so we just skip altogether
    # if too heavy debug output
    if lgr.getEffectiveLevel() <= logging.DEBUG:
        raise SkipTest("Skipping due to too heavy impact on logs complicating debugging")

    #do it again with capturing:
    with swallow_logs():
        ret = runner.run(cmd, log_stderr=True, log_stdout=True, expect_stderr=True)

    return
    # and now original problematic command with a massive single line
    if not log_online:
        # We know it would get stuck in online mode
        cmd = '%s -c "import sys; x=str(list(range(1000))); ' \
              '[(sys.stdout.write(x), sys.stderr.write(x)) ' \
              'for i in range(100)];"' % sys.executable
        with swallow_logs():
            ret = runner.run(cmd, log_stderr=True, log_stdout=True,
                             expect_stderr=True)


def test_runner_heavy_output():
    for log_online in [True, False]:
        yield check_runner_heavy_output, log_online


@with_tempfile
def test_link_file_load(tempfile):
    tempfile2 = tempfile + '_'

    with open(tempfile, 'w') as f:
        f.write("LOAD")

    link_file_load(tempfile, tempfile2)  # this should work in general

    ok_(os.path.exists(tempfile2))

    with open(tempfile2, 'r') as f:
        assert_equal(f.read(), "LOAD")

    def inode(fname):
        with open(fname) as fd:
            return os.fstat(fd.fileno()).st_ino

    def stats(fname, times=True):
        """Return stats on the file which should have been preserved"""
        with open(fname) as fd:
            st = os.fstat(fd.fileno())
            stats = (st.st_mode, st.st_uid, st.st_gid, st.st_size)
            if times:
                return stats + (st.st_atime, st.st_mtime)
            else:
                return stats
            # despite copystat mtime is not copied. TODO
            #        st.st_mtime)

    if on_linux or on_osx:
        # above call should result in the hardlink
        assert_equal(inode(tempfile), inode(tempfile2))
        assert_equal(stats(tempfile), stats(tempfile2))

        # and if we mock absence of .link
        def raise_AttributeError(*args):
            raise AttributeError("TEST")

        with patch('os.link', raise_AttributeError):
            with swallow_logs(logging.WARNING) as cm:
                link_file_load(tempfile, tempfile2)  # should still work
                ok_("failed (TEST), copying file" in cm.out)

    # should be a copy (either originally for windows, or after mocked call)
    ok_(inode(tempfile) != inode(tempfile2))
    with open(tempfile2, 'r') as f:
        assert_equal(f.read(), "LOAD")
    assert_equal(stats(tempfile, times=False), stats(tempfile2, times=False))
    os.unlink(tempfile2)  # TODO: next two with_tempfile


@with_tempfile(mkdir=True)
def test_runner_failure(dir_):
    from ..support.annexrepo import AnnexRepo
    repo = AnnexRepo(dir_, create=True)
    runner = Runner()
    failing_cmd = ['git-annex', 'add', 'notexistent.dat']

    with assert_raises(CommandError) as cme, \
         swallow_logs() as cml:
        runner.run(failing_cmd, cwd=dir_)
        assert_in('notexistent.dat not found', cml.out)
    assert_equal(1, cme.exception.code)


@with_tempfile(mkdir=True)
def test_git_path(dir_):
    from ..support.gitrepo import GitRepo
    # As soon as we use any GitRepo we should get _GIT_PATH set in the Runner
    repo = GitRepo(dir_, create=True)
    assert GitRunner._GIT_PATH is not None


@with_tempfile(mkdir=True)
def test_runner_stdin(path):
    runner = Runner()
    with open(opj(path, "test_input.txt"), "w") as f:
        f.write("whatever")

    with swallow_outputs() as cmo, open(opj(path, "test_input.txt"), "r") as fake_input:
        runner.run(['cat'], log_stdout=False, stdin=fake_input)
        assert_in("whatever", cmo.out)
