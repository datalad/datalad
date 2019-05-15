# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Definitions for ansi colors etc"""

import os
from .. import cfg
from ..ui import ui

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(30, 38)
BOLD = 1
UNDERLINE = 4

RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

LOG_LEVEL_COLORS = {
    'WARNING': YELLOW,
    'INFO': None,
    'DEBUG': BLUE,
    'CRITICAL': YELLOW,
    'ERROR': RED
}

RESULT_STATUS_COLORS = {
    'ok': GREEN,
    'notneeded': GREEN,
    'impossible': YELLOW,
    'error': RED
}

# Aliases for uniform presentation

DATASET = UNDERLINE
FIELD = BOLD


def color_enabled():
    """Check for whether color output is enabled

    Color is only enabled if the terminal is interactive.
    If the datalad.ui.color configuration setting is 'on' or 'off', then
    respect that.
    If the datalad.ui.color setting is 'auto' (default), then color is
    enabled unless the environment variable NO_COLOR is defined.

    Returns
    -------
    bool
    """
    if not ui.is_interactive:
        return False

    ui_color = cfg.obtain('datalad.ui.color')
    if ui_color == 'off':
        return False

    return ui_color == 'on' or os.getenv('NO_COLOR') is None


def format_msg(fmt, use_color=False):
    """Replace $RESET and $BOLD with corresponding ANSI entries"""
    if color_enabled() and use_color:
        return fmt.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
    else:
        return fmt.replace("$RESET", "").replace("$BOLD", "")


def color_word(s, color, force=False):
    """Color `s` with `color`.

    Parameters
    ----------
    s : string
    color : int
        Code for color. If the value evaluates to false, the string will not be
        colored.
    force : boolean, optional
        Color string even when non-interactive session is detected.

    Returns
    -------
    str
    """
    if color and (force or color_enabled()):
        return "%s%s%s" % (COLOR_SEQ % color, s, RESET_SEQ)
    return s


def color_status(status):
    return color_word(status, RESULT_STATUS_COLORS.get(status))
