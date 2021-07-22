# -*- coding: utf-8 -*-
"""Pygments lexer for text containing ANSI color codes."""
from __future__ import absolute_import
from __future__ import unicode_literals

import itertools
import re

import pygments.lexer
import pygments.token


Color = pygments.token.Token.Color

_ansi_code_to_color = {
    0: 'Black',
    1: 'Red',
    2: 'Green',
    3: 'Yellow',
    4: 'Blue',
    5: 'Magenta',
    6: 'Cyan',
    7: 'White',
}


def _token_from_lexer_state(bold, fg_color, bg_color):
    """Construct a token given the current lexer state.

    We can only emit one token even though we have a multiple-tuple state.
    To do work around this, we construct tokens like "BoldRed".
    """
    token_name = ''

    if bold:
        token_name += 'Bold'

    if fg_color:
        token_name += fg_color

    if bg_color:
        token_name += 'BG' + bg_color

    if token_name == '':
        return pygments.token.Text
    else:
        return getattr(Color, token_name)


def color_tokens(fg_colors, bg_colors):
    """Return color tokens for a given set of colors.

    Pygments doesn't have a generic "color" token; instead everything is
    contextual (e.g. "comment" or "variable"). That doesn't make sense for us,
    where the colors actually *are* what we care about.

    This function will register combinations of tokens (things like "Red" or
    "BoldRedBGGreen") based on the colors passed in.

    You can also define the tokens yourself, but note that the token names are
    *not* currently guaranteed to be stable between releases as I'm not really
    happy with this approach.

    Usage:

        fg_colors = bg_colors = {
            'Black': '#000000',
            'Red': '#EF2929',
            'Green': '#8AE234',
            'Yellow': '#FCE94F',
            'Blue': '#3465A4',
            'Magenta': '#c509c5',
            'Cyan': '#34E2E2',
            'White': '#ffffff',
        }
        class MyStyle(pygments.styles.SomeStyle):
            styles = dict(pygments.styles.SomeStyle.styles)
            styles.update(color_tokens(fg_colors, bg_colors))
    """
    styles = {}

    for bold, fg_color, bg_color in itertools.product(
            (False, True),
            {None} | set(fg_colors),
            {None} | set(bg_colors),
    ):
        token = _token_from_lexer_state(bold, fg_color, bg_color)
        if token is not pygments.token.Text:
            value = []
            if bold:
                value.append('bold')
            if fg_color:
                value.append(fg_colors[fg_color])
            if bg_color:
                value.append('bg:' + bg_colors[bg_color])
            styles[token] = ' '.join(value)

    return styles


class AnsiColorLexer(pygments.lexer.RegexLexer):
    name = 'ANSI Color'
    aliases = ('ansi-color', 'ansi', 'ansi-terminal')
    flags = re.DOTALL | re.MULTILINE

    def __init__(self, *args, **kwargs):
        super(AnsiColorLexer, self).__init__(*args, **kwargs)
        self.reset_state()

    def reset_state(self):
        self.bold = False
        self.fg_color = None
        self.bg_color = None

    @property
    def current_token(self):
        return _token_from_lexer_state(
            self.bold, self.fg_color, self.bg_color,
        )

    def process(self, match):
        """Produce the next token and bit of text.

        Interprets the ANSI code (which may be a color code or some other
        code), changing the lexer state and producing a new token. If it's not
        a color code, we just strip it out and move on.

        Some useful reference for ANSI codes:
          * http://ascii-table.com/ansi-escape-sequences.php
        """
        # "after_escape" contains everything after the start of the escape
        # sequence, up to the next escape sequence. We still need to separate
        # the content from the end of the escape sequence.
        after_escape = match.group(1)

        # TODO: this doesn't handle the case where the values are non-numeric.
        # This is rare but can happen for keyboard remapping, e.g.
        # '\x1b[0;59;"A"p'
        parsed = re.match(
            r'([0-9;=]*?)?([a-zA-Z])(.*)$',
            after_escape,
            re.DOTALL | re.MULTILINE,
        )
        if parsed is None:
            # This shouldn't ever happen if we're given valid text + ANSI, but
            # people can provide us with utter junk, and we should tolerate it.
            text = after_escape
        else:
            value, code, text = parsed.groups()

            if code == 'm':  # "m" is "Set Graphics Mode"
                # Special case \x1b[m is a reset code
                if value == '':
                    self.reset_state()
                else:
                    values = value.split(';')
                    for value in values:
                        try:
                            value = int(value)
                        except ValueError:
                            # Shouldn't ever happen, but could with invalid
                            # ANSI.
                            continue
                        else:
                            fg_color = _ansi_code_to_color.get(value - 30)
                            bg_color = _ansi_code_to_color.get(value - 40)
                            if fg_color:
                                self.fg_color = fg_color
                            elif bg_color:
                                self.bg_color = bg_color
                            elif value == 1:
                                self.bold = True
                            elif value == 22:
                                self.bold = False
                            elif value == 39:
                                self.fg_color = None
                            elif value == 49:
                                self.bg_color = None
                            elif value == 0:
                                self.reset_state()

        yield match.start(), self.current_token, text

    tokens = {
        # states have to be native strings
        str('root'): [
            (r'\x1b\[([^\x1b]*)', process),
            (r'[^\x1b]+', pygments.token.Text),
        ],
    }
