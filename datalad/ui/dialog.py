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


class DialogUI(object):
    def __init__(self, out=sys.stdout):
        self.out = sys.stdout

    def question(self, text, title=None, choices=None, hidden=False):
        if title:
            self.out.write(title + "\n")
        if choices is not None:
            msg = "%s (choices: %s)" % (text, ' '.join(choices))
        else:
            msg = text
        done = False
        while not done:
            self.out.write(msg + ": ")

            # TODO: raw_input works only if stdin was not controlled by
            # (e.g. if coming from annex).  So we might need to do the
            # same trick as get_pass() does while directly dealing with /dev/pty
            # and provide per-OS handling with stdin being override
            response = raw_input() if not hidden else getpass('')
            if choices:
                if response not in choices:
                    self.error("%s is not among choices: %s. Repeat your answer"
                               % (response, choices))
                else:
                    done = True
            else:
                done = True
        return response

    def yesno(self, *args, **kwargs):
        response = self.question(*args, choices=['yes', 'no'], **kwargs).rstrip('\n')
        if response == 'yes':
            return True
        elif response == 'no':
            return False
        else:
            raise RuntimeError("must not happen but did")

    def message(self, msg):
        self.out.write(msg)

    def error(self, error):
        self.out.write("ERROR: %s\n" % error)


if __name__ == '__main__':
    ui = DialogUI()
    ui.yesno("Found no credentials for CRCNS.org.  Do you have any?",
             title="Danger zone")