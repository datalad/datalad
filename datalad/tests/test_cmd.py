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

import unittest.mock

from datalad.cmd import readline_rstripped


def test_readline_rstripped_deprecation():
    with unittest.mock.patch("datalad.cmd.warnings.warn") as warn_mock:
        class StdoutMock:
            def readline(self):
                return "abc\n"
        readline_rstripped(StdoutMock())
        warn_mock.assert_called_once()
