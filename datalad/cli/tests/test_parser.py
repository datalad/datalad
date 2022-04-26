"""Tests for parser components"""

__docformat__ = 'restructuredtext'

from io import StringIO
from unittest.mock import patch

from datalad.tests.utils_pytest import (
    assert_equal,
    assert_in,
    assert_raises,
)

from ..parser import (
    fail_with_short_help,
    setup_parser,
)


def test_fail_with_short_help():
    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(exit_code=3, out=out)
    assert_equal(cme.value.code, 3)
    assert_equal(out.getvalue(), "")

    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(msg="Failed badly", out=out)
    assert_equal(cme.value.code, 1)
    assert_equal(out.getvalue(), "error: Failed badly\n")

    # Suggestions, hint, etc
    out = StringIO()
    with assert_raises(SystemExit) as cme:
        fail_with_short_help(
            msg="Failed badly",
            known=["mother", "mutter", "father", "son"],
            provided="muther",
            hint="You can become one",
            exit_code=0,  # no one forbids
            what="parent",
            out=out)
    assert_equal(cme.value.code, 0)
    assert_equal(out.getvalue(),
                 "error: Failed badly\n"
                 "datalad: Unknown parent 'muther'.  See 'datalad --help'.\n\n"
                 "Did you mean any of these?\n"
                 "        mutter\n"
                 "        mother\n"
                 "        father\n"
                 "Hint: You can become one\n")


def check_setup_parser(args, exit_code=None):
    parser = None
    with patch('sys.stderr', new_callable=StringIO) as cmerr:
        with patch('sys.stdout', new_callable=StringIO) as cmout:
            if exit_code is not None:
                with assert_raises(SystemExit) as cm:
                    setup_parser(args)
            else:
                parser = setup_parser(args)
    if exit_code is not None:
        assert_equal(cm.value.code, exit_code)
    stdout = cmout.getvalue()
    stderr = cmerr.getvalue()
    return {'parser': parser, 'out': stdout, 'err': stderr}


def test_setup():
    # insufficient arguments
    check_setup_parser([], 2)
    assert_in('too few arguments', check_setup_parser(['datalad'], 2)['err'])
    assert_in('.', check_setup_parser(['datalad', '--version'], 0)['out'])
    parser = check_setup_parser(['datalad', 'wtf'])['parser']
    # check into the guts of argparse to check that really only a single
    # subparser was constructed
    assert_equal(
        list(parser._positionals._group_actions[0].choices.keys()),
        ['wtf']
    )
