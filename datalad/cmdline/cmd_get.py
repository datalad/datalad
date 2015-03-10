# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Get content from a dataset

"""

"""
some more bits...

more TODO

Examples:

$ datalad get foo/*

TODO: See TODO.org

"""

__docformat__ = 'restructuredtext'

# magic line for manpage summary
# man: -*- % get a dataset from a remote repository


import calendar
import os
import re
import shutil
import time

import argparse
import os
import sys

import datalad.log
from .helpers import parser_add_common_args

def setup_parser(parser):

    parser.add_argument(
        "path", metavar='file', nargs='+',
        help="path or pattern describing what to get")

    #parser_add_common_args(parser, opt=('log_level'))
    
def run(args):
    import glob

    from datalad.api import Dataset
    from datalad.log import lgr

    lgr.debug("Command line arguments: %r" % args)

    cwd_path = os.getcwd()
    ds = Dataset(cwd_path)

    # args.path comes as a list
    # Expansions (like globs) provided by the shell itself are already done.
    # But: We don't know exactly what shells we are running on and what it may provide or not.
    # Therefore, make any expansion we want to guarantee, per item of the list:

    expanded_list = []
    for item in args.path:
        expanded_list.extend(glob.glob(item))
        # TODO: regexp + may be ext. glob zsh-style
        # TODO: what about spaces in filenames and similar things?
        # TODO: os.path.expandvars, os.path.expanduser? Is not needed here, isn't it? Always?

    ds.get(expanded_list)