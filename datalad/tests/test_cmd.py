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

import nose.tools

from datalad.cmd2 import Runner
from datalad.tests.utils import with_tempfile, assert_cwd_unchanged


@assert_cwd_unchanged
@with_tempfile
def test_runner_dry(tempfile):

    runner = Runner(dry=True)
    cmd = 'echo Testing dry run > %s' % tempfile
    ret = runner.run(cmd)
    nose.tools.assert_is(None, ret, "Dry run of: %s resulted in exitcode %s" % (cmd, ret))
    nose.tools.assert_equal(runner.cmdBuffer.__str__(), ("['%s']" % cmd), "Dry run of: %s resulting buffer: %s" % (cmd, runner.cmdBuffer.__str__()))
    nose.tools.assert_false(os.path.exists(tempfile))


@assert_cwd_unchanged
@with_tempfile
def test_runner(tempfile):

    runner = Runner(dry=False)
    cmd = 'echo Testing real run > %s' % tempfile
    ret = runner.run(cmd)
    nose.tools.assert_equal(0, ret, "Run of: %s resulted in exitcode %s" % (cmd, ret))
    nose.tools.assert_equal(runner.cmdBuffer, [], "Run of: %s resulted in non-empty buffer: %s" % (cmd, runner.cmdBuffer.__str__()))
    nose.tools.assert_true(os.path.exists(tempfile), "Run of: %s resulted with non-existing file %s" % (cmd, tempfile))


