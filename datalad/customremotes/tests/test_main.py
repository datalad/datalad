# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the "main" driver of the special remotes"""

import logging
import os

from ..main import main

from ..base import AnnexCustomRemote

from datalad.tests.utils_pytest import (
    swallow_logs,
    swallow_outputs,
)

import pytest


def test_erroring_out():
    class TooAbstract(AnnexCustomRemote):
        pass

    with swallow_logs(new_level=logging.DEBUG) as cml, \
        swallow_outputs() as cmo:
        with pytest.raises(SystemExit) as cme:
            main(args=[], cls=TooAbstract)
        assert cme.value.code == 1
        assert 'passing ERROR to git-annex' in cml.out
        # verify basic correct formatting of string to git-annex
        assert cmo.out.startswith('ERROR ')
        assert os.linesep not in cmo.out.rstrip()
        assert cmo.out.endswith('\n')  # This is the case even on Windows.
