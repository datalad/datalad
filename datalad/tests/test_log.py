# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test logging facilities """

import inspect
import logging
import os.path
from logging import makeLogRecord
from os.path import exists
from unittest.mock import patch

from datalad import cfg as dl_cfg
from datalad.log import (
    ColorFormatter,
    LoggerHelper,
    TraceBack,
    log_progress,
    with_progress,
    with_result_progress,
)
from datalad.support import ansi_colors as colors
from datalad.support.constraints import EnsureBool
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_in,
    assert_no_open_files,
    assert_not_in,
    assert_re_in,
    known_failure_githubci_win,
    ok_,
    ok_endswith,
    ok_generator,
    swallow_logs,
    with_tempfile,
)
from datalad.utils import on_windows


# pretend we are in interactive mode so we could check if coloring is
# disabled
@patch("datalad.log.is_interactive", lambda: True)
@with_tempfile
def test_logging_to_a_file(dst=None):
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
    regex = r"\[ERROR\]"
    if EnsureBool()(dl_cfg.get('datalad.log.timestamp', False)):
        regex = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} " + regex
    if EnsureBool()(dl_cfg.get('datalad.log.vmem', False)):
        regex += r' RSS/VMS: \S+/\S+( \S+)?\s*'
    regex += r"(\s+\S+\s*)? " + msg
    assert_re_in(regex, line, match=True)

    # Python's logger is ok (although not documented as supported) to accept
    # non-string messages, which could be str()'ed.  We should not puke
    msg2 = "Kenny is alive"
    lgr.error(RuntimeError(msg2))
    with open(dst) as f:
        assert_in(msg2, f.read())

    # Close all handlers so windows is happy -- apparently not closed fast enough
    for handler in lgr.handlers:
        handler.close()
    assert_no_open_files(dst)


@with_tempfile
def test_logtarget_via_env_variable(dst=None):
    with patch.dict('os.environ', {'DATALADTEST_LOG_TARGET': dst}):
        ok_(not exists(dst))
        lgr = LoggerHelper("dataladtest-2").get_initialized_logger()
        ok_(not exists(dst))
    # just to see that mocking patch worked
    ok_('DATALADTEST_LOG_TARGET' not in os.environ)


@with_tempfile
@with_tempfile
def test_mutliple_targets(dst1=None, dst2=None):
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
        assert_not_in('log3', cml.out)


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
    from inspect import (
        currentframe,
        getframeinfo,
    )

    # do not move lines below among themselves -- we rely on consistent line numbers ;)
    tb_line = getframeinfo(currentframe()).lineno + 2
    def rec(tb, n):
        return rec(tb, n-1) if n else tb()
    tb1 = rec(TraceBack(), 10)
    ok_endswith(tb1, ">test_log:%d,%s" % (tb_line + 1, ",".join([str(tb_line)]*10)))

    # we limit to the last 100
    tb1 = rec(TraceBack(collide=True), 110)
    ok_endswith(tb1, "…>test_log:%s" % (",".join([str(tb_line)]*100)))


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
        if on_windows:
            raise SkipTest('Unclear under which conditions coloring should work')
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


def test_with_result_progress_generator():
    # Tests ability for the decorator to decorate a regular function
    # or a generator function (then it returns a generator function)

    @with_result_progress
    def func(l):
        return l

    generated = []
    @with_result_progress
    def gen(l):
        for i in l:
            generated.append(i)
            yield i

    recs = [{'status': 'ok', 'unrelated': i} for i in range(2)]
    # still works for a func and returns provided list
    ok_(not inspect.isgeneratorfunction(func))
    assert_equal(func(recs), recs)

    # generator should still yield and next iteration should only happen
    # when requested
    ok_(inspect.isgeneratorfunction(gen))
    g = gen(recs)

    ok_generator(g)
    assert_equal(generated, [])  # nothing yet
    assert_equal(next(g), recs[0])
    assert_equal(generated, recs[:1])
    assert_equal(next(g), recs[1])
    assert_equal(generated, recs)

    # just to make sure all good to redo
    assert_equal(list(gen(recs)), recs)


def test_with_progress_generator():
    # Well, we could also pass an iterable directly now and display
    # progress iterative over it
    g = with_progress(range(3))
    ok_generator(g)
    assert_equal(list(g), list(range(3)))
