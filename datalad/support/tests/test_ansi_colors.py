# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test ANSI color tools """

import os
import pytest
from unittest.mock import patch

from datalad.support import ansi_colors as colors
from datalad.tests.utils_pytest import (
    assert_equal,
    patch_config,
)
import datalad.utils as du


@pytest.mark.filterwarnings(r"ignore::DeprecationWarning")
def test_color_enabled():
    # In the absence of NO_COLOR, follow ui.color, or ui.is_interactive if 'auto'
    with patch.dict(os.environ), \
         patch('datalad.utils.is_interactive'):
        os.environ.pop('NO_COLOR', None)
        for is_interactive in (True, False):
            du.is_interactive = lambda: is_interactive
            with patch_config({'datalad.ui.color': 'off'}):
                assert_equal(colors.color_enabled(), False)
            with patch_config({'datalad.ui.color': 'on'}):
                assert_equal(colors.color_enabled(), True)
            with patch_config({'datalad.ui.color': 'auto'}):
                assert_equal(colors.color_enabled(), is_interactive)

    # In the presence of NO_COLOR, default to disable, unless ui.color is "on"
    # The value of NO_COLOR should have no effect, so try true-ish and false-ish values
    for NO_COLOR in ("", "1", "0"):
        with patch.dict(os.environ, {'NO_COLOR': NO_COLOR}), \
             patch('datalad.utils.is_interactive'):
            for is_interactive in (True, False):
                du.is_interactive = lambda: is_interactive
                with patch_config({'datalad.ui.color': 'on'}):
                    assert_equal(colors.color_enabled(), True)
                for ui_color in ('off', 'auto'):
                    with patch_config({'datalad.ui.color': ui_color}):
                        assert_equal(colors.color_enabled(), False)

#
# In all other tests, just patch color_enabled
#

@pytest.mark.filterwarnings(r"ignore::DeprecationWarning")
def test_format_msg():
    fmt = r'a$BOLDb$RESETc$BOLDd$RESETe'
    for enabled in (True, False):
        with patch('datalad.support.ansi_colors.AnsiFormatter.is_enabled', enabled):
            assert_equal(colors.format_msg(fmt), 'abcde')
            assert_equal(colors.format_msg(fmt, use_color=False), 'abcde')

    with patch('datalad.support.ansi_colors.AnsiFormatter.is_enabled', False):
        for use_color in (True, False):
            assert_equal(colors.format_msg(fmt), 'abcde')
            assert_equal(colors.format_msg(fmt, use_color=use_color), 'abcde')

    with patch('datalad.support.ansi_colors.AnsiFormatter.is_enabled', True):
        assert_equal(colors.format_msg(fmt, use_color=True), 'a\033[1mb\033[0mc\033[1md\033[0me')


@pytest.mark.filterwarnings(r"ignore::DeprecationWarning")
def test_color_word():
    s = 'word'
    green_s = '\033[1;32mword\033[0m'
    for enabled in (True, False):
        with patch('datalad.support.ansi_colors.AnsiFormatter.is_enabled', enabled):
            assert_equal(colors.color_word(s, colors.GREEN, force=True), green_s)

    with patch('datalad.support.ansi_colors.AnsiFormatter.is_enabled', True):
        assert_equal(colors.color_word(s, colors.GREEN), green_s)
        assert_equal(colors.color_word(s, colors.GREEN, force=False), green_s)

    with patch('datalad.support.ansi_colors.AnsiFormatter.is_enabled', False):
        assert_equal(colors.color_word(s, colors.GREEN), s)
        assert_equal(colors.color_word(s, colors.GREEN, force=False), s)


@pytest.mark.filterwarnings(r"ignore::DeprecationWarning")
def test_color_status():
    # status -> (plain, colored)
    statuses = {
        'ok': ('ok', '\033[1;32mok\033[0m'),
        'notneeded': ('notneeded', '\033[1;32mnotneeded\033[0m'),
        'impossible': ('impossible', '\033[1;33mimpossible\033[0m'),
        'error': ('error', '\033[1;31merror\033[0m'),
        'invalid': ('invalid', 'invalid'),
        }

    for enabled in (True, False):
        with patch('datalad.support.ansi_colors.AnsiFormatter.is_enabled', enabled):
            for status, retopts in statuses.items():
                assert_equal(colors.color_status(status), retopts[enabled])
