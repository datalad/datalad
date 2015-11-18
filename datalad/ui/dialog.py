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
#
class DialogUI(object):
    def __init__(self, out=sys.stdout):
        self.out = sys.stdout

    def question(self, text, title=None, choices=None):
        if title:
            self.out.write(title + "\n")
        if choices is not None:
            msg = "%s (choices: %s)" % (text, ' '.join(choices))
        else:
            msg = text
        done = False
        while not done:
            self.out.write(msg + ": ")

            response = raw_input()
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

    def getpass(self):
        return getpass()

    def error(self, error):
        self.out.write("ERROR: %s\n" % error)


if __name__ == '__main__':
    ui = DialogUI()
    ui.yesno("Found no credentials for CRCNS.org.  Do you have any?",
             title="Danger zone")