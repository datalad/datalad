from unittest.mock import patch
from nose.tools import assert_equal, assert_true
from datalad.support.exceptions import CapturedException
from datalad.tests.utils import assert_re_in
from datalad import cfg


def test_CapturedException():

    try:
        raise Exception("BOOM")
    except Exception as e:
        captured_exc = CapturedException(e)

    assert_re_in("BOOM \[test_captured_exception.py:test_CapturedException:[0-9]+\]", captured_exc.format_oneline_tb())
    assert_re_in("^\[.*\]", captured_exc.format_oneline_tb(include_str=False))  # only traceback

    try:
        raise NotImplementedError
    except Exception as e:
        captured_exc = CapturedException(e)

    assert_re_in("NotImplementedError \[test_captured_exception.py:test_CapturedException:[0-9]+\]", captured_exc.format_oneline_tb())

    def f():
        def f2():
            raise Exception("my bad again")
        try:
            f2()
        except Exception as e:
            # exception chain
            raise RuntimeError("new message") from e

    try:
        f()
    except Exception as e:
        captured_exc = CapturedException(e)

    # default limit: one level:
    estr1 = captured_exc.format_oneline_tb(limit=1)
    estr2 = captured_exc.format_oneline_tb(limit=2)
    # and we can control it via environ/config by default
    try:
        with patch.dict('os.environ', {'DATALAD_EXC_STR_TBLIMIT': '3'}):
            cfg.reload()
            estr3 = captured_exc.format_oneline_tb()
        with patch.dict('os.environ', {}, clear=True):
            cfg.reload()
            estr_ = captured_exc.format_oneline_tb()
    finally:
        cfg.reload()  # make sure we don't have a side effect on other tests

    estr_full = captured_exc.format_oneline_tb(10)

    assert_re_in("new message \[test_captured_exception.py:test_CapturedException:[0-9]+,test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f2:[0-9]+\]", estr_full)
    assert_re_in("new message \[test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f2:[0-9]+\]", estr3)
    assert_re_in("new message \[test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f2:[0-9]+\]", estr2)
    assert_re_in("new message \[test_captured_exception.py:f2:[0-9]+\]", estr1)
    # default: no limit:
    assert_equal(estr_, estr_full)

    # standard output
    full_display = captured_exc.format_standard().splitlines()

    assert_equal(full_display[0], "Traceback (most recent call last):")
    # points in f and f2 for first exception with two lines each
    # (where is the line and what reads the line):
    assert_true(full_display[1].lstrip().startswith("File"))
    assert_equal(full_display[2].strip(), "f2()")
    assert_true(full_display[3].lstrip().startswith("File"))
    assert_equal(full_display[4].strip(), "raise Exception(\"my bad again\")")
    assert_equal(full_display[5].strip(), "Exception: my bad again")
    assert_equal(full_display[7].strip(), "The above exception was the direct cause of the following exception:")
    assert_equal(full_display[9], "Traceback (most recent call last):")
    # ...
    assert_equal(full_display[-1].strip(), "RuntimeError: new message")

    # CapturedException.__repr__:
    assert_re_in(r".*test_captured_exception.py:f2:[0-9]+\]$",
                 captured_exc.__repr__())
