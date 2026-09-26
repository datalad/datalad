import sys
from http.client import IncompleteRead
from unittest.mock import patch

import pytest

from datalad import cfg
from datalad.support.exceptions import (
    CapturedException,
    _exception_message,
    format_exception_with_cause,
)
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_re_in,
    assert_true,
)


def test_CapturedException():

    try:
        raise Exception("BOOM")
    except Exception as e:
        captured_exc = CapturedException(e)

    assert_re_in(r"BOOM \[test_captured_exception.py:test_CapturedException:[0-9]+\]", captured_exc.format_oneline_tb())
    assert_re_in(r"^\[.*\]", captured_exc.format_oneline_tb(include_str=False))  # only traceback

    try:
        raise NotImplementedError
    except Exception as e:
        captured_exc = CapturedException(e)

    assert_re_in(r"NotImplementedError \[test_captured_exception.py:test_CapturedException:[0-9]+\]", captured_exc.format_oneline_tb())

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

    assert_re_in(r"new message -caused by- my bad again \[test_captured_exception.py:test_CapturedException:[0-9]+,test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f2:[0-9]+\]", estr_full)
    assert_re_in(r"new message -caused by- my bad again \[test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f2:[0-9]+\]", estr3)
    assert_re_in(r"new message -caused by- my bad again \[test_captured_exception.py:f:[0-9]+,test_captured_exception.py:f2:[0-9]+\]", estr2)
    assert_re_in(r"new message -caused by- my bad again \[test_captured_exception.py:f2:[0-9]+\]", estr1)
    # default: no limit:
    assert_equal(estr_, estr_full)

    # standard output
    full_display = captured_exc.format_standard().splitlines()

    assert_equal(full_display[0], "Traceback (most recent call last):")
    # points in f and f2 for first exception with two lines each
    # (where is the line and what reads the line):
    assert full_display[1].lstrip().startswith("File")
    assert full_display[2].strip() == "f2()"
    inc = int(sys.version_info >= (3, 13))
    assert full_display[3 + inc].lstrip().startswith("File")
    assert full_display[4 + inc].strip() == "raise Exception(\"my bad again\")"
    assert full_display[5 + inc].strip() == "Exception: my bad again"
    assert full_display[7 + inc].strip() == "The above exception was the direct cause of the following exception:"
    assert full_display[9 + inc] == "Traceback (most recent call last):"
    # ...
    assert full_display[-1].strip() == "RuntimeError: new message"

    # CapturedException.__repr__:
    assert_re_in(r".*test_captured_exception.py:f2:[0-9]+\]$",
                 captured_exc.__repr__())


def makeitraise():
    def raise_valueerror():
        try:
            raise_runtimeerror()
        except Exception as e:
            raise ValueError from e

    def raise_runtimeerror():
        raise RuntimeError("Mike")

    try:
        raise_valueerror()
    except Exception as e:
        raise RuntimeError from e


def test_format_exception_with_cause():
    try:
        makeitraise()
    except Exception as e:
        assert_equal(
            format_exception_with_cause(e),
            'RuntimeError -caused by- ValueError -caused by- Mike')
        # make sure it also works with TracebackException/CapturedException:
        ce = CapturedException(e)
        assert_equal(
            ce.format_with_cause(),
            'RuntimeError -caused by- ValueError -caused by- Mike')


_RESET = ConnectionResetError(104, 'Connection reset by peer')


@pytest.mark.ai_generated
@pytest.mark.parametrize('chain, expected', [
    # a cause its wrapper already rendered, the way urllib3 reports a broken
    # connection, is not spelled out a second time
    ([RuntimeError("Connection broken: %r" % ValueError("no more data")),
      ValueError("no more data")],
     "Connection broken: ValueError('no more data')"),
    ([RuntimeError("Connection broken: %r" % IncompleteRead(b'a', 2)),
      IncompleteRead(b'a', 2)],
     "Connection broken: IncompleteRead(1 bytes read, 2 more expected)"),
    ([RuntimeError("Connection broken: %r" % _RESET, _RESET), _RESET],
     "Connection broken: ConnectionResetError(104, 'Connection reset by peer')"),
    # ... but only that one: its own cause is still reported
    ([RuntimeError("step failed: %r" % ValueError("write failed")),
      ValueError("write failed"), OSError(28, "No space left on device")],
     "step failed: ValueError('write failed') "
     "-caused by- [Errno 28] No space left on device"),
    # sharing a word, or a type name without a message, is not a rendering
    ([RuntimeError("the connection failed"), _RESET],
     "the connection failed -caused by- [Errno 104] Connection reset by peer"),
    ([RuntimeError("hit a timeout while reading"), OSError("timeout")],
     "hit a timeout while reading -caused by- timeout"),
    ([RuntimeError("could not parse the ValueError log"), ValueError()],
     "could not parse the ValueError log -caused by- ValueError"),
])
def test_format_exception_with_cause_skips_rendered_causes(chain, expected):
    for e, cause in zip(chain, chain[1:]):
        e.__cause__ = cause
    assert_equal(format_exception_with_cause(chain[0]), expected)
    assert_equal(CapturedException(chain[0]).format_with_cause(), expected)
    message, sep, causes = expected.partition(' -caused by- ')
    assert_equal(CapturedException(chain[0]).format_short(),
                 f'RuntimeError({message}){sep}{causes}')


@pytest.mark.ai_generated
def test_format_exception_with_cause_cycle():
    a, b = RuntimeError("a"), RuntimeError("b")
    a.__cause__, b.__cause__ = b, a
    assert_equal(format_exception_with_cause(a), "a -caused by- b")
    a.__cause__ = a
    assert_equal(CapturedException(a).format_short(), "RuntimeError(a)")


class _VerbatimStr(Exception):
    def __str__(self):
        return self.args[0]


@pytest.mark.ai_generated
@pytest.mark.parametrize('exc, expected', [
    (Exception("Connection broken: %r" % _RESET, _RESET),
     "Connection broken: ConnectionResetError(104, 'Connection reset by peer')"),
    (Exception("""he said "hi" and 'bye'""", ValueError()),
     """he said "hi" and 'bye'"""),
    # anything else is left as is
    (Exception('a', 'b'), "('a', 'b')"),
    (Exception('a', 'b('), "('a', 'b(')"),
    (Exception('', ValueError('y')), "('', ValueError('y'))"),
    (Exception("(abc)"), "(abc)"),
    (Exception("('abc)"), "('abc)"),
    (_VerbatimStr(r"('\x', ValueError('y'))"), r"('\x', ValueError('y'))"),
    (OSError(28, "No space left on device"),
     "[Errno 28] No space left on device"),
    (ValueError(), ""),
])
def test_exception_message(exc, expected):
    assert_equal(_exception_message(exc), expected)
