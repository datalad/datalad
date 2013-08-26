#!/usr/bin/python
#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""
 @file      fetch_url.py
 @date      Wed May 22 15:31:19 2013
 @brief


  Yaroslav Halchenko                                            Dartmouth
  web:     http://www.onerussian.com                              College
  e-mail:  yoh@onerussian.com                              ICQ#: 60653192

 DESCRIPTION (NOTES):

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
__version__ = "0.0.0.dev"

import calendar
import os
import re
import shutil
import time

import datagit.log
from datagit.api import *


class RegexpType(object):
    """Factory for creating regular expression types for argparse

    DEPRECATED AFAIK -- now things are in the config file...
    but we might provide a mode where we operate solely from cmdline
    """
    def __call__(self, string):
        if string:
            return re.compile(string)
        else:
            return None


if __name__ == '__main__':

    # setup cmdline args parser
    # main parser
    import argparse
    import os
    import sys

    import logging
    lgr = logging.getLogger('datagit')

    parser = argparse.ArgumentParser(
        fromfile_prefix_chars='@',
        description="""
    Fetch web page's linked content into git-annex repository.

    """,
        epilog='',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
        version=__version__
    )

    # common options
#    parser.add_argument(
#        "-a", "--addurl-opts", default="",
#        help="Additional options to pass to 'git annex addurl', e.g. --fast")
#    parser.add_argument(
#        "-i", "--include", type=RegexpType(),
#        help="Include links which match regular expression (by HREF). "
#             "Otherwise all are considered")
#    parser.add_argument(
#        "-e", "--exclude", type=RegexpType(),
#        help="Exclude links which match regular expression (by HREF)")
#     parser.add_argument(
#         "--use-a", action="store_true",
#         help="Use name provided in the link, not filename given by the server")

    # TODO: we might want few modes than just dry:
    #   act [default] as now without dry-run
    #   monitor -- the one like dry BUT which would collect all "interesting"
    #              entries and if anything to be actually done -- spit them
    #              out or email?
    parser.add_argument(
        "-n", "--dry-run", action="store_true",
        help="No git-annex is invoked, commands are only printed to the screen")

    parser.add_argument(
        "--cache", action="store_true",
        help="Either to cache fetching of pages and parsing out urls")

    parser.add_argument(
        "--existing", choices=('check', 'skip'), default='check',
        help="How to deal with files already known. 'skip' would entirely skip "
        "file without checking if it was modified or not. 'check' would "
        "proceed normally updating the file(s) if changed")

    parser.add_argument(
        "--tests", action="store_true",
        help="Do not do anything but run tests")

    parser.add_argument(
        '-l', '--log-level',
        choices=['critical', 'error', 'warning', 'info', 'debug'] + [str(x) for x in range(1, 10)],
        default='warning',
        help="""level of verbosity. Integers provide even more debugging information""")

    if __debug__:
        # borrowed from Michael's bigmess
        parser.add_argument(
            '--dbg', action='store_true', dest='common_debug',
            help="do not catch exceptions and show exception traceback")


    parser.add_argument("configs", metavar='file', nargs='+',
                        help="Configuration file(s) defining the structure of the 'project'")

    args = parser.parse_args() #['-n', '-l', 'debug', 'allen-genetic.cfg'])

    # set our loglevel
    datagit.log.set_level(args.log_level)

    lgr.debug("Command line arguments: %r" % args)

    if args.tests:
        lgr.info("Running tests")
        import nose
        # TODO fix it so it works ;-)
        nose.runmodule('datagit', exit=True)

    try:
        lgr.info("Reading configs")
        cfg = load_config(args.configs)
        page2annex(cfg, existing=args.existing, dry_run=args.dry_run, cache=args.cache)

    except Exception as exc:
        lgr.error('%s (%s)' % (str(exc), exc.__class__.__name__))
        if __debug__ and args.common_debug:
            import pdb
            pdb.post_mortem()
        raise

