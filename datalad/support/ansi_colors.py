# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Definitions for ansi colors etc"""

from ..ui import ui

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(30, 38)
BOLD = 1
UNDERLINE = 4

RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

LOG_LEVEL_COLORS = {
    'WARNING': YELLOW,
    'INFO': WHITE,
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


def format_msg(fmt, use_color=False):
    """Replace $RESET and $BOLD with corresponding ANSI entries"""
    if use_color:
        return fmt.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
    else:
        return fmt.replace("$RESET", "").replace("$BOLD", "")


def color_word(s, color):
    return "%s%s%s" % (COLOR_SEQ % color, s, RESET_SEQ) \
        if ui.is_interactive \
        else s


def color_status(status):
    col = RESULT_STATUS_COLORS.get(status, None)
    return color_word(status, col) if col else status
