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

import os
import sys
from six import PY2
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
for i in range(10):
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

from progressbar import Bar, ETA, FileTransferSpeed, \
    Percentage, ProgressBar, RotatingMarker

# TODO: might better delegate to an arbitrary bar?
class BarWithFillText(Bar):
    """A progress bar widget which fills the bar with the target text"""

    def __init__(self, fill_text, **kwargs):
        super(BarWithFillText, self).__init__(**kwargs)
        self.fill_text = fill_text

    def update(self, pbar, width):
        orig = super(BarWithFillText, self).update(pbar, width)
        # replace beginning with the title
        if len(self.fill_text) > width:
            # TODO:  make it fancier! That we also at the same time scroll it from
            # the left so it does end up at the end with the tail but starts with
            # the beginning
            fill_text = '...' + self.fill_text[-(width-4):]
        else:
            fill_text = self.fill_text
        fill_text = fill_text[:min(len(fill_text), int(round(width * pbar.percentage()/100.)))]
        return fill_text + " " + orig[len(fill_text)+1:]


@auto_repr
class ConsoleLog(object):

    def __init__(self, out=sys.stdout):
        self.out = out

    def message(self, msg, cr='\n'):
        self.out.write(msg)
        if cr:
            self.out.write(cr)

    def error(self, error):
        self.out.write("ERROR: %s\n" % error)

    def get_progressbar(self, label='', fill_text=None, currval=None, maxval=None):
        """'Inspired' by progressbar module interface

        Should return an object with .update(), and .finish()
        methods, and maxval, currval attributes
        """
        bar = dict(marker=RotatingMarker())
        # TODO: RF entire messaging to be able to support multiple progressbars at once
        widgets = ['%s: ' % label,
                   BarWithFillText(fill_text=fill_text, marker=RotatingMarker()), ' ',
                   Percentage(), ' ',
                   ETA(), ' ',
                   FileTransferSpeed()]
        if currval is not None:
            raise NotImplementedError("Not yet supported to set currval in the beginning")
        return ProgressBar(widgets=widgets, maxval=maxval, fd=self.out).start()


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
        """
        Anaconda format:

Question? [choice1|choice2]
[default] >>> yes
        """
        attempt = 0
        while True:
            attempt += 1
            if attempt >= 100:
                raise RuntimeError("This is 100th attempt. Something really went wrong")
            if not hidden:
                self.out.write(msg + ": ")
                self.out.flush()  # not effective for stderr for some reason under annex

                # TODO: raw_input works only if stdin was not controlled by
                # (e.g. if coming from annex).  So we might need to do the
                # same trick as get_pass() does while directly dealing with /dev/pty
                # and provide per-OS handling with stdin being override
                response = (raw_input if PY2 else input)()
            else:
                response = getpass(msg + ": ")

            if not response and default:
                response = default
                break

            if choices and response not in choices:
                self.error("%r is not among choices: %s. Repeat your answer"
                           % (response, choices))
                continue
            break
        return response


# poor man thingie for now
@auto_repr
class UnderAnnexUI(DialogUI):
    def __init__(self, **kwargs):
        if 'out' not in kwargs:
            # to avoid buffering
            # http://stackoverflow.com/a/181654/1265472
            #kwargs['out'] = os.fdopen(sys.stderr.fileno(), 'w', 0)
            # but wasn't effective! sp kist straogjt for now
            kwargs['out'] = sys.stderr
        super(UnderAnnexUI, self).__init__(**kwargs)