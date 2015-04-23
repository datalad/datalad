# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test logging facilities """

import re
import os.path
from os.path import exists

from nose.tools import assert_raises, assert_is_instance, assert_true
from git.exc import GitCommandError

from mock import patch

from datalad.log import LoggerHelper

from datalad.tests.utils import with_tempfile, ok_, assert_equal

# pretend we are in interactive mode so we could check if coloring is
# disabled
@patch("datalad.log.is_interactive", lambda: True)
@with_tempfile
def test_logging_to_a_file(dst):
    ok_(not exists(dst))

    lgr = LoggerHelper("dataladtest").get_initialized_logger(logtarget=dst)
    ok_(exists(dst))

    msg = "Oh my god, they killed Kenny"
    lgr.error(msg)
    with open(dst) as f:
        lines = f.readlines()
    assert_equal(len(lines), 1, "Read more than a single log line: %s" %  lines)
    line = lines[0]
    ok_(msg in line)
    ok_(not '\033[' in line,
        msg="There should be no color formatting in log files. Got: %s" % line)
    # verify that time stamp and level are present in the log line
    # do not want to rely on not having race conditions around date/time changes
    # so matching just with regexp
    ok_(re.match("\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \[ERROR\] %s" % msg,
                 line))

@with_tempfile
def test_logtarget_via_env_variable(dst):
    with patch.dict('os.environ', {'DATALADTEST_LOGTARGET': dst}):
        ok_(not exists(dst))
        lgr = LoggerHelper("dataladtest").get_initialized_logger()
        ok_(exists(dst))
    # just to see that mocking patch worked
    ok_(not 'DATALADTEST_LOGTARGET' in os.environ)

@with_tempfile
@with_tempfile
def test_mutliple_targets(dst1, dst2):
    ok_(not exists(dst1))
    ok_(not exists(dst2))
    lgr = LoggerHelper("dataladtest").get_initialized_logger(
        logtarget="%s,%s" % (dst1, dst2))
    ok_(exists(dst1))
    ok_(exists(dst2))

    msg = "Oh my god, they killed Kenny"
    lgr.error(msg)
    for dst in (dst1, dst2):
        with open(dst) as f:
            lines = f.readlines()
        assert_equal(len(lines), 1, "Read more than a single log line: %s" %  lines)
        ok_(msg in lines[0])

# TODO: somehow test is stdout/stderr get their stuff