# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Various utils oriented to UI"""

from datalad.support import ansi_colors
from datalad.utils import on_windows
import struct


# origin http://stackoverflow.com/a/3010495/1265472
def get_terminal_size():
    """Return current terminal size"""
    if on_windows:
        try:
            from ctypes import windll, create_string_buffer

            # stdin handle is -10
            # stdout handle is -11
            # stderr handle is -12

            h = windll.kernel32.GetStdHandle(-12)
            csbi = create_string_buffer(22)
            res = windll.kernel32.GetConsoleScreenBufferInfo(h, csbi)
        except:
            return None, None
        if res:
            (bufx, bufy, curx, cury, wattr,
             left, top, right, bottom, maxx, maxy) = struct.unpack("hhhhHhhhhhh", csbi.raw)
            sizex = right - left + 1
            sizey = bottom - top + 1
            return sizex, sizey
        else:
            return None, None
    else:
        import fcntl
        import termios
        try:
            h, w, hp, wp = struct.unpack(
                'HHHH',
                fcntl.ioctl(0, termios.TIOCGWINSZ,
                            struct.pack('HHHH', 0, 0, 0, 0))
            )
            return w, h
        except:
            return None, None


def get_console_width(default_min=20):
    """Return console width to use

    In some cases shutil reports it to be 0, so we cannot rely on it
    alone
    """
    console_width = get_terminal_size()[0] or 0
    # it might still be 0, e.g. in conda builds for 0.10.0
    if console_width <= 0:
        console_width = 80
    elif console_width <= 20:
        # or some other too small to be real number,
        # to prevent crashes below guarantee that it is at least 20
        console_width = 20
    return console_width


def show_hint(msg):
    from datalad.ui import ui
    ui.message("{}".format(
            ansi_colors.color_word(
                msg,
                ansi_colors.YELLOW)))