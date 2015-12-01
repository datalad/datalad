# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Basic dialog-like interface for interactions in the terminal window

"""

__docformat__ = 'restructuredtext'

import sys
from getpass import getpass

from ..utils import auto_repr
from .base import InteractiveUI

# Example APIs which might be useful to look for "inspiration"
#  man debconf-devel
#  man zenity
#
# "Fancy" output of progress etc in the terminal:
# - docker has multiple simultaneous progressbars.  Apparently "navigation"
#   is obtained with escape characters in the terminal.
#   see docker/pkg/jsonmessage/jsonmessage.go or following snippet
"""
from time import sleep
import sys

out = sys.stderr
for i in xrange(10):
  diff = 2
  if i:
      out.write("%c[%dA" % (27, diff))
  out.write("%d\n%d\n" % (i, i ** 2))
  sleep(0.5)
"""
# They also use JSON representation for the message which might provide a nice abstraction
# Other useful codes
#         // <ESC>[2K = erase entire current line
#        fmt.Fprintf(out, "%c[2K\r", 27)
# and code in docker: pkg/progressreader/progressreader.go pkg/streamformatter/streamformatter.go
#
# reference for ESC codes: http://ascii-table.com/ansi-escape-sequences.php

@auto_repr
class ConsoleLog(object):

    def __init__(self, out=sys.stdout):
        self.out = out

    def message(self, msg, cr=True):
        self.out.write(msg)
        if cr:
            self.out.write('\n')

    def error(self, error):
        self.out.write("ERROR: %s\n" % error)


@auto_repr
class DialogUI(ConsoleLog, InteractiveUI):

    def question(self, text,
                 title=None, choices=None,
                 default=None,
                 hidden=False):
        # Do initial checks first
        if default and default not in choices:
            raise ValueError("default value %r is not among choices: %s"
                             % (default, choices))
        if title:
            self.out.write(title + "\n")

        def mark_default(x):
            return "[%s]" % x \
                if default is not None and x == default \
                else x

        if choices is not None:
            msg = "%s (choices: %s)" % (text, ', '.join(map(mark_default, choices)))
        else:
            msg = text

        attempt = 0
        while True:
            attempt += 1
            if attempt >= 100:
                raise RuntimeError("This is 100th attempt. Something really went wrong")

            self.out.write(msg + ": ")
            self.out.flush()

            # TODO: raw_input works only if stdin was not controlled by
            # (e.g. if coming from annex).  So we might need to do the
            # same trick as get_pass() does while directly dealing with /dev/pty
            # and provide per-OS handling with stdin being override
            response = raw_input() if not hidden else getpass('')

            if not response and default:
                response = default
                break

            if choices and response not in choices:
                self.error("%r is not among choices: %s. Repeat your answer"
                           % (response, choices))
                continue
            break
        return response