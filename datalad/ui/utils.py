# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Various utils oriented to UI"""

import fcntl
import termios
import struct


# origin http://stackoverflow.com/a/3010495/1265472
def get_terminal_size():
    """Return current terminal size"""
    try:
        h, w, hp, wp = struct.unpack(
            'HHHH',
            fcntl.ioctl(0, termios.TIOCGWINSZ,
            struct.pack('HHHH', 0, 0, 0, 0))
        )
        return w, h
    except:
        return None, None