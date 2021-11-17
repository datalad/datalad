# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test WitlessRunner
"""
import sys
import unittest.mock

from datalad.tests.utils import assert_equal

from datalad.cmd import (
    readline_rstripped,
    BatchedCommand,
)


def test_readline_rstripped_deprecation():
    with unittest.mock.patch("datalad.cmd.warnings.warn") as warn_mock:
        class StdoutMock:
            def readline(self):
                return "abc\n"
        readline_rstripped(StdoutMock())
        warn_mock.assert_called_once()


def test_batched_command():
    bc = BatchedCommand(cmd=[sys.executable, "-i", "-u", "-q", "-"])
    response = bc("print('a')")
    assert_equal(response, "a")
    response = bc("print(2 + 1)")
    assert_equal(response, "3")
    stderr = bc.close(return_stderr=True)
    assert_equal(stderr.strip(), ">>> >>> >>>")
