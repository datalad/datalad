#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""

 COPYRIGHT: Yaroslav Halchenko 2013

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""
#-----------------\____________________________________/------------------

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

import os
import commands

import logging
lgr = logging.getLogger('datalad.files')

def dry(s, dry_):
    """Small helper for dry runs
    """
    if dry_:
        return "DRY " + s
    return s

class Runner(object):
    """Helper to run commands and functions while allowing for dry_run and later reporting
    """

    __slots__ = ['commands', 'dry']

    def __init__(self, dry=False):
        self.commands = []
        self.dry = dry                    # TODO: make use of it

    # TODO -- remove dry_run specification here -- use constructor parameter
    #def __call__(self, cmd, dry_run=False):
    def getstatusoutput(self, cmd, dry_run=None):
        """A wrapper around commands.getstatusoutput

        Provides improved logging for debugging purposes and raises
        RuntimeError exception in case of non-0 return
        """
        self.log("Running: %s" % (cmd,))
        if not self.dry:
            # status, output = commands.getstatusoutput(cmd)
            # doing manually for improved debugging
            pipe = os.popen('{ ' + cmd + '; } 2>&1', 'r')
            output = ''
            for line in iter(pipe.readline, ''):
                self.log("| " + line.rstrip('\n'), level=5)
                output += line
            if output[-1:] == '\n': output = output[:-1]
            status = pipe.close() or 0

            if not status in [0, None]:
                msg = "Failed to run %r. Exit code=%d output=%s" \
                      % (cmd, status, output)
                lgr.error(msg)
                raise RuntimeError(msg)
            else:
                self.log("Finished running %r with status %s" % (cmd, status),
                         level=8)
                return status, output
        else:
            self.commands.append(cmd)
        return None, None

    def drycall(self, f, *args, **kwargs):
        """Helper to unify collection of logging all "dry" actions.

        f : callable
        *args, **kwargs:
          Callable arguments
        """
        if self.dry:
            self.commands.append("%s args=%s kwargs=%s" % (f, args, kwargs))
        else:
            f(*args, **kwargs)

    def log(self, msg, level=None):
        if level is None:
            logf = lgr.debug
        else:
            logf = lambda msg: lgr.log(level, msg)
        if self.dry:
            lgr.debug("DRY: %s" % msg)
        else:
            lgr.debug(msg)

#getstatusoutput = Runner()

# this one might get under Runner for better output/control
def link_file_load(src, dst, dry_run=False):
    """Just a little helper to hardlink files's load
    """
    dst_dir = os.path.dirname(dst)
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    if os.path.lexists(dst):
        lgr.debug("Destination file %(dst)s exists. Removing it first"
                  % locals())
        # TODO: how would it interact with git/git-annex
        os.unlink(dst)
    lgr.debug("Hardlinking %(src)s under %(dst)s" % locals())
    os.link(os.path.realpath(src), dst)
