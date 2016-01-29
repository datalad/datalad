# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the universal datalad's annex customremote"""

from ...support.handlerepo import HandleRepo
from ...consts import DATALAD_SPECIAL_REMOTE
from ...tests.utils import *
from . import _get_custom_runner


@with_tempfile()
def check_basic_scenario(direct, d):
    handle = HandleRepo(d, runner=_get_custom_runner(d), direct=direct)
    handle.annex_initremote(
        DATALAD_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=%s' % DATALAD_SPECIAL_REMOTE,
         'autoenable=true'])


def test_basic_scenario():
    yield check_basic_scenario, False
    if not on_windows:
        yield check_basic_scenario, True
