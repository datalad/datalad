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
import platform
import sys
import logging

from nose.tools import ok_, eq_, assert_is, assert_equal, assert_false, \
    assert_true, assert_greater

from datalad.cmd import Runner, link_file_load
from datalad.tests.utils import with_tempfile, assert_cwd_unchanged, \
    ignore_nose_capturing_stdout, swallow_outputs


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_runner_dry(tempfile):

    runner = Runner(dry=True)

    # test dry command call
    cmd = 'echo Testing dry run > %s' % tempfile
    ret = runner.run(cmd)
    assert_is(None, ret, "Dry run of: %s resulted in exitcode %s" % (cmd, ret))
    assert_greater(runner.commands.__str__().find('echo Testing dry run'), -1,
                 "Dry run of: %s resulted in buffer: %s" % (cmd, runner.commands.__str__()))
    assert_false(os.path.exists(tempfile))

    # test dry python function call
    output = runner.call(os.path.join, 'foo', 'bar')
    assert_is(None, output, "Drycall of: os.path.join, 'foo', 'bar' returned %s" % output)
    assert_greater(runner.commands.__str__().find('join'), -1,
                   "Drycall of: os.path.join, 'foo', 'bar' resulted in buffer: %s" % runner.commands.__str__())



@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_runner(tempfile):

    # test non-dry command call
    runner = Runner(dry=False)
    cmd = 'echo Testing real run > %s' % tempfile
    ret = runner.run(cmd)
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
    assert_equal(runner.commands, [], "Run of: %s resulted in non-empty buffer: %s" % (cmd, runner.commands.__str__()))
    assert_true(os.path.exists(tempfile), "Run of: %s resulted with non-existing file %s" % (cmd, tempfile))

    # test non-dry python function call
    output = runner.call(os.path.join, 'foo', 'bar')
    assert_equal(os.path.join('foo', 'bar'), output,
                 "Drycall of: os.path.join, 'foo', 'bar' returned %s" % output)
    assert_equal(runner.commands.__str__().find('os.path.join'), -1,
                   "Drycall of: os.path.join, 'foo', 'bar' resulted in buffer: %s" % runner.commands.__str__())


@ignore_nose_capturing_stdout
def test_runner_instance_callable():

    cmd_ = ['echo', 'Testing __call__ with string']
    for cmd in [cmd_, ' '.join(cmd_)]:
        runner = Runner(dry=True)
        runner(cmd)
        assert_equal(runner.commands.__str__(), ("[%r]" % cmd),
                     "Dry run of Runner.__call__ didn't record command: %s.\n"
                     "Buffer: %s" % (cmd, runner.commands.__str__()))

    runner(os.path.join, 'foo', 'bar')
    assert_greater(runner.commands.__str__().find('join'), -1,
                   "Dry run of Runner.__call__ didn't record function join()."
                   "Buffer: %s" % runner.commands.__str__())
    assert_greater(runner.commands.__str__().find('args='), -1,
                   "Dry run of Runner.__call__ didn't record function join()."
                   "Buffer: %s" % runner.commands.__str__())


@ignore_nose_capturing_stdout
def test_runner_log_stderr():
    # TODO: no idea of how to check correct logging via any kind of assertion yet.

    runner = Runner(dry=False)
    cmd = 'echo stderr-Message should be logged >&2'
    ret = runner.run(cmd, log_stderr=True)
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
    assert_equal(runner.commands, [], "Run of: %s resulted in non-empty buffer: %s" % (cmd, runner.commands.__str__()))

    cmd = 'echo stderr-Message should not be logged >&2'
    ret = runner.run(cmd, log_stderr=False)
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
    assert_equal(runner.commands, [], "Run of: %s resulted in non-empty buffer: %s" % (cmd, runner.commands.__str__()))


@ignore_nose_capturing_stdout
def test_runner_log_stdout():
    # TODO: no idea of how to check correct logging via any kind of assertion yet.

    lgr = logging.getLogger('datalad.cmd')
    level_old = lgr.getEffectiveLevel()
    lgr.setLevel(logging.DEBUG)

    runner = Runner(dry=False)
    cmd_ = ['echo', 'stdout-Message should be logged']
    for cmd in [cmd_, ' '.join(cmd_)]:
        # should be identical runs, either as a string or as a list
        kw = {}
        # on Windows it can't find echo if ran outside the shell
        if platform.system() in ('Windows',) and isinstance(cmd, list):
            kw['shell'] = True
        ret = runner.run(cmd, log_stdout=True, **kw)
        assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
        assert_equal(runner.commands, [], "Run of: %s resulted in non-empty buffer: %s" % (cmd, runner.commands.__str__()))

    cmd = 'echo stdout-Message should not be logged'
    ret = runner.run(cmd, log_stdout=False)
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
    assert_equal(runner.commands, [], "Run of: %s resulted in non-empty buffer: %s" % (cmd, runner.commands.__str__()))

    lgr.setLevel(level_old)


@ignore_nose_capturing_stdout
def check_runner_heavy_output(log_online):
    # TODO: again, no automatic detection of this resulting in being stucked yet.

    runner = Runner()
    cmd = '%s -c "import datalad.tests.heavyoutput;"' % sys.executable
    with swallow_outputs() as cm:
        ret = runner.run(cmd, log_stderr=False, log_stdout=False, expect_stderr=True)
        eq_(cm.err, cm.out) # they are identical in that script
        eq_(cm.out[:10], "[0, 1, 2, ")
        eq_(cm.out[-15:], "997, 998, 999]\n")
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))

    #do it again with capturing:
    ret = runner.run(cmd, log_stderr=True, log_stdout=True, expect_stderr=True)
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))

    # and now original problematic command with a massive single line
    if not log_online:
        # We know it would get stuck in online mode
        cmd = '%s -c "import sys; x=str(list(range(1000))); [(sys.stdout.write(x), sys.stderr.write(x)) for i in xrange(100)];"' % sys.executable
        ret = runner.run(cmd, log_stderr=True, log_stdout=True, expect_stderr=True)
        assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))

def test_runner_heavy_output():
    for log_online in [True, False]:
        yield check_runner_heavy_output, log_online

@with_tempfile
def test_link_file_load(tempfile):
    tempfile2 = tempfile + '_'

    with open(tempfile, 'w') as f:
        f.write("LOAD")

    link_file_load(tempfile, tempfile2) # this should work in general

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
        class raise_AttributeError:
            def __call__(*args):
                raise AttributeError("TEST")
        with patch('os.link', new_callable=raise_AttributeError):
            link_file_load(tempfile, tempfile2) # should still work

    # should be a copy (either originally for windows, or after mocked call)
    ok_(inode(tempfile) != inode(tempfile2))
    with open(tempfile2, 'r') as f:
        assert_equal(f.read(), "LOAD")
    assert_equal(stats(tempfile, times=False), stats(tempfile2, times=False))
    os.unlink(tempfile2) # TODO: next two with_tempfile

