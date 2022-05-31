# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper for formatting text with ANSI color macros

This code is fully self-contained, except for an auto-detection of
when to actually perform coloring, which is uses
datalad.utils.is_interactive() as a minimum criterion.
"""

from enum import Enum


class AnsiColors(Enum):
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    # the following are BOLD + a color
    BLACK = '\033[1;30m'
    RED = '\033[1;31m'
    GREEN = '\033[1;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[1;34m'
    MAGENTA = '\033[1;35m'
    CYAN = '\033[1;36m'
    WHITE = '\033[1;37m'


LOG_LEVEL_COLORS = {
    'WARNING': AnsiColors.YELLOW,
    'INFO': None,
    'DEBUG': AnsiColors.BLUE,
    'CRITICAL': AnsiColors.YELLOW,
    'ERROR': AnsiColors.RED
}

RESULT_STATUS_COLORS = {
    'ok': AnsiColors.GREEN,
    'notneeded': AnsiColors.GREEN,
    'impossible': AnsiColors.YELLOW,
    'error': AnsiColors.RED
}


class AnsiFormatter:
    def __init__(self):
        self._enabled = None

    # convenience access
    color = AnsiColors

    _RESET_SEQ = "\033[0m"

    @property
    def is_enabled(self):
        """Check for whether color output is enabled

        If the configuration value ``datalad.ui.color`` is ``'on'`` or ``'off'``,
        that takes precedence.
        If ``datalad.ui.color`` is ``'auto'``, and the environment variable
        ``NO_COLOR`` is defined (see https://no-color.org), then color is disabled.
        Otherwise, enable colors if a TTY is detected by ``datalad.ui.ui.is_interactive``.

        Returns
        -------
        bool
        """
        if self._enabled is None:
            from datalad import cfg
            ui_color = cfg.obtain('datalad.ui.color')
            if ui_color in ('on', 'yes'):
                self._enabled = True
            elif ui_color == ('off', 'no'):
                self._enabled = False
            else:
                import os
                from datalad.utils import is_interactive
                self._enabled = ui_color == 'auto' \
                    and os.getenv('NO_COLOR') is None \
                    and is_interactive()
        return self._enabled

    def colorize(self, text, code):
        if code is None or not self.is_enabled:
            # nothing to do
            return text

        elif isinstance(code, AnsiColors):
            seq = code.value
        else:
            seq = AnsiColors[code].value
        return f"{seq}{text}{AnsiFormatter._RESET_SEQ}"

    def color_status(self, status):
        return self.colorize(status, RESULT_STATUS_COLORS.get(status))

    def format(self, fmt, use_color=False):
        """Replace $RESET and $BOLD with corresponding ANSI entries"""
        # TODO this could replace much more placeholders. There could be
        # $MAGENTA and all that, to largely avoid the use of `color_word()`
        if use_color and self.is_enabled:
            return fmt.replace(
                "$RESET", AnsiFormatter._RESET_SEQ).replace(
                "$BOLD", AnsiColors.BOLD.value)
        else:
            return fmt.replace(
                "$RESET", "").replace(
                "$BOLD", "")


formatter = AnsiFormatter()


#
# Legacy API
#

import warnings

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(30, 38)
BOLD = 1
UNDERLINE = 4

RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

DATASET = UNDERLINE
FIELD = BOLD


def color_enabled():
    warnings.warn('color_enabled() is deprecated, use AnsiFormatter',
                  DeprecationWarning)
    return AnsiFormatter().is_enabled


def format_msg(fmt, use_color=False):
    """Replace $RESET and $BOLD with corresponding ANSI entries

    .. deprecated:: 0.17
       Use AnsiFormatter.format() instead.
    """
    warnings.warn('format_msg() is deprecated, use AnsiFormatter.format()',
                  DeprecationWarning)
    return AnsiFormatter().format(fmt, use_color=use_color)


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

    .. deprecated:: 0.17
       Use AnsiFormatter.colorize() instead.
    """
    warnings.warn('color_word() is deprecated, use AnsiFormatter.colorize()',
                  DeprecationWarning)
    if not color:
        return s

    f = AnsiFormatter()
    # new API wants AnsiColors, recode via enum
    color = f.color(COLOR_SEQ % color)
    if force:
        f.is_enabled = True
    return f.colorize(s, color)


def color_status(status):
    """
    .. deprecated:: 0.17
       Use AnsiFormatter.color_status() instead.
    """
    warnings.warn(
        'color_status() is deprecated, use AnsiFormatter.color_status()',
        DeprecationWarning)
    return formatter.color_status(status)
