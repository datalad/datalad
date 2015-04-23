# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the testkraut package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
This is Testkraut's unit test interface to serve the local SPECs within
the unit tests battery as actual test cases.
"""

import os
import logging
import os.path as op

from .utils import on_windows

if 'TESTKRAUT_LOGGER_VERBOSE' in os.environ:
    lgr = logging.getLogger('testkraut')
    console = logging.StreamHandler()
    lgr.addHandler(console)
    cfg = os.environ['TESTKRAUT_LOGGER_VERBOSE']
    if cfg == 'debug':
        lgr.setLevel(logging.DEBUG)
    else:
        lgr.setLevel(logging.INFO)

from testkraut.testcase import generate_testkraut_tests

if not on_windows:
    # TODO: there is no easy logic available to seamlessly test annex in both
    # original (e.g. on Linux/OSX) and Direct (Windows) modes.  So for now disabled.
    # 
    local_test_cases = generate_testkraut_tests(
        [os.path.join(os.path.dirname(__file__), 'data')],
        [op.join(op.dirname(__file__), 'testspecs')])
