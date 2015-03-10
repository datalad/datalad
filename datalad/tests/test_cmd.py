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

import os
import sys
import logging

from nose.tools import assert_is, assert_equal, assert_false, assert_true, assert_greater

from datalad.cmd import Runner
from datalad.tests.utils import with_tempfile, assert_cwd_unchanged, ignore_nose_capturing_stdout


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_runner_dry(tempfile):

    runner = Runner(dry=True)

    # test dry command call
    cmd = 'echo Testing dry run > %s' % tempfile
    ret = runner.run(cmd)
    assert_is(None, ret, "Dry run of: %s resulted in exitcode %s" % (cmd, ret))
    assert_equal(runner.commands.__str__(), ("['%s']" % cmd),
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

    runner = Runner(dry=True)
    cmd = 'echo Testing __call__ with string'
    runner(cmd)
    assert_equal(runner.commands.__str__(), ("['%s']" % cmd),
                 "Dry run of Runner.__call__ didn't record command: %s.\nBuffer: %s" % (cmd, runner.commands.__str__()))

    runner(os.path.join, 'foo', 'bar')
    assert_greater(runner.commands.__str__().find('join'), -1,
                   "Dry run of Runner.__call__ didn't record function join(). Buffer: %s" % runner.commands.__str__())
    assert_greater(runner.commands.__str__().find('args='), -1,
                   "Dry run of Runner.__call__ didn't record function join(). Buffer: %s" % runner.commands.__str__())


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
    cmd = 'echo stdout-Message should be logged'
    ret = runner.run(cmd, log_stdout=True)
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
    assert_equal(runner.commands, [], "Run of: %s resulted in non-empty buffer: %s" % (cmd, runner.commands.__str__()))

    cmd = 'echo stdout-Message should not be logged'
    ret = runner.run(cmd, log_stdout=False)
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
    assert_equal(runner.commands, [], "Run of: %s resulted in non-empty buffer: %s" % (cmd, runner.commands.__str__()))

    lgr.setLevel(level_old)


@ignore_nose_capturing_stdout
def test_runner_heavy_output():
    # TODO: again, no automatic detection of this resulting in being stucked yet.

    runner = Runner()
    cmd = '%s -c "import sys; x=str(list(range(1000))); [(sys.stdout.write(x), sys.stderr.write(x)) for i in xrange(100)];"' % sys.executable
    ret = runner.run(cmd)
    assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
