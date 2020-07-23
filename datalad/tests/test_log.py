# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test logging facilities """

import logging
import os.path
from os.path import exists

from logging import makeLogRecord

from unittest.mock import patch

from datalad.log import (
    ColorFormatter,
    LoggerHelper,
    log_progress,
    TraceBack,
)
from datalad import cfg as dl_cfg
from datalad.support.constraints import EnsureBool
from datalad.support import ansi_colors as colors

from datalad.tests.utils import (
    assert_equal,
    assert_in,
    assert_not_in,
    assert_re_in,
    known_failure_githubci_win,
    ok_,
    ok_endswith,
    swallow_logs,
    with_tempfile,
)

# pretend we are in interactive mode so we could check if coloring is
# disabled
@patch("datalad.log.is_interactive", lambda: True)
@with_tempfile
def test_logging_to_a_file(dst):
    ok_(not exists(dst))

    lgr = LoggerHelper("dataladtest-1").get_initialized_logger(logtarget=dst)
    ok_(exists(dst))  # nothing was logged -- no file created

    msg = "Oh my god, they killed Kenny"
    lgr.error(msg)
    with open(dst) as f:
        lines = f.readlines()
    assert_equal(len(lines), 1, "Read more than a single log line: %s" %  lines)
    line = lines[0]
    ok_(msg in line)
    ok_('\033[' not in line,
        msg="There should be no color formatting in log files. Got: %s" % line)
    # verify that time stamp and level are present in the log line
    # do not want to rely on not having race conditions around date/time changes
    # so matching just with regexp
    # (...)? is added to swallow possible traceback logs
    regex = "\[ERROR\]"
    if EnsureBool()(dl_cfg.get('datalad.log.timestamp', False)):
        regex = "\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} " + regex
    if EnsureBool()(dl_cfg.get('datalad.log.vmem', False)):
        regex += ' RSS/VMS: \S+/\S+( \S+)?\s*'
    regex += "(\s+\S+\s*)? " + msg
    assert_re_in(regex, line, match=True)
    # Close all handlers so windows is happy -- apparently not closed fast enough
    for handler in lgr.handlers:
        handler.close()


@with_tempfile
def test_logtarget_via_env_variable(dst):
    with patch.dict('os.environ', {'DATALADTEST_LOG_TARGET': dst}):
        ok_(not exists(dst))
        lgr = LoggerHelper("dataladtest-2").get_initialized_logger()
        ok_(not exists(dst))
    # just to see that mocking patch worked
    ok_('DATALADTEST_LOG_TARGET' not in os.environ)


@with_tempfile
@with_tempfile
def test_mutliple_targets(dst1, dst2):
    ok_(not exists(dst1))
    ok_(not exists(dst2))
    lgr = LoggerHelper("dataladtest-3").get_initialized_logger(
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
    # Close all handlers so windows is happy -- apparently not closed fast enough
    for handler in lgr.handlers:
        handler.close()


def check_filters(name):
    with swallow_logs(new_level=logging.DEBUG, name=name) as cml:
        lgr1 = logging.getLogger(name + '.goodone')
        lgr2 = logging.getLogger(name + '.anotherone')
        lgr3 = logging.getLogger(name + '.bad')
        lgr1.debug('log1')
        lgr2.info('log2')
        lgr3.info('log3')
        assert_in('log1', cml.out)
        assert_in('log2', cml.out)
        assert 'log3' not in cml.out


def test_filters():
    def _mock_names(self, v, d=None):
        return 'datalad1.goodone,datalad1.anotherone' if v == 'names' else d
    with patch.object(LoggerHelper, '_get_config', _mock_names):
        LoggerHelper('datalad1').get_initialized_logger()
        check_filters('datalad1')

    def _mock_namesre(self, v, d=None):
        return 'datalad.*one' if v == 'namesre' else d
    with patch.object(LoggerHelper, '_get_config', _mock_namesre):
        LoggerHelper('datalad2').get_initialized_logger()
        check_filters('datalad2')


def test_traceback():
    from inspect import currentframe, getframeinfo
    # do not move lines below among themselves -- we rely on consistent line numbers ;)
    tb_line = getframeinfo(currentframe()).lineno + 2
    def rec(tb, n):
        return rec(tb, n-1) if n else tb()
    tb1 = rec(TraceBack(), 10)
    ok_endswith(tb1, ">test_log:%d,%s" % (tb_line + 1, ",".join([str(tb_line)]*10)))

    # we limit to the last 100
    tb1 = rec(TraceBack(collide=True), 110)
    ok_endswith(tb1, "...>test_log:%s" % (",".join([str(tb_line)]*100)))


@known_failure_githubci_win
def test_color_formatter():

    # want to make sure that coloring doesn't get "stuck"
    for use_color in False, True, False:
        # we can't reuse the same object since it gets colored etc inplace
        rec = makeLogRecord(
            dict(msg='very long message',
                 levelname='DEBUG',
                 name='some name'))

        cf = ColorFormatter(use_color=use_color)
        (assert_in if use_color else assert_not_in)(colors.RESET_SEQ, cf.format(rec))


# TODO: somehow test is stdout/stderr get their stuff


@patch("datalad.log.is_interactive", lambda: False)
def test_log_progress_noninteractive_filter():
    name = "dl-test"
    lgr = LoggerHelper(name).get_initialized_logger()
    pbar_id = "lp_test"
    with swallow_logs(new_level=logging.INFO, name=name) as cml:
        log_progress(lgr.info, pbar_id, "Start", label="testing", total=3)
        log_progress(lgr.info, pbar_id, "THERE0", update=1)
        log_progress(lgr.info, pbar_id, "NOT", update=1,
                     noninteractive_level=logging.DEBUG)
        log_progress(lgr.info, pbar_id, "THERE1", update=1,
                     noninteractive_level=logging.INFO)
        log_progress(lgr.info, pbar_id, "Done")
        for present in ["Start", "THERE0", "THERE1", "Done"]:
            assert_in(present, cml.out)
        assert_not_in("NOT", cml.out)
