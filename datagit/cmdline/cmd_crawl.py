# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datagit package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Crawl the website to collect/extract data and push it into a git-annex repository.

"""

# For some reason argparse manages to remove all the formatting for me here.
"""
some more bits...

more TODO

Examples:

$ datagit crawl cfgs/openfmri.cfg

TODO: See TODO.org

"""

__docformat__ = 'restructuredtext'

# magic line for manpage summary
# man: -*- % crawl the website to collect/extract data for git-annex

__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

import calendar
import os
import re
import shutil
import time

import argparse
import os
import sys

import datagit.log


def setup_parser(parser):

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

#    parser.add_argument(
#        "--tests", action="store_true",
#        help="Do not do anything but run tests")
#
#     parser.add_argument(
#         '-l', '--log-level',
#         choices=['critical', 'error', 'warning', 'info', 'debug'] + [str(x) for x in range(1, 10)],
#         default='warning',
#         help="""level of verbosity. Integers provide even more debugging information""")
# 
#     if __debug__:
#         # borrowed from Michael's bigmess
#         parser.add_argument(
#             '--dbg', action='store_true', dest='common_debug',
#             help="do not catch exceptions and show exception traceback")

    parser.add_argument(
        "configs", metavar='file', nargs='+',
        help="Configuration file(s) defining the structure of the 'project'")


def run(args):
    from datagit.api import DoubleAnnexRepo, load_config
    from datagit.log import lgr

    lgr.debug("Command line arguments: %r" % args)

    lgr.info("Reading configs")
    cfg = load_config(args.configs)

    drepo = DoubleAnnexRepo(cfg)
    drepo.page2annex(existing=args.existing, dry_run=args.dry_run,
                     cache=args.cache)


